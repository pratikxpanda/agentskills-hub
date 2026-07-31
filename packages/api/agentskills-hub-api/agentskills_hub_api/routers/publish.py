"""Publishing.

The order in `docs/issues/v0.1.md` is not an implementation detail: content that reaches the store
reaches an agent's context verbatim, so nothing may become visible before it has been validated,
and a rejected publish must leave nothing behind.
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile, status
from pydantic import BaseModel, Field

from agentskills_hub_api.dependencies import Principal, Session, Store
from agentskills_hub_api.errors import ApiError, ErrorResponse
from agentskills_hub_core import (
    InvalidIdentifierError,
    InvalidSkillArchiveError,
    SkillRepository,
    UnsafeArchiveError,
    UnsupportedArchiveError,
    VersionAlreadyPublishedError,
    validate_skill_id,
    validate_version,
)

router = APIRouter(prefix="/api", tags=["publishing"])


class PublishedSkill(BaseModel):
    skill_id: str
    version: str
    content_digest: str = Field(description="SHA-256 over the stored tree. Stable across hosts.")
    description: str
    owner_team_id: uuid.UUID
    version_id: uuid.UUID


def _parse_tags(raw: str | None) -> list[str]:
    if raw is None or raw.strip() == "":
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "invalid_tags",
            "tags must be a JSON array of strings.",
            [str(exc)],
        ) from exc
    if not isinstance(parsed, list) or not all(isinstance(tag, str) for tag in parsed):
        raise ApiError(
            status.HTTP_400_BAD_REQUEST, "invalid_tags", "tags must be a JSON array of strings."
        )
    return parsed


@router.post(
    "/skills",
    status_code=status.HTTP_201_CREATED,
    response_model=PublishedSkill,
    summary="Publish a skill version",
    responses={
        400: {"model": ErrorResponse, "description": "Identifiers, tags, or content are invalid."},
        409: {"model": ErrorResponse, "description": "That version is already published."},
        413: {"model": ErrorResponse, "description": "An archive limit was breached."},
    },
)
async def publish_skill(
    principal: Principal,
    session: Session,
    store: Store,
    archive: Annotated[UploadFile, File(description="tar.gz or zip of the skill folder.")],
    skill_id: Annotated[str, Form(description="Must equal the frontmatter `name`.")],
    version: Annotated[str, Form(description="Semantic version. Immutable once published.")],
    tags: Annotated[str | None, Form(description="JSON array of strings.")] = None,
) -> PublishedSkill:
    try:
        validate_skill_id(skill_id)
        validate_version(version)
    except InvalidIdentifierError as exc:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_identifier", str(exc)) from exc

    parsed_tags = _parse_tags(tags)
    skills = SkillRepository(session)

    existing = await skills.get_by_skill_id(skill_id)
    if store.exists(skill_id, version) or (
        existing is not None and await skills.get_version(existing.id, version) is not None
    ):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "version_exists",
            f"{skill_id} {version} is already published; versions are immutable.",
        )

    try:
        published = await store.publish(skill_id, version, archive.file)
    except VersionAlreadyPublishedError as exc:
        # Lost a race with a concurrent publish of the same version.
        raise ApiError(status.HTTP_409_CONFLICT, "version_exists", str(exc)) from exc
    except InvalidSkillArchiveError as exc:
        # The SDK's messages, unmodified: an author sees what the agentskills CLI would tell them.
        raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_skill", str(exc), exc.errors) from exc
    except UnsupportedArchiveError as exc:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "unsupported_archive", str(exc)) from exc
    except UnsafeArchiveError as exc:
        raise ApiError(status.HTTP_413_CONTENT_TOO_LARGE, "archive_rejected", str(exc)) from exc

    if existing is None:
        # Tags are set at creation only. Changing another team's tags is a v0.2 concern with an
        # authorisation question attached.
        existing = await skills.create(skill_id, principal.team_id, tags=parsed_tags)

    created = await skills.add_version(
        existing,
        version,
        published.description,
        published.digest,
        catalog_tokens=_estimate_catalog_tokens(skill_id, published.description),
        published_by=principal.team_slug,
    )

    return PublishedSkill(
        skill_id=skill_id,
        version=version,
        content_digest=published.digest,
        description=published.description,
        owner_team_id=existing.owner_team_id,
        version_id=created.id,
    )


def _estimate_catalog_tokens(skill_id: str, description: str) -> int:
    """Rough size of the catalog entry an agent sees. Four characters per token until v0.3
    introduces a real budget and a real tokenizer."""
    return (len(skill_id) + len(description)) // 4
