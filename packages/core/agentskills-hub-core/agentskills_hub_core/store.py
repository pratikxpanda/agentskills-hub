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
import shutil
import uuid
from pathlib import Path
from typing import Protocol

from agentskills_core import Skill as SdkSkill
from agentskills_core import validate_skill
from agentskills_fs import LocalFileSystemSkillProvider

from agentskills_hub_core.archives import ArchiveLimits, content_digest, extract
from agentskills_hub_core.identifiers import validate_skill_id, validate_version

SKILL_FILE = "SKILL.md"


class SkillStoreError(Exception):
    """Base class for store failures. Messages name a skill and version, never a server path."""


class VersionAlreadyPublishedError(SkillStoreError):
    """The target version already exists. Republishing is an error, never an overwrite."""


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

    async def publish(self, skill_id: str, version: str, archive: Path) -> str:
        """Store a version's content and return its digest."""


class LocalFileSystemSkillStore:
    def __init__(self, root: Path, limits: ArchiveLimits | None = None) -> None:
        self._root = Path(root).resolve()
        self._limits = limits or ArchiveLimits()
        self._skills = self._root / "skills"
        self._staging = self._root / "staging"

    @property
    def root(self) -> Path:
        return self._root

    def version_root(self, skill_id: str, version: str) -> Path:
        validate_skill_id(skill_id)
        validate_version(version)
        candidate = (self._skills / skill_id / version).resolve()
        # Belt and braces: the identifier patterns already exclude separators, but the assertion
        # costs nothing and this is the path that trusts them.
        if self._skills not in candidate.parents:
            raise SkillStoreError(f"resolved path for {skill_id} {version} escapes the store")
        return candidate

    def exists(self, skill_id: str, version: str) -> bool:
        return (self.version_root(skill_id, version) / skill_id / SKILL_FILE).is_file()

    async def publish(self, skill_id: str, version: str, archive: Path) -> str:
        destination = self.version_root(skill_id, version)
        if destination.exists():
            raise VersionAlreadyPublishedError(
                f"{skill_id} {version} is already published; versions are immutable"
            )

        workspace = self._staging / uuid.uuid4().hex
        try:
            staged = await asyncio.to_thread(self._stage, skill_id, archive, workspace)
            errors = await validate_skill(
                SdkSkill(skill_id=skill_id, provider=LocalFileSystemSkillProvider(staged))
            )
            if errors:
                raise InvalidSkillArchiveError(
                    f"{skill_id} {version} failed validation", errors=errors
                )
            return await asyncio.to_thread(self._commit, staged, destination)
        finally:
            await asyncio.to_thread(shutil.rmtree, workspace, True)

    def _stage(self, skill_id: str, archive: Path, workspace: Path) -> Path:
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
    "SkillStore",
    "SkillStoreError",
    "VersionAlreadyPublishedError",
]
