"""The versioned skill store, including the property the whole layout exists for."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from agentskills_core import Skill as SdkSkill
from agentskills_core import validate_skill
from agentskills_fs import LocalFileSystemSkillProvider

from agentskills_hub_core import store as store_module
from agentskills_hub_core.identifiers import InvalidIdentifierError
from agentskills_hub_core.store import (
    InvalidSkillArchiveError,
    LocalFileSystemSkillStore,
    SkillStore,
    VersionAlreadyPublishedError,
)

SKILL_ID = "incident-response"


def frontmatter(name: str, body: str = "Steps for the on-call engineer.") -> str:
    return (
        f"---\nname: {name}\n"
        "description: Guides an on-call engineer through an incident.\n---\n\n"
        f"{body}\n"
    )


def make_archive(
    path: Path,
    *,
    skill_id: str = SKILL_ID,
    name: str | None = None,
    body: str = "Steps for the on-call engineer.",
    nested: bool = False,
) -> Path:
    prefix = f"{skill_id}/" if nested else ""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{prefix}SKILL.md", frontmatter(name or skill_id, body))
        zf.writestr(f"{prefix}references/runbook.md", "Runbook.\n")
    return path


@pytest.fixture
def store(tmp_path: Path) -> LocalFileSystemSkillStore:
    return LocalFileSystemSkillStore(tmp_path / "store")


def test_local_store_satisfies_the_protocol(store: LocalFileSystemSkillStore) -> None:
    # Structural, so the assertion that matters is mypy's: a blob-backed implementation has to
    # satisfy the same shape.
    def accepts(candidate: SkillStore) -> SkillStore:
        return candidate

    assert accepts(store) is store


async def test_a_published_version_reads_with_the_sdk_provider(
    store: LocalFileSystemSkillStore, tmp_path: Path
) -> None:
    """The whole doubled-directory layout exists to make this work with no adapter code."""
    await store.publish(SKILL_ID, "1.0.0", make_archive(tmp_path / "skill.zip"))

    provider = LocalFileSystemSkillProvider(store.version_root(SKILL_ID, "1.0.0"))
    skill = SdkSkill(skill_id=SKILL_ID, provider=provider)

    assert await validate_skill(skill) == []
    assert "on-call engineer" in await skill.get_body()
    assert (await skill.get_metadata())["name"] == SKILL_ID


async def test_an_archive_nesting_the_skill_directory_is_accepted(
    store: LocalFileSystemSkillStore, tmp_path: Path
) -> None:
    await store.publish(SKILL_ID, "1.0.0", make_archive(tmp_path / "skill.zip", nested=True))

    assert store.exists(SKILL_ID, "1.0.0")
    assert (store.version_root(SKILL_ID, "1.0.0") / SKILL_ID / "SKILL.md").is_file()


async def test_republishing_raises_and_leaves_the_existing_content_untouched(
    store: LocalFileSystemSkillStore, tmp_path: Path
) -> None:
    await store.publish(SKILL_ID, "1.0.0", make_archive(tmp_path / "first.zip", body="Original."))
    published = store.version_root(SKILL_ID, "1.0.0") / SKILL_ID / "SKILL.md"
    original = published.read_text()

    replacement = make_archive(tmp_path / "second.zip", body="Replacement.")
    with pytest.raises(VersionAlreadyPublishedError):
        await store.publish(SKILL_ID, "1.0.0", replacement)

    assert published.read_text() == original


async def test_a_commit_interrupted_before_the_rename_leaves_nothing_visible(
    store: LocalFileSystemSkillStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(root: Path) -> str:
        raise RuntimeError("interrupted")

    monkeypatch.setattr(store_module, "content_digest", boom)

    with pytest.raises(RuntimeError, match="interrupted"):
        await store.publish(SKILL_ID, "1.0.0", make_archive(tmp_path / "skill.zip"))

    assert not store.exists(SKILL_ID, "1.0.0")
    assert not store.version_root(SKILL_ID, "1.0.0").exists()
    assert list((store.root / "staging").glob("*")) == []


async def test_a_failed_publish_leaves_no_staging_directory(
    store: LocalFileSystemSkillStore, tmp_path: Path
) -> None:
    archive = make_archive(tmp_path / "skill.zip", name="a-different-name")

    with pytest.raises(InvalidSkillArchiveError) as caught:
        await store.publish(SKILL_ID, "1.0.0", archive)

    assert caught.value.errors
    assert not store.version_root(SKILL_ID, "1.0.0").exists()
    assert list((store.root / "staging").glob("*")) == []


async def test_an_archive_without_a_skill_file_is_rejected(
    store: LocalFileSystemSkillStore, tmp_path: Path
) -> None:
    archive = tmp_path / "empty.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.md", "no skill here")

    with pytest.raises(InvalidSkillArchiveError, match=r"SKILL\.md"):
        await store.publish(SKILL_ID, "1.0.0", archive)


async def test_digest_is_returned_and_is_content_addressed(
    store: LocalFileSystemSkillStore, tmp_path: Path
) -> None:
    first = await store.publish(SKILL_ID, "1.0.0", make_archive(tmp_path / "a.zip"))
    second = await store.publish(SKILL_ID, "1.0.1", make_archive(tmp_path / "b.zip"))
    changed = await store.publish(
        SKILL_ID, "1.0.2", make_archive(tmp_path / "c.zip", body="Different steps.")
    )

    assert first == second
    assert changed != first
    assert len(first) == 64


def test_identifiers_are_validated_before_a_path_is_built(
    store: LocalFileSystemSkillStore,
) -> None:
    with pytest.raises(InvalidIdentifierError):
        store.version_root("../../etc", "1.0.0")
    with pytest.raises(InvalidIdentifierError):
        store.version_root(SKILL_ID, "../../etc")


async def test_errors_never_disclose_server_paths(
    store: LocalFileSystemSkillStore, tmp_path: Path
) -> None:
    await store.publish(SKILL_ID, "1.0.0", make_archive(tmp_path / "first.zip"))

    with pytest.raises(VersionAlreadyPublishedError) as caught:
        await store.publish(SKILL_ID, "1.0.0", make_archive(tmp_path / "second.zip"))

    message = str(caught.value)
    assert str(tmp_path) not in message
    assert SKILL_ID in message and "1.0.0" in message


async def test_versions_are_independent_directories(
    store: LocalFileSystemSkillStore, tmp_path: Path
) -> None:
    await store.publish(SKILL_ID, "1.0.0", make_archive(tmp_path / "a.zip", body="First."))
    await store.publish(SKILL_ID, "2.0.0", make_archive(tmp_path / "b.zip", body="Second."))

    first = store.version_root(SKILL_ID, "1.0.0") / SKILL_ID / "SKILL.md"
    second = store.version_root(SKILL_ID, "2.0.0") / SKILL_ID / "SKILL.md"

    assert "First." in first.read_text()
    assert "Second." in second.read_text()
