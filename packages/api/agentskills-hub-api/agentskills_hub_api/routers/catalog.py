"""The catalog.

Read-only, and deliberately fat: the list response carries every field the catalog page renders,
so drawing a page costs one request rather than one plus N. A thin list response is not a smaller
API, it is the same API with the join moved into every client.

Bodies are returned as markdown and never as HTML. The Hub's entire content model is
user-submitted markdown, so a server-side renderer would put stored XSS one templating mistake
away; sanitisation belongs at render time, in the client that knows its own context.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field

from agentskills_hub_api.dependencies import Principal, Session, Store
from agentskills_hub_api.errors import ApiError, ErrorResponse
from agentskills_hub_core import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    CatalogEntry,
    CatalogRepository,
    DatabaseSession,
    InvalidCursorError,
    InvalidIdentifierError,
    LocalFileSystemSkillStore,
    Skill,
    SkillLifecycle,
    SkillRepository,
    SkillScope,
    StoredVersion,
    SubscriptionModel,
    VersionNotStoredError,
    VersionSummary,
    validate_skill_id,
    validate_version,
)

router = APIRouter(prefix="/api/skills", tags=["catalog"])

_MARKDOWN = "Raw markdown exactly as published. Never HTML."


class CatalogSkill(BaseModel):
    skill_id: str
    description: str
    owner: str = Field(description="Slug of the owning team.")
    scope: SkillScope
    lifecycle: SkillLifecycle
    subscription_model: SubscriptionModel
    tags: list[str]
    latest_version: str
    published_at: datetime | None
    subscriber_count: int
    is_subscribed: bool = Field(description="Whether the calling team is subscribed.")
    subscribed_version: str | None = Field(description="The version the calling team is pinned to.")


class CatalogPageResponse(BaseModel):
    items: list[CatalogSkill]
    next_cursor: str | None = Field(
        description="Pass as `cursor` for the next page. Absent on the last page."
    )


class SkillVersionSummary(BaseModel):
    version: str
    description: str
    content_digest: str
    catalog_tokens: int
    published_at: datetime | None
    published_by: str | None


class SkillDetail(CatalogSkill):
    body: str = Field(description=_MARKDOWN)
    resources: dict[str, list[str]] = Field(
        description="Filenames by kind: references, scripts, assets."
    )


class SkillVersionDetail(SkillVersionSummary):
    skill_id: str
    body: str = Field(description=_MARKDOWN)
    resources: dict[str, list[str]]


@router.get("", response_model=CatalogPageResponse, summary="Browse the catalog")
async def list_skills(
    principal: Principal,
    session: Session,
    q: Annotated[str | None, Query(description="Matches skill id, description, and tags.")] = None,
    tags: Annotated[
        list[str] | None, Query(description="Repeatable. A skill must carry all of them.")
    ] = None,
    cursor: Annotated[str | None, Query(description="From a previous `next_cursor`.")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> CatalogPageResponse:
    try:
        page = await CatalogRepository(session).list_skills(
            environment_id=principal.environment_id, query=q, tags=tags, cursor=cursor, limit=limit
        )
    except InvalidCursorError as exc:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_cursor", str(exc)) from exc
    except InvalidIdentifierError as exc:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_tags", str(exc)) from exc

    return CatalogPageResponse(
        items=[_entry(item) for item in page.entries], next_cursor=page.next_cursor
    )


@router.get(
    "/{skill_id}",
    response_model=SkillDetail,
    summary="One skill, with the body of its latest version",
    responses={404: {"model": ErrorResponse, "description": "No such published skill."}},
)
async def get_skill(
    principal: Principal, session: Session, store: Store, skill_id: str
) -> SkillDetail:
    entry = await _entry_or_404(session, skill_id, principal.environment_id)
    stored = await _read(store, skill_id, entry.latest_version)
    return SkillDetail(**_entry(entry).model_dump(), body=stored.body, resources=stored.resources)


@router.get(
    "/{skill_id}/versions",
    response_model=list[SkillVersionSummary],
    summary="Published versions, newest first",
    responses={404: {"model": ErrorResponse, "description": "No such published skill."}},
)
async def list_versions(
    principal: Principal, session: Session, skill_id: str
) -> list[SkillVersionSummary]:
    skill = await _skill_or_404(session, skill_id)
    versions = await CatalogRepository(session).list_versions(skill)
    return [_version(item) for item in versions]


@router.get(
    "/{skill_id}/versions/{version}",
    response_model=SkillVersionDetail,
    summary="One version, with its body",
    responses={404: {"model": ErrorResponse, "description": "No such published version."}},
)
async def get_version(
    principal: Principal, session: Session, store: Store, skill_id: str, version: str
) -> SkillVersionDetail:
    skill = await _skill_or_404(session, skill_id)
    try:
        validate_version(version)
    except InvalidIdentifierError as exc:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_identifier", str(exc)) from exc

    summary = await CatalogRepository(session).get_version(skill, version)
    if summary is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "version_not_found",
            f"{skill_id} has no published version {version}.",
        )

    stored = await _read(store, skill_id, version)
    return SkillVersionDetail(
        **_version(summary).model_dump(),
        skill_id=skill_id,
        body=stored.body,
        resources=stored.resources,
    )


async def _skill_or_404(session: DatabaseSession, skill_id: str) -> Skill:
    try:
        validate_skill_id(skill_id)
    except InvalidIdentifierError as exc:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_identifier", str(exc)) from exc

    skill = await SkillRepository(session).get_by_skill_id(skill_id)
    if skill is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "skill_not_found", f"No skill {skill_id}.")
    return skill


async def _entry_or_404(
    session: DatabaseSession, skill_id: str, environment_id: uuid.UUID
) -> CatalogEntry:
    await _skill_or_404(session, skill_id)
    entry = await CatalogRepository(session).get_entry(skill_id, environment_id=environment_id)
    if entry is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "skill_not_found",
            f"{skill_id} has no published version.",
        )
    return entry


async def _read(store: LocalFileSystemSkillStore, skill_id: str, version: str) -> StoredVersion:
    try:
        return await store.read(skill_id, version)
    except VersionNotStoredError as exc:
        # The row exists and the content does not. Not a 404: the catalog is wrong, not the caller.
        raise ApiError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "content_missing",
            f"{skill_id} {version} is recorded as published but its content is missing.",
        ) from exc


def _entry(entry: CatalogEntry) -> CatalogSkill:
    return CatalogSkill(
        skill_id=entry.skill_id,
        description=entry.description,
        owner=entry.owner,
        scope=entry.scope,
        lifecycle=entry.lifecycle,
        subscription_model=entry.subscription_model,
        tags=entry.tags,
        latest_version=entry.latest_version,
        published_at=entry.published_at,
        subscriber_count=entry.subscriber_count,
        is_subscribed=entry.is_subscribed,
        subscribed_version=entry.subscribed_version,
    )


def _version(summary: VersionSummary) -> SkillVersionSummary:
    return SkillVersionSummary(
        version=summary.version,
        description=summary.description,
        content_digest=summary.content_digest,
        catalog_tokens=summary.catalog_tokens,
        published_at=summary.published_at,
        published_by=summary.published_by,
    )
