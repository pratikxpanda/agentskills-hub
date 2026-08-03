"""The versioned skill store.

The layout nests one level further than seems necessary:

    {store_root}/skills/{skill_id}/{version}/{skill_id}/SKILL.md

`{store_root}/skills/{skill_id}/{version}` is handed straight to the SDK's
`LocalFileSystemSkillProvider`, and the `{skill_id}` directory inside it is the skill directory
the provider expects. The doubled segment is what lets the Hub own no retrieval code at all --
see ADR 0002.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any, Protocol

from agentskills_core import ResourceListingNotSupportedError, validate_skill
from agentskills_core import Skill as SdkSkill
from agentskills_fs import LocalFileSystemSkillProvider

from agentskills_hub_core.archives import ArchiveLimits, content_digest, extract, spool
from agentskills_hub_core.identifiers import validate_skill_id, validate_version

SKILL_FILE = "SKILL.md"


@dataclass(frozen=True)
class PublishedVersion:
    """What a successful publish learned about the content, so callers need not re-read it."""

    digest: str
    description: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StoredVersion:
    """A version's content, as the catalog serves it.

    `body` is markdown exactly as published. The Hub never renders it -- see item 5 and ADR 0002.
    """

    body: str
    metadata: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, list[str]] = field(default_factory=dict)


class SkillStoreError(Exception):
    """Base class for store failures. Messages name a skill and version, never a server path."""


class VersionAlreadyPublishedError(SkillStoreError):
    """The target version already exists. Republishing is an error, never an overwrite."""


class VersionNotStoredError(SkillStoreError):
    """The database knows about a version whose content is missing from the store."""


class InvalidSkillArchiveError(SkillStoreError):
    """The archive does not contain a skill the SDK can read."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


class SkillStore(Protocol):
    """Content storage for published skill versions.

    Deliberately narrow, so a blob-backed implementation can follow without touching callers.
    """

    def version_root(self, skill_id: str, version: str) -> Path:
        """The provider root for a version: pass it straight to a `SkillProvider`."""

    def exists(self, skill_id: str, version: str) -> bool: ...

    async def publish(
        self, skill_id: str, version: str, archive: Path | IO[bytes]
    ) -> PublishedVersion:
        """Store a version's content and describe what was stored."""

    async def read(self, skill_id: str, version: str) -> StoredVersion:
        """Return a stored version's markdown body, frontmatter, and resource inventory."""


class LocalFileSystemSkillStore:
    def __init__(self, root: Path | str, limits: ArchiveLimits | None = None) -> None:
        # `str` is accepted so that layers forbidden from importing pathlib can still configure a
        # root. Resolution happens here, once.
        self._root = Path(root).resolve()
        self._limits = limits or ArchiveLimits()
        # Resolved here so that a symlinked store directory is followed once, rather than on every
        # path built under it.
        self._skills = (self._root / "skills").resolve()
        self._staging = self._root / "staging"

    @property
    def root(self) -> Path:
        return self._root

    @property
    def limits(self) -> ArchiveLimits:
        return self._limits

    def version_root(self, skill_id: str, version: str) -> Path:
        validate_skill_id(skill_id)
        validate_version(version)

        # Both identifiers reach here straight from a URL path, so containment is established the
        # way a scanner can follow as well as a reader: normalise the join, then require the store
        # root as a literal prefix. The patterns above already exclude separators and `..`; this is
        # the second of the two independent reasons a traversal cannot get through.
        root = str(self._skills)
        candidate = os.path.normpath(os.path.join(root, skill_id, version))
        if not candidate.startswith(root + os.sep):
            raise SkillStoreError(f"resolved path for {skill_id} {version} escapes the store")
        return Path(candidate)

    def skill_dir(self, skill_id: str, version: str) -> Path:
        """The SDK skill directory inside a version root."""
        root = self.version_root(skill_id, version)
        # Taken from the validated path rather than from the argument a second time: the inner
        # segment is by construction the same one `version_root` already proved safe.
        return root / root.parent.name

    def exists(self, skill_id: str, version: str) -> bool:
        return (self.skill_dir(skill_id, version) / SKILL_FILE).is_file()

    async def publish(
        self, skill_id: str, version: str, archive: Path | IO[bytes]
    ) -> PublishedVersion:
        destination = self.version_root(skill_id, version)
        if destination.exists():
            raise VersionAlreadyPublishedError(
                f"{skill_id} {version} is already published; versions are immutable"
            )

        workspace = self._staging / uuid.uuid4().hex
        try:
            staged = await asyncio.to_thread(self._stage, skill_id, archive, workspace)
            skill = SdkSkill(skill_id=skill_id, provider=LocalFileSystemSkillProvider(staged))
            errors = await validate_skill(skill)
            if errors:
                raise InvalidSkillArchiveError(
                    f"{skill_id} {version} failed validation", errors=errors
                )

            metadata = await skill.get_metadata()
            # validate_skill already enforces this. Asserted again because the failure it guards
            # against is a silently mis-filed skill, which nothing downstream would notice.
            if metadata.get("name") != skill_id:
                raise InvalidSkillArchiveError(
                    f"{skill_id} {version} failed validation",
                    errors=[f"name {metadata.get('name')!r} does not match skill_id {skill_id!r}"],
                )

            digest = await asyncio.to_thread(self._commit, staged, destination)
            return PublishedVersion(
                digest=digest,
                description=str(metadata.get("description", "")),
                metadata=metadata,
            )
        finally:
            await asyncio.to_thread(shutil.rmtree, workspace, True)

    async def read(self, skill_id: str, version: str) -> StoredVersion:
        root = self.version_root(skill_id, version)
        if not self.exists(skill_id, version):
            raise VersionNotStoredError(f"{skill_id} {version} has no content in the store")

        skill = SdkSkill(skill_id=skill_id, provider=LocalFileSystemSkillProvider(root))
        try:
            resources = await skill.list_resources()
        except ResourceListingNotSupportedError:
            # A provider that cannot enumerate is not an error the catalog should surface; the
            # inventory is additional information, not the reason the page exists.
            resources = {}

        return StoredVersion(
            body=await skill.get_body(),
            metadata=await skill.get_metadata(),
            resources={kind: names for kind, names in resources.items() if names},
        )

    def _stage(self, skill_id: str, archive: Path | IO[bytes], workspace: Path) -> Path:
        if not isinstance(archive, Path):
            upload = workspace / "upload"
            spool(archive, upload, self._limits.max_archive_bytes)
            archive = upload

        extracted = workspace / "extracted"
        extract(archive, extracted, self._limits)

        if (extracted / SKILL_FILE).is_file():
            source = extracted
        elif (extracted / skill_id / SKILL_FILE).is_file():
            source = extracted / skill_id
        else:
            raise InvalidSkillArchiveError(
                f"archive for {skill_id} contains no {SKILL_FILE} at its root or under {skill_id}/"
            )

        staged = workspace / "staged"
        staged.mkdir(parents=True)
        source.rename(staged / skill_id)
        return staged

    def _commit(self, staged: Path, destination: Path) -> str:
        digest = content_digest(staged)
        destination.parent.mkdir(parents=True, exist_ok=True)
        # rename rather than replace: it refuses an existing destination, so a race between two
        # publishes of the same version fails instead of one silently clobbering the other.
        staged.rename(destination)
        return digest


__all__ = [
    "SKILL_FILE",
    "InvalidSkillArchiveError",
    "LocalFileSystemSkillStore",
    "PublishedVersion",
    "SkillStore",
    "SkillStoreError",
    "StoredVersion",
    "VersionAlreadyPublishedError",
    "VersionNotStoredError",
]
