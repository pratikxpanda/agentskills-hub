"""Subscriptions.

A subscription is the only thing that changes what an agent sees, so every route here is a
deliberate act by a named credential against a named version. There is no `latest` and there are
no ranges (ADR 0003): a floating pin means republishing a skill rewrites the system prompt of
every subscribed agent with no review and no way to correlate a behaviour change to a cause.

The compensating feature is visibility, which is why the list flags newer versions rather than
making the client fetch each skill to find out.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from agentskills_hub_api.dependencies import Session, TeamScoped
from agentskills_hub_api.errors import ApiError, ErrorResponse
from agentskills_hub_core import (
    CatalogRepository,
    DatabaseSession,
    InvalidIdentifierError,
    Skill,
    SkillLifecycle,
    SkillRepository,
    SubscriptionOrigin,
    SubscriptionRepository,
    SubscriptionView,
    VersionStatus,
    validate_skill_id,
    validate_version,
)

router = APIRouter(prefix="/api/teams/{team}/subscriptions", tags=["subscriptions"])

# One message for every reason a target cannot be subscribed to. Distinguishing "no such skill"
# from "that version is not published" would confirm the existence of skills the caller is not
# meant to be able to enumerate, and `403` would confirm it more loudly still.
_UNAVAILABLE = "No such published skill version is available to this team."


class SubscribeRequest(BaseModel):
    skill_id: str
    version: str = Field(description="Exact version. `latest` and ranges are refused by design.")


class RepinRequest(BaseModel):
    version: str


class SubscriptionResponse(BaseModel):
    skill_id: str
    owner: str = Field(description="Slug of the owning team.")
    description: str
    version: str = Field(description="The pinned version. Only this version is served.")
    latest_version: str | None
    update_available: bool = Field(description="Whether a newer version has been published.")
    lifecycle: SkillLifecycle = Field(description="The skill's status, not the subscription's.")
    origin: SubscriptionOrigin
    subscribed_at: datetime
    subscribed_by: str | None = Field(description="Prefix of the credential that subscribed.")
    updated_at: datetime | None
    updated_by: str | None


def _response(view: SubscriptionView) -> SubscriptionResponse:
    return SubscriptionResponse(
        skill_id=view.skill_id,
        owner=view.owner,
        description=view.description,
        version=view.version,
        latest_version=view.latest_version,
        update_available=view.update_available,
        lifecycle=view.lifecycle,
        origin=view.origin,
        subscribed_at=view.subscribed_at,
        subscribed_by=view.subscribed_by,
        updated_at=view.updated_at,
        updated_by=view.updated_by,
    )


async def _subscribable(session: DatabaseSession, skill_id: str, version: str) -> Skill:
    """Resolve a subscription target, or refuse with a `404` that says nothing about why."""
    try:
        validate_skill_id(skill_id)
        validate_version(version)
    except InvalidIdentifierError as exc:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_identifier", str(exc)) from exc

    skills = SkillRepository(session)
    skill = await skills.get_by_skill_id(skill_id)
    if skill is None or skill.lifecycle is SkillLifecycle.ARCHIVED:
        raise ApiError(status.HTTP_404_NOT_FOUND, "not_subscribable", _UNAVAILABLE)

    published = await skills.get_version(skill.id, version)
    if published is None or published.status is not VersionStatus.PUBLISHED:
        raise ApiError(status.HTTP_404_NOT_FOUND, "not_subscribable", _UNAVAILABLE)
    return skill


async def _view_or_500(
    session: DatabaseSession, environment_id: uuid.UUID, skill_id: str
) -> SubscriptionResponse:
    view = await CatalogRepository(session).get_subscription(environment_id, skill_id)
    if view is None:  # pragma: no cover - the row was written in this transaction
        raise ApiError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "subscription_missing",
            "The subscription was written but could not be read back.",
        )
    return _response(view)


@router.get(
    "",
    response_model=list[SubscriptionResponse],
    summary="The team's active subscriptions",
)
async def list_subscriptions(principal: TeamScoped, session: Session) -> list[SubscriptionResponse]:
    views = await CatalogRepository(session).list_subscriptions(principal.environment_id)
    return [_response(view) for view in views]


@router.post(
    "",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subscribe to one version of one skill",
    responses={
        404: {"model": ErrorResponse, "description": "No such published skill version."},
        409: {"model": ErrorResponse, "description": "Already subscribed."},
    },
)
async def subscribe(
    principal: TeamScoped, session: Session, request: SubscribeRequest
) -> SubscriptionResponse:
    skill = await _subscribable(session, request.skill_id, request.version)

    subscriptions = SubscriptionRepository(session)
    if await subscriptions.get(principal.environment_id, skill.id) is not None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "already_subscribed",
            f"Already subscribed to {request.skill_id}. Use PATCH to change the pinned version.",
        )

    await subscriptions.subscribe(
        principal.team_id,
        principal.environment_id,
        skill.id,
        request.version,
        actor=principal.api_key_prefix,
    )
    return await _view_or_500(session, principal.environment_id, request.skill_id)


@router.patch(
    "/{skill_id}",
    response_model=SubscriptionResponse,
    summary="Change the pinned version",
    responses={
        404: {
            "model": ErrorResponse,
            "description": "Not subscribed, or no such published version.",
        }
    },
)
async def repin(
    principal: TeamScoped, session: Session, skill_id: str, request: RepinRequest
) -> SubscriptionResponse:
    skill = await _subscribable(session, skill_id, request.version)

    subscriptions = SubscriptionRepository(session)
    subscription = await subscriptions.get(principal.environment_id, skill.id)
    if subscription is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "not_subscribed",
            f"This team is not subscribed to {skill_id}.",
        )

    await subscriptions.repin(subscription, request.version, actor=principal.api_key_prefix)
    return await _view_or_500(session, principal.environment_id, skill_id)


@router.delete(
    "/{skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unsubscribe",
)
async def unsubscribe(principal: TeamScoped, session: Session, skill_id: str) -> Response:
    """Idempotent: unsubscribing from something this team is not subscribed to is a success.

    A `404` here would make retrying a failed request indistinguishable from a bug.
    """
    try:
        validate_skill_id(skill_id)
    except InvalidIdentifierError as exc:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_identifier", str(exc)) from exc

    skill = await SkillRepository(session).get_by_skill_id(skill_id)
    if skill is not None:
        await SubscriptionRepository(session).unsubscribe(
            principal.environment_id, skill.id, actor=principal.api_key_prefix
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
