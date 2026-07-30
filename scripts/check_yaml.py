"""Check that every YAML file in the repository parses.

Workflows, issue forms, and the label set are only ever exercised by GitHub, so a syntax error
otherwise surfaces as a feature silently not working rather than as a failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "node_modules", ".local"}


def yaml_files() -> list[Path]:
    return sorted(
        path
        for pattern in ("*.yml", "*.yaml")
        for path in REPO_ROOT.rglob(pattern)
        if not SKIP_DIRS.intersection(path.relative_to(REPO_ROOT).parts)
    )


def main() -> int:
    paths = yaml_files()
    failures: list[str] = []
    for path in paths:
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            failures.append(f"{path.relative_to(REPO_ROOT)}: {exc}")

    if failures:
        print(f"{len(failures)} YAML file(s) failed to parse:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print(f"All {len(paths)} YAML files parse.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
