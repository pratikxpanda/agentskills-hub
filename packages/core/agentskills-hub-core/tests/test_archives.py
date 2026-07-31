"""Archive extraction, exercised with hostile fixtures.

Every archive here is built by hand rather than by shutil.make_archive: the point is to produce
members a well-behaved packer would never emit.
"""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from agentskills_hub_core.archives import (
    ArchiveLimits,
    UnsafeArchiveError,
    UnsupportedArchiveError,
    content_digest,
    extract,
)

TIGHT = ArchiveLimits(max_total_bytes=512, max_file_bytes=256, max_members=4)


def _tar_with(
    path: Path, *members: tarfile.TarInfo, payloads: dict[str, bytes] | None = None
) -> Path:
    payloads = payloads or {}
    with tarfile.open(path, "w:gz") as tf:
        for member in members:
            data = payloads.get(member.name)
            if data is None:
                tf.addfile(member)
            else:
                member.size = len(data)
                tf.addfile(member, io.BytesIO(data))
    return path


def _regular(name: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.REGTYPE
    return info


def test_a_well_formed_zip_extracts(tmp_path: Path) -> None:
    archive = tmp_path / "skill.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("SKILL.md", "content")
        zf.writestr("references/notes.md", "notes")

    destination = tmp_path / "out"
    extract(archive, destination)

    assert (destination / "SKILL.md").read_text() == "content"
    assert (destination / "references" / "notes.md").read_text() == "notes"


def test_a_well_formed_tar_extracts(tmp_path: Path) -> None:
    archive = _tar_with(
        tmp_path / "skill.tar.gz",
        _regular("SKILL.md"),
        payloads={"SKILL.md": b"content"},
    )

    destination = tmp_path / "out"
    extract(archive, destination)

    assert (destination / "SKILL.md").read_bytes() == b"content"


def test_zip_slip_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escaped.txt", "pwned")

    with pytest.raises(UnsafeArchiveError, match="traverses"):
        extract(archive, tmp_path / "out")
    assert not (tmp_path / "escaped.txt").exists()


def test_tar_traversal_is_rejected(tmp_path: Path) -> None:
    archive = _tar_with(
        tmp_path / "evil.tar.gz",
        _regular("../escaped.txt"),
        payloads={"../escaped.txt": b"pwned"},
    )

    with pytest.raises(UnsafeArchiveError, match="traverses"):
        extract(archive, tmp_path / "out")
    assert not (tmp_path / "escaped.txt").exists()


def test_absolute_paths_are_rejected(tmp_path: Path) -> None:
    archive = _tar_with(
        tmp_path / "abs.tar.gz",
        _regular("/etc/passwd"),
        payloads={"/etc/passwd": b"pwned"},
    )

    with pytest.raises(UnsafeArchiveError, match="absolute"):
        extract(archive, tmp_path / "out")


def test_backslash_members_are_rejected(tmp_path: Path) -> None:
    # A Windows-style separator is a directory separator once it reaches Path, so a member that
    # looks like a harmless filename on POSIX becomes a path on Windows. The fixture is a tar
    # because zipfile rewrites os.sep to "/" while reading, which hides the case entirely.
    archive = _tar_with(
        tmp_path / "backslash.tar.gz",
        _regular("sub\\escaped.txt"),
        payloads={"sub\\escaped.txt": b"pwned"},
    )

    with pytest.raises(UnsafeArchiveError, match="backslash"):
        extract(archive, tmp_path / "out")


def test_drive_letters_are_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "drive.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("C:/windows/system32/evil.dll", "pwned")

    with pytest.raises(UnsafeArchiveError, match="drive"):
        extract(archive, tmp_path / "out")


def test_tar_symlinks_are_rejected(tmp_path: Path) -> None:
    link = tarfile.TarInfo("secrets")
    link.type = tarfile.SYMTYPE
    link.linkname = "/etc/shadow"
    archive = _tar_with(tmp_path / "link.tar.gz", link)

    with pytest.raises(UnsafeArchiveError, match="not a regular file"):
        extract(archive, tmp_path / "out")


def test_zip_symlinks_are_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "link.zip"
    info = zipfile.ZipInfo("secrets")
    info.external_attr = (0o120777 << 16) | 0o600
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(info, "/etc/shadow")

    with pytest.raises(UnsafeArchiveError, match="symlink"):
        extract(archive, tmp_path / "out")


def test_non_regular_members_are_rejected(tmp_path: Path) -> None:
    fifo = tarfile.TarInfo("pipe")
    fifo.type = tarfile.FIFOTYPE
    archive = _tar_with(tmp_path / "fifo.tar.gz", fifo)

    with pytest.raises(UnsafeArchiveError, match="not a regular file"):
        extract(archive, tmp_path / "out")


def test_total_size_bomb_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "bomb.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for index in range(3):
            zf.writestr(f"file{index}.txt", "a" * 250)

    with pytest.raises(UnsafeArchiveError, match="total limit"):
        extract(archive, tmp_path / "out", TIGHT)


def test_per_file_size_bomb_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "bomb.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("huge.txt", "a" * 400)

    with pytest.raises(UnsafeArchiveError, match=r"file limit|declares more"):
        extract(archive, tmp_path / "out", TIGHT)


def test_member_count_bomb_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "many.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for index in range(10):
            zf.writestr(f"file{index}.txt", "a")

    with pytest.raises(UnsafeArchiveError, match="more than 4 members"):
        extract(archive, tmp_path / "out", TIGHT)


def test_tar_member_count_bomb_is_rejected(tmp_path: Path) -> None:
    members = [_regular(f"file{index}.txt") for index in range(10)]
    archive = _tar_with(
        tmp_path / "many.tar.gz",
        *members,
        payloads={member.name: b"a" for member in members},
    )

    with pytest.raises(UnsafeArchiveError, match="more than 4 members"):
        extract(archive, tmp_path / "out", TIGHT)


def test_a_file_that_is_not_an_archive_is_rejected(tmp_path: Path) -> None:
    plain = tmp_path / "notes.txt"
    plain.write_text("not an archive")

    with pytest.raises(UnsupportedArchiveError):
        extract(plain, tmp_path / "out")


def test_digest_is_stable_for_identical_trees(tmp_path: Path) -> None:
    def build(root: Path, body: str) -> Path:
        (root / "nested").mkdir(parents=True)
        (root / "SKILL.md").write_text(body)
        (root / "nested" / "notes.md").write_text("notes")
        return root

    first = build(tmp_path / "a", "content")
    second = build(tmp_path / "b", "content")
    assert content_digest(first) == content_digest(second)


def test_digest_changes_with_content_and_with_layout(tmp_path: Path) -> None:
    base = tmp_path / "a"
    base.mkdir()
    (base / "SKILL.md").write_text("content")
    original = content_digest(base)

    (base / "SKILL.md").write_text("content ")
    assert content_digest(base) != original

    (base / "SKILL.md").write_text("content")
    (base / "extra.md").write_text("")
    assert content_digest(base) != original
