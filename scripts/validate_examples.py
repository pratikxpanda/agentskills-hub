"""Validate examples/skills/ with the SDK's own validator.

The Hub promises that a skill it stores is a plain SDK skill (ADR 0001). This checks that claim
against the real `agentskills-core` validator rather than a local reimplementation of it, which
would defeat the point.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from agentskills_core import SkillRegistry, validate_skill
from agentskills_fs import LocalFileSystemSkillProvider

SKILLS_ROOT = Path(__file__).resolve().parent.parent / "examples" / "skills"


async def main() -> int:
    if not SKILLS_ROOT.is_dir():
        print(f"No skills directory at {SKILLS_ROOT}", file=sys.stderr)
        return 1

    skill_ids = sorted(p.name for p in SKILLS_ROOT.iterdir() if (p / "SKILL.md").is_file())
    if not skill_ids:
        print(f"No skills found under {SKILLS_ROOT}", file=sys.stderr)
        return 1

    provider = LocalFileSystemSkillProvider(SKILLS_ROOT)
    registry = SkillRegistry()
    await registry.register([(skill_id, provider) for skill_id in skill_ids])

    failed = False
    for skill in registry.list_skills():
        errors = await validate_skill(skill)
        if errors:
            failed = True
            print(f"FAIL {skill.get_id()}", file=sys.stderr)
            for error in errors:
                print(f"  {error}", file=sys.stderr)
        else:
            print(f"ok   {skill.get_id()}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
