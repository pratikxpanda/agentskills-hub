"""Apply .github/labels.yml to the repository via the GitHub CLI.

Labels edited in the web UI drift from the ones the specs reference within a week, so the file is
the source of truth. Existing labels are updated; labels not listed here are left alone.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

LABELS_FILE = Path(__file__).resolve().parent.parent / ".github" / "labels.yml"


def main() -> int:
    labels = yaml.safe_load(LABELS_FILE.read_text(encoding="utf-8"))
    repo = os.environ.get("GITHUB_REPOSITORY", "")

    failed = False
    for label in labels:
        command = [
            "gh",
            "label",
            "create",
            label["name"],
            "--color",
            label["color"],
            "--description",
            label.get("description", ""),
            "--force",
        ]
        if repo:
            command += ["--repo", repo]

        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"ok   {label['name']}")
        else:
            failed = True
            print(f"FAIL {label['name']}: {result.stderr.strip()}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
