"""Single entry point for the whole project.

Put `src` on the import path itself, so nothing has to be set up beforehand.
Works identically in PowerShell, CMD, bash and Git Bash:

    python run.py health
    python run.py check --checklist FILE --submission FILE
    python run.py evaluate
    python run.py evaluate --no-model
    python run.py test

There is deliberately no PYTHONPATH to set and no package to install. Earlier
instructions asked the team to export PYTHONPATH, which silently fails in
PowerShell because `NAME=value command` is bash-only syntax. This file removes
that whole class of mistake.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SRC = REPO_ROOT / "src"
EVALUATION_DIR = REPO_ROOT / "tests" / "evaluation"

USAGE = """\
Public Procurement Document-Completeness Agent

Usage:
  python run.py health                        Check the model backend is reachable
  python run.py verify [--quick]              Self-check that the system works
  python run.py check --checklist F --submission F [options]
                                              Run a completeness check
  python run.py evaluate [--no-model]         Run the prompt evaluation cases
  python run.py test                          Run the unit test suite
  python run.py api                           Start the FastAPI server

Pass --help after check for its full options, e.g.
  python run.py check --help
"""


def _bootstrap() -> None:
    """Make `import procurecheck` work regardless of how python was invoked."""
    if not SRC.is_dir():
        raise SystemExit(
            f"Cannot find {SRC}. Run this from inside the repository, and make "
            f"sure you are on a branch that contains the source code."
        )
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))


def _run_evaluate(argv: list[str]) -> int:
    """Run the evaluation as a subprocess so its own sys.path setup applies."""
    script = EVALUATION_DIR / "run_evaluation.py"
    if not script.is_file():
        raise SystemExit(f"Cannot find {script}.")
    return subprocess.call([sys.executable, str(script), *argv])


def _run_tests(argv: list[str]) -> int:
    return subprocess.call(
        [sys.executable, "-m", "pytest", str(REPO_ROOT / "tests"), "-q", *argv],
        cwd=str(REPO_ROOT),
    )


def _run_api(argv: list[str]) -> int:
    _bootstrap()
    return subprocess.call(
        [sys.executable, "-m", "uvicorn", "procurecheck.api:app", *argv],
        cwd=str(REPO_ROOT),
        env={**_env_with_src()},
    )


def _env_with_src() -> dict:
    import os

    existing = os.environ.get("PYTHONPATH", "")
    joined = str(SRC) + (os.pathsep + existing if existing else "")
    return {**os.environ, "PYTHONPATH": joined}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0

    command, rest = args[0], args[1:]

    if command == "evaluate":
        return _run_evaluate(rest)
    if command == "test":
        return _run_tests(rest)
    if command == "api":
        return _run_api(rest)
    if command in ("health", "check", "verify"):
        _bootstrap()
        from procurecheck.cli import main as cli_main

        return cli_main([command, *rest])

    print(f"Unknown command {command!r}.\n", file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
