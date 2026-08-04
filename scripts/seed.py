"""Seed a Hub with a working demo, from `examples/seed.yaml`.

Two things this deliberately does not do. It does not go through the HTTP API: minting an API key
has no endpoint, and scope, visibility, and subscription model are not settable over `POST
/api/skills`, so a seeder built on the API could only produce a subset of the demo. It is an
administrative operation and it talks to the core directly.

And it does not invent content. Every skill is packed from `examples/skills/` and handed to the
same store the publish endpoint uses, so the SDK's validator sees it on the way in exactly as it
would see an upload.

Re-running is safe. Teams, skills, versions, and subscriptions are all created only if absent.
API keys are the exception worth knowing about: only their hash is stored, so an existing token
cannot be printed a second time. Pass `--rotate` to issue a new one.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
import tarfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from sqlmodel import col, select

from agentskills_hub_core import (
    ApiKey,
    ApiKeyRepository,
    LocalFileSystemSkillStore,
    SkillLifecycle,
    SkillRepository,
    SkillScope,
    SubscriptionModel,
    SubscriptionOrigin,
    SubscriptionRepository,
    TeamRepository,
    Visibility,
    create_engine,
    create_session_factory,
    normalise_tags,
    session_scope,
)
from agentskills_hub_core.database import DEFAULT_DATABASE_URL
from agentskills_hub_core.schema import upgrade_to_head

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "examples" / "seed.yaml"

DEFAULT_STORE_ROOT = "./store"
DEFAULT_PUBLIC_URL = "http://127.0.0.1:8000"


@dataclass(frozen=True)
class SeededTeam:
    slug: str
    name: str
    team_id: uuid.UUID
    environment_id: uuid.UUID
    token: str | None
    """None when the team already had a key: the stored hash cannot be turned back into a token."""


@dataclass
class SeedResult:
    database_url: str
    store_root: Path
    teams: dict[str, SeededTeam] = field(default_factory=dict)
    published: list[tuple[str, str]] = field(default_factory=list)
    subscribed: list[tuple[str, str, str]] = field(default_factory=list)

    def token(self, slug: str) -> str:
        token = self.teams[slug].token
        if token is None:
            raise RuntimeError(f"{slug} already had an API key; seed with rotate=True for a token.")
        return token


def pack(directory: Path) -> bytes:
    """A tar.gz shaped exactly like an upload: one top-level folder named for the skill."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path in sorted(p for p in directory.rglob("*") if p.is_file()):
            archive.add(path, arcname=f"{directory.name}/{path.relative_to(directory).as_posix()}")
    return buffer.getvalue()


async def _team(session: Any, slug: str, name: str, *, rotate: bool) -> SeededTeam:
    teams = TeamRepository(session)
    team = await teams.get_by_slug(slug)
    if team is None:
        team, environment = await teams.create(slug, name)
    else:
        default = await teams.default_environment(team.id)
        if default is None:  # pragma: no cover - a team is never created without one
            raise RuntimeError(f"{slug} has no default environment.")
        environment = default

    keys = ApiKeyRepository(session)
    live = (
        await session.exec(
            select(ApiKey).where(col(ApiKey.team_id) == team.id, col(ApiKey.revoked_at).is_(None))
        )
    ).first()

    token: str | None = None
    if live is None or rotate:
        _, token = await keys.issue(team.id, environment.id)

    return SeededTeam(slug, name, team.id, environment.id, token)


async def _skill(
    session: Any, store: LocalFileSystemSkillStore, entry: dict[str, Any], owner: SeededTeam
) -> bool:
    skills = SkillRepository(session)
    skill_id, version = str(entry["skill_id"]), str(entry["version"])

    existing = await skills.get_by_skill_id(skill_id)
    if existing is not None and await skills.get_version(existing.id, version) is not None:
        return False

    source = (MANIFEST.parent / str(entry["source"])).resolve()
    if not (source / "SKILL.md").is_file():
        raise FileNotFoundError(f"{source} has no SKILL.md")

    published = await store.publish(skill_id, version, io.BytesIO(pack(source)))

    if existing is None:
        existing = await skills.create(
            skill_id,
            owner.team_id,
            scope=SkillScope(entry.get("scope", "org")),
            visibility=Visibility(entry.get("visibility", "listed")),
            subscription_model=SubscriptionModel(entry.get("subscription_model", "open")),
            lifecycle=SkillLifecycle(entry.get("lifecycle", "active")),
            tags=normalise_tags([str(tag) for tag in entry.get("tags", [])]),
        )

    await skills.add_version(
        existing, version, published.description, published.digest, published_by=owner.slug
    )
    return True


async def seed(
    *,
    manifest: Path = MANIFEST,
    database_url: str | None = None,
    store_root: str | Path | None = None,
    rotate: bool = False,
    migrate: bool = True,
) -> SeedResult:
    database_url = database_url or os.environ.get("HUB_DATABASE_URL", DEFAULT_DATABASE_URL)
    store_root = Path(store_root or os.environ.get("HUB_STORE_ROOT", DEFAULT_STORE_ROOT))

    if migrate:
        # env.py drives an async engine through asyncio.run, so this cannot run on the event loop.
        await asyncio.to_thread(upgrade_to_head, database_url)

    document = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    result = SeedResult(database_url=database_url, store_root=store_root)
    store = LocalFileSystemSkillStore(store_root)

    engine = create_engine(database_url)
    try:
        factory = create_session_factory(engine)
        async with session_scope(factory) as session:
            for entry in document.get("teams", []):
                team = await _team(session, entry["slug"], entry["name"], rotate=rotate)
                result.teams[team.slug] = team

            for entry in document.get("skills", []):
                owner = result.teams[str(entry["owner"])]
                if await _skill(session, store, entry, owner):
                    result.published.append((str(entry["skill_id"]), str(entry["version"])))

            subscriptions = SubscriptionRepository(session)
            skills = SkillRepository(session)
            for entry in document.get("subscriptions", []):
                team = result.teams[str(entry["team"])]
                skill = await skills.get_by_skill_id(str(entry["skill"]))
                if skill is None:
                    raise KeyError(f"subscription names an unpublished skill: {entry['skill']}")
                if await subscriptions.get(team.environment_id, skill.id) is not None:
                    continue
                await subscriptions.subscribe(
                    team.team_id,
                    team.environment_id,
                    skill.id,
                    str(entry["version"]),
                    actor=team.slug,
                    origin=SubscriptionOrigin.POLICY,
                )
                result.subscribed.append((team.slug, str(entry["skill"]), str(entry["version"])))
    finally:
        await engine.dispose()

    return result


def report(result: SeedResult, public_url: str) -> None:
    print(f"\nDatabase   {result.database_url}")
    print(f"Store      {result.store_root}")

    if result.published:
        print("\nPublished")
        for skill_id, version in result.published:
            print(f"  {skill_id} {version}")
    else:
        print("\nPublished  nothing new; every version in the manifest was already stored.")

    for slug, skill_id, version in result.subscribed:
        print(f"Subscribed {slug} -> {skill_id} {version}")

    print("\nTeams")
    for team in result.teams.values():
        print(f"\n  {team.name} ({team.slug})")
        print(f"    MCP endpoint  {public_url.rstrip('/')}/mcp/{team.slug}")
        if team.token is None:
            print("    API key       kept (only its hash is stored; --rotate issues a new one)")
        else:
            print(f"    API key       {team.token}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--store-root", default=None)
    parser.add_argument(
        "--rotate", action="store_true", help="Issue a new API key even if the team has one."
    )
    parser.add_argument("--no-migrate", action="store_true", help="Assume the schema is current.")
    parser.add_argument(
        "--public-url", default=os.environ.get("HUB_PUBLIC_URL", DEFAULT_PUBLIC_URL)
    )
    args = parser.parse_args()

    result = asyncio.run(
        seed(
            manifest=args.manifest,
            database_url=args.database_url,
            store_root=args.store_root,
            rotate=args.rotate,
            migrate=not args.no_migrate,
        )
    )
    report(result, args.public_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
