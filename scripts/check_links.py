"""Check that every relative markdown link in the repository resolves to a real path.

Counting `../` by eye is unreliable, and a docs-only repository has nothing else to break.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
EXTERNAL = re.compile(r"^(https?:|mailto:|#)")
SKIP_DIRS = {".git", ".venv", "node_modules", ".local"}


def markdown_files() -> list[Path]:
    return sorted(
        path
        for path in REPO_ROOT.rglob("*.md")
        if not SKIP_DIRS.intersection(path.relative_to(REPO_ROOT).parts)
    )


def broken_links(path: Path) -> list[str]:
    failures: list[str] = []
    for match in LINK.finditer(path.read_text(encoding="utf-8")):
        target = match.group(1).strip()
        if EXTERNAL.match(target):
            continue
        relative = target.split("#", 1)[0]
        if not relative:
            continue
        if not (path.parent / relative).exists():
            failures.append(f"{path.relative_to(REPO_ROOT)} -> {target}")
    return failures


def main() -> int:
    failures = [failure for path in markdown_files() for failure in broken_links(path)]
    if failures:
        print(f"{len(failures)} broken relative link(s):", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print(f"All relative links resolve across {len(markdown_files())} markdown files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
