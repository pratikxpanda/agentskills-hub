"""Archive extraction.

Everything here treats the archive as hostile. `tarfile.extractall` and `ZipFile.extractall` are
not used even with a filter: the limits below have to be enforced while bytes are being read, not
after a member has already landed on disk.
"""

from __future__ import annotations

import hashlib
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import IO

_CHUNK = 64 * 1024

# Symlinks and directories in a zip's external attributes, on the Unix half of the field.
_S_IFMT = 0o170000
_S_IFLNK = 0o120000
_S_IFDIR = 0o040000


class UnsafeArchiveError(Exception):
    """An archive member would escape the extraction root, or the archive exceeds its limits."""


class UnsupportedArchiveError(Exception):
    """The archive is neither a zip nor a tar."""


@dataclass(frozen=True)
class ArchiveLimits:
    # The first limit is on the compressed upload, the rest on what it expands to.
    max_archive_bytes: int = 20 * 1024 * 1024
    max_total_bytes: int = 50 * 1024 * 1024
    max_file_bytes: int = 10 * 1024 * 1024
    max_members: int = 2000


class _Budget:
    def __init__(self, limits: ArchiveLimits) -> None:
        self.limits = limits
        self.total = 0

    def spend(self, written: int, count: int) -> None:
        self.total += count
        if written > self.limits.max_file_bytes:
            raise UnsafeArchiveError(
                f"archive member exceeds the {self.limits.max_file_bytes} byte file limit"
            )
        if self.total > self.limits.max_total_bytes:
            raise UnsafeArchiveError(
                f"archive exceeds the {self.limits.max_total_bytes} byte total limit"
            )


def _resolve_member(root: Path, name: str) -> Path:
    """Resolve an archive member name under `root`, or refuse.

    `root` must already be resolved.
    """
    if not name or name in (".", "./"):
        raise UnsafeArchiveError("archive contains an unnamed member")
    if "\\" in name:
        raise UnsafeArchiveError(f"archive member {name!r} contains a backslash")
    pure = PurePosixPath(name)
    if pure.is_absolute():
        raise UnsafeArchiveError(f"archive member {name!r} is an absolute path")
    parts = [part for part in pure.parts if part != "."]
    if any(part == ".." for part in parts):
        raise UnsafeArchiveError(f"archive member {name!r} traverses outside the archive")
    if parts and ":" in parts[0]:
        raise UnsafeArchiveError(f"archive member {name!r} names a drive")

    target = root.joinpath(*parts)
    resolved = Path(target).resolve()
    if resolved != root and root not in resolved.parents:
        raise UnsafeArchiveError(f"archive member {name!r} escapes the extraction root")
    return target


def _write_member(source: IO[bytes], target: Path, budget: _Budget) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    # A declared size is a claim, not a fact; count the bytes that actually arrive.
    with target.open("wb") as handle:
        while chunk := source.read(_CHUNK):
            written += len(chunk)
            budget.spend(written, len(chunk))
            handle.write(chunk)


def _extract_zip(archive: Path, root: Path, limits: ArchiveLimits) -> None:
    budget = _Budget(limits)
    with zipfile.ZipFile(archive) as zf:
        infos = zf.infolist()
        if len(infos) > limits.max_members:
            raise UnsafeArchiveError(f"archive holds more than {limits.max_members} members")
        for info in infos:
            mode = (info.external_attr >> 16) & _S_IFMT
            if mode == _S_IFLNK:
                raise UnsafeArchiveError(f"archive member {info.filename!r} is a symlink")
            target = _resolve_member(root, info.filename)
            if info.is_dir() or mode == _S_IFDIR:
                target.mkdir(parents=True, exist_ok=True)
                continue
            if info.file_size > limits.max_file_bytes:
                raise UnsafeArchiveError(
                    f"archive member {info.filename!r} declares more than "
                    f"{limits.max_file_bytes} bytes"
                )
            with zf.open(info) as source:
                _write_member(source, target, budget)


def _extract_tar(archive: Path, root: Path, limits: ArchiveLimits) -> None:
    budget = _Budget(limits)
    with tarfile.open(archive, "r:*") as tf:
        members = 0
        for member in tf:
            members += 1
            if members > limits.max_members:
                raise UnsafeArchiveError(f"archive holds more than {limits.max_members} members")
            if not (member.isfile() or member.isdir()):
                raise UnsafeArchiveError(
                    f"archive member {member.name!r} is not a regular file or directory"
                )
            target = _resolve_member(root, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if member.size > limits.max_file_bytes:
                raise UnsafeArchiveError(
                    f"archive member {member.name!r} declares more than "
                    f"{limits.max_file_bytes} bytes"
                )
            source = tf.extractfile(member)
            if source is None:
                raise UnsafeArchiveError(f"archive member {member.name!r} has no content")
            with source:
                _write_member(source, target, budget)


def spool(source: IO[bytes], target: Path, max_bytes: int) -> None:
    """Write an uploaded stream to `target`, refusing it past `max_bytes`.

    Exists so that layers barred from importing `tempfile` can still hand over an upload: the
    stream lands inside the store's own staging workspace, which the caller already cleans up.
    A declared Content-Length is a claim, so the count is of bytes that actually arrive.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with target.open("wb") as handle:
        while chunk := source.read(_CHUNK):
            written += len(chunk)
            if written > max_bytes:
                raise UnsafeArchiveError(f"upload exceeds the {max_bytes} byte archive limit")
            handle.write(chunk)


def extract(archive: Path, destination: Path, limits: ArchiveLimits | None = None) -> None:
    """Extract `archive` into `destination`, refusing anything that escapes it."""
    limits = limits or ArchiveLimits()
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()

    if zipfile.is_zipfile(archive):
        _extract_zip(archive, root, limits)
    elif tarfile.is_tarfile(archive):
        _extract_tar(archive, root, limits)
    else:
        raise UnsupportedArchiveError("archive is neither a zip nor a tar")


def content_digest(root: Path) -> str:
    """SHA-256 over a directory tree: relative path, size, and bytes of every file, in order.

    Only files contribute, so an empty directory is invisible to the digest. Nothing the SDK reads
    lives in one.
    """
    entries = sorted(
        (path.relative_to(root).as_posix(), path) for path in root.rglob("*") if path.is_file()
    )
    digest = hashlib.sha256()
    for relative, path in entries:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(path.stat().st_size).encode("ascii"))
        digest.update(b"\0")
        with path.open("rb") as handle:
            while chunk := handle.read(_CHUNK):
                digest.update(chunk)
    return digest.hexdigest()
