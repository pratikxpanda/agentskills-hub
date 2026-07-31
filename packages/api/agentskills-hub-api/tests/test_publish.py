"""Publishing.

Every rejection path asserts the same thing twice: the right status, and that nothing was left
under `skills/`. A publish that fails halfway is the failure mode that matters here, because the
leftovers would be invisible to the database and visible to the gateway.
"""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest
from httpx import AsyncClient, Response

from conftest import ApiFactory, ApiFixture, skill_markdown


def _targz(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tf:
        for name, payload in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def _zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in files.items():
            zf.writestr(name, payload)
    return buffer.getvalue()


def _archive(skill_id: str = "incident-response", **kwargs: str) -> bytes:
    return _targz({f"{skill_id}/SKILL.md": skill_markdown(skill_id, **kwargs).encode()})


async def _publish(
    client: AsyncClient,
    headers: dict[str, str],
    payload: bytes,
    *,
    skill_id: str = "incident-response",
    version: str = "1.0.0",
    tags: str | None = None,
    filename: str = "skill.tar.gz",
) -> Response:
    data = {"skill_id": skill_id, "version": version}
    if tags is not None:
        data["tags"] = tags
    return await client.post(
        "/api/skills",
        headers=headers,
        data=data,
        files={"archive": (filename, payload, "application/gzip")},
    )


def _published(store_root: Path) -> list[Path]:
    skills = store_root / "skills"
    return sorted(skills.rglob("SKILL.md")) if skills.exists() else []


async def test_a_valid_skill_is_published(api: ApiFixture) -> None:
    response = await _publish(api.client, api.alice.headers, _archive())

    assert response.status_code == 201
    body = response.json()
    assert body["skill_id"] == "incident-response"
    assert body["version"] == "1.0.0"
    assert len(body["content_digest"]) == 64
    assert body["description"]


async def test_the_stored_tree_is_readable_by_the_sdk_provider(api: ApiFixture) -> None:
    """The doubled directory exists so the Hub owns no retrieval code. Prove the SDK can read it."""
    from agentskills_core import Skill as SdkSkill
    from agentskills_fs import LocalFileSystemSkillProvider

    await _publish(api.client, api.alice.headers, _archive())

    version_root = api.store_root / "skills" / "incident-response" / "1.0.0"
    skill = SdkSkill(
        skill_id="incident-response", provider=LocalFileSystemSkillProvider(version_root)
    )
    assert (await skill.get_metadata())["name"] == "incident-response"
    assert await skill.get_body()


async def test_a_zip_is_accepted_too(api: ApiFixture) -> None:
    payload = _zip({"incident-response/SKILL.md": skill_markdown("incident-response").encode()})
    response = await _publish(api.client, api.alice.headers, payload, filename="skill.zip")

    assert response.status_code == 201


async def test_a_skill_file_at_the_archive_root_is_accepted(api: ApiFixture) -> None:
    payload = _targz({"SKILL.md": skill_markdown("incident-response").encode()})
    response = await _publish(api.client, api.alice.headers, payload)

    assert response.status_code == 201


async def test_publishing_requires_a_credential(api: ApiFixture) -> None:
    response = await _publish(api.client, {}, _archive())

    assert response.status_code == 401
    assert _published(api.store_root) == []


async def test_the_sdk_error_messages_are_passed_through_verbatim(api: ApiFixture) -> None:
    payload = _targz(
        {"incident-response/SKILL.md": b"---\nname: incident-response\n---\n\nBody.\n"}
    )
    response = await _publish(api.client, api.alice.headers, payload)

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "invalid_skill"
    # The Hub does not paraphrase spec errors: an author sees what the agentskills CLI would say.
    assert any("description" in detail for detail in body["error"]["details"])
    assert _published(api.store_root) == []


async def test_a_name_that_disagrees_with_skill_id_is_rejected(api: ApiFixture) -> None:
    payload = _targz({"incident-response/SKILL.md": skill_markdown("something-else").encode()})
    response = await _publish(api.client, api.alice.headers, payload)

    assert response.status_code == 400
    assert _published(api.store_root) == []


async def test_an_archive_without_a_skill_file_is_rejected(api: ApiFixture) -> None:
    response = await _publish(api.client, api.alice.headers, _targz({"notes/README.md": b"hi"}))

    assert response.status_code == 400
    assert _published(api.store_root) == []


async def test_something_that_is_not_an_archive_is_rejected(api: ApiFixture) -> None:
    response = await _publish(api.client, api.alice.headers, b"this is not an archive")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_archive"
    assert _published(api.store_root) == []


@pytest.mark.parametrize(
    ("skill_id", "version"),
    [
        ("Incident-Response", "1.0.0"),
        ("has--double-dash", "1.0.0"),
        ("../escape", "1.0.0"),
        ("incident-response", "1.0"),
        ("incident-response", "v1.0.0"),
        ("incident-response", "not-a-version"),
    ],
)
async def test_malformed_identifiers_are_rejected_before_anything_is_read(
    api: ApiFixture, skill_id: str, version: str
) -> None:
    response = await _publish(
        api.client, api.alice.headers, _archive(), skill_id=skill_id, version=version
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_identifier"
    assert _published(api.store_root) == []


async def test_republishing_a_version_is_a_conflict_and_changes_nothing(api: ApiFixture) -> None:
    first = await _publish(api.client, api.alice.headers, _archive())
    assert first.status_code == 201

    second = await _publish(
        api.client, api.alice.headers, _archive(description="Completely different.")
    )

    assert second.status_code == 409
    stored = (
        api.store_root / "skills" / "incident-response" / "1.0.0" / "incident-response" / "SKILL.md"
    ).read_text()
    assert "Completely different." not in stored


async def test_a_second_version_of_the_same_skill_is_accepted(api: ApiFixture) -> None:
    assert (await _publish(api.client, api.alice.headers, _archive())).status_code == 201
    second = await _publish(api.client, api.alice.headers, _archive(), version="1.1.0")

    assert second.status_code == 201
    assert len(_published(api.store_root)) == 2


async def test_tags_must_be_a_json_array_of_strings(api: ApiFixture) -> None:
    response = await _publish(api.client, api.alice.headers, _archive(), tags="sre, oncall")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_tags"
    assert _published(api.store_root) == []


async def test_tags_are_accepted_as_json(api: ApiFixture) -> None:
    response = await _publish(api.client, api.alice.headers, _archive(), tags='["sre", "oncall"]')

    assert response.status_code == 201


class TestLimits:
    """One test per limit. Each is configurable, so each is set low and then breached."""

    async def test_the_compressed_upload_limit(self, api_factory: ApiFactory) -> None:
        api = await api_factory(max_archive_bytes=64)
        response = await _publish(api.client, api.alice.headers, _archive())

        assert response.status_code == 413
        assert _published(api.store_root) == []

    async def test_the_uncompressed_total_limit(self, api_factory: ApiFactory) -> None:
        api = await api_factory(max_total_bytes=32)
        response = await _publish(api.client, api.alice.headers, _archive())

        assert response.status_code == 413
        assert _published(api.store_root) == []

    async def test_the_per_file_limit(self, api_factory: ApiFactory) -> None:
        api = await api_factory(max_file_bytes=32)
        response = await _publish(api.client, api.alice.headers, _archive())

        assert response.status_code == 413
        assert _published(api.store_root) == []

    async def test_the_member_count_limit(self, api_factory: ApiFactory) -> None:
        api = await api_factory(max_members=1)
        payload = _targz(
            {
                "incident-response/SKILL.md": skill_markdown("incident-response").encode(),
                "incident-response/extra.md": b"filler",
                "incident-response/more.md": b"filler",
            }
        )
        response = await _publish(api.client, api.alice.headers, payload)

        assert response.status_code == 413
        assert _published(api.store_root) == []


async def test_openapi_documents_the_request_and_every_error(api: ApiFixture) -> None:
    schema = (await api.client.get("/openapi.json")).json()
    operation = schema["paths"]["/api/skills"]["post"]

    assert set(operation["responses"]) >= {"201", "400", "409", "413"}
    for code in ("400", "409", "413"):
        ref = operation["responses"][code]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("ErrorResponse")

    body = operation["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"]
    fields = schema["components"]["schemas"][body.rsplit("/", 1)[-1]]["properties"]
    assert set(fields) == {"archive", "skill_id", "version", "tags"}
