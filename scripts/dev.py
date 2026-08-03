#!/usr/bin/env python3
"""Development task runner for the Agent Skills Hub.

Usage:
    python scripts/dev.py check       # Format check + lint + typecheck + import contracts
    python scripts/dev.py test        # Run the test suite
    python scripts/dev.py all         # Format + lint + test

Run `python scripts/dev.py` with no arguments for the full task list.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES_DIR = ROOT / "packages"

# Use sys.executable -m so tools resolve from the active venv.
_PY = sys.executable


def _run(cmd: list[str], *, check: bool = True) -> int:
    print(f"\n{'=' * 60}")
    print(f"  {' '.join(cmd)}")
    print(f"{'=' * 60}\n")
    result = subprocess.run(cmd, cwd=ROOT, check=False)
    if check and result.returncode != 0:
        sys.exit(result.returncode)
    return result.returncode


# conftest.py sits at the root so that mypy sees exactly one module named `conftest`.
# `examples/` is linted but not type-checked: its imports are optional agent frameworks that the
# Hub does not depend on, and installing them to satisfy mypy would be the tail wagging the dog.
_SOURCES = ["packages/", "scripts/", "tests/", "examples/", "conftest.py"]


def lint() -> None:
    """Run ruff linter (check only, no fixes)."""
    _run([_PY, "-m", "ruff", "check", *_SOURCES])


def lint_fix() -> None:
    """Run ruff linter with auto-fix."""
    _run([_PY, "-m", "ruff", "check", "--fix", *_SOURCES])


def fmt() -> None:
    """Auto-format code with ruff."""
    _run([_PY, "-m", "ruff", "format", *_SOURCES])
    lint_fix()


def fmt_check() -> None:
    """Check formatting without changing files."""
    _run([_PY, "-m", "ruff", "format", "--check", *_SOURCES])


def typecheck() -> None:
    """Run mypy type checking."""
    _run([_PY, "-m", "mypy"])


def imports() -> None:
    """Verify the layering contracts between packages."""
    # `python -m importlinter.cli` exits 0 without running anything; use the console script.
    _run([str(Path(_PY).parent / "lint-imports")])


def docs() -> None:
    """Check relative markdown links and YAML syntax."""
    _run([_PY, "scripts/check_links.py"])
    _run([_PY, "scripts/check_yaml.py"])


def examples() -> None:
    """Validate the example skills against the SDK's own validator."""
    _run([_PY, "scripts/validate_examples.py"])


def seed() -> None:
    """Populate a demo organization, teams, skills, and API keys. Idempotent."""
    _run([_PY, "scripts/seed.py", *sys.argv[2:]])


def e2e() -> None:
    """End to end: seed, publish, subscribe, connect over MCP. No model involved."""
    # Outside `test` on purpose: `testpaths` is `packages`, and this is slow enough that it
    # should not sit in the loop a change to one package runs.
    _run([_PY, "-m", "pytest", "tests/", "-v"])


def _npm(*args: str) -> None:
    npm = shutil.which("npm")
    if npm is None:
        print("npm is not on PATH; skipping. The Python checks do not need it.")
        sys.exit(1)
    print(f"\n{'=' * 60}")
    print(f"  npm {' '.join(args)}  (in web/)")
    print(f"{'=' * 60}\n")
    result = subprocess.run([npm, *args], cwd=ROOT / "web", check=False)
    if result.returncode != 0:
        sys.exit(result.returncode)


def web_install() -> None:
    """Install the UI's dependencies from the lockfile."""
    _npm("ci")


def web_check() -> None:
    """Lint, typecheck, and test the UI."""
    _npm("run", "lint")
    _npm("run", "test")
    _npm("run", "build")


def web_dev() -> None:
    """Serve the UI, proxying /api and /mcp to a Hub on port 8000."""
    _npm("run", "dev")


def migrate() -> None:
    """Upgrade the database to the latest migration."""
    _run([str(Path(_PY).parent / "alembic"), "upgrade", "head"])


def migrate_down() -> None:
    """Roll the database back one migration."""
    _run([str(Path(_PY).parent / "alembic"), "downgrade", "-1"])


def migration() -> None:
    """Autogenerate a migration: dev.py migration "message"."""
    if len(sys.argv) < 3:
        print('Usage: dev.py migration "describe the change"')
        sys.exit(1)
    _run([str(Path(_PY).parent / "alembic"), "revision", "--autogenerate", "-m", sys.argv[2]])


def check() -> None:
    """Run every check without modifying files."""
    fmt_check()
    lint()
    typecheck()
    imports()
    docs()


def test() -> None:
    """Run the test suite."""
    _run([_PY, "-m", "pytest", "packages/", "-v"])


def test_cov() -> None:
    """Run tests with a coverage report."""
    _run([_PY, "-m", "pytest", "packages/", "-v", "--cov=packages", "--cov-report=term-missing"])


def clean() -> None:
    """Remove all cache and build artifacts."""
    patterns = [
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "*.egg-info",
        "dist",
        "build",
        "htmlcov",
    ]
    removed = 0
    root_venv = ROOT / ".venv"

    for pattern in patterns:
        for path in ROOT.rglob(pattern):
            if root_venv in (path, *path.parents):
                continue
            if path.is_dir():
                shutil.rmtree(path)
                print(f"  Removed {path.relative_to(ROOT)}")
                removed += 1
            elif path.is_file():
                path.unlink()
                print(f"  Removed {path.relative_to(ROOT)}")
                removed += 1

    cov_file = ROOT / ".coverage"
    if cov_file.exists():
        cov_file.unlink()
        print("  Removed .coverage")
        removed += 1

    # Stray .venv directories under packages/, created by poetry build.
    for venv_path in PACKAGES_DIR.rglob(".venv"):
        if venv_path.is_dir():
            shutil.rmtree(venv_path)
            print(f"  Removed {venv_path.relative_to(ROOT)}")
            removed += 1

    print(f"\n  Cleaned {removed} item(s)." if removed else "  Nothing to clean.")


def all_tasks() -> None:
    """Run format + lint + test."""
    fmt()
    lint()
    test()


TASKS = {
    "lint": lint,
    "lint:fix": lint_fix,
    "format": fmt,
    "fmt": fmt,
    "format:check": fmt_check,
    "typecheck": typecheck,
    "imports": imports,
    "docs": docs,
    "examples": examples,
    "seed": seed,
    "e2e": e2e,
    "web": web_check,
    "web:install": web_install,
    "web:dev": web_dev,
    "migrate": migrate,
    "migrate:down": migrate_down,
    "migration": migration,
    "check": check,
    "test": test,
    "test:cov": test_cov,
    "clean": clean,
    "all": all_tasks,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        print("Available tasks:")
        for name, fn in TASKS.items():
            print(f"  {name:16s} {fn.__doc__ or ''}")
        sys.exit(0)

    task_name = sys.argv[1]
    task = TASKS.get(task_name)
    if task is None:
        print(f"Unknown task: {task_name}")
        print(f"Available: {', '.join(TASKS.keys())}")
        sys.exit(1)

    task()


if __name__ == "__main__":
    main()
