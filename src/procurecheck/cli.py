"""Command-line entry point.

Runs a completeness check without starting the API, so that the baseline model
interaction can be demonstrated and evaluated from a terminal.

Usage:
    python -m procurecheck.cli check --checklist FILE --submission FILE
    python -m procurecheck.cli health
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .config import STRATEGY_BATCH, STRATEGY_PER_ITEM, Settings
from .engine import ContextOverflowError, MatchingEngine
from .ingestion import (
    EmptyChecklistError,
    EmptyDocumentError,
    UnsupportedDocumentError,
    parse_checklist,
    parse_submission,
)
from .llm import ModelUnavailableError, OllamaClient
from .report import to_csv, to_json, to_text

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_BACKEND_ERROR = 2
EXIT_REFUSED = 3


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="procurecheck",
        description=(
            "Check a tender submission against a published procurement "
            "checklist. Reports presence only; never scores, ranks, or "
            "recommends an award."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health", help="Check that the model backend is reachable")

    check = subparsers.add_parser("check", help="Run a completeness check")
    check.add_argument("--checklist", required=True, type=Path)
    check.add_argument("--submission", required=True, type=Path)
    check.add_argument("--instruction", default=None, help="Optional user instruction")
    check.add_argument(
        "--format", dest="output_format", choices=("text", "json", "csv"), default="text"
    )
    check.add_argument("--out", type=Path, default=None, help="Write the report to a file")
    check.add_argument(
        "--strategy", choices=(STRATEGY_PER_ITEM, STRATEGY_BATCH), default=None
    )
    return parser


def _run_health(settings: Settings) -> int:
    try:
        with OllamaClient(settings) as client:
            info = client.health()
    except ModelUnavailableError as exc:
        print(f"Model backend unavailable: {exc}", file=sys.stderr)
        return EXIT_BACKEND_ERROR
    print(f"Backend : {info['backend']}")
    print(f"Model   : {info['model']}")
    print(f"Installed: {', '.join(info['available_models'])}")
    return EXIT_OK


def _run_check(args: argparse.Namespace, settings: Settings) -> int:
    try:
        items = parse_checklist(args.checklist)
        parsed = parse_submission(args.submission)
    except (UnsupportedDocumentError, EmptyChecklistError, EmptyDocumentError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return EXIT_USER_ERROR

    if parsed.scanned_pages:
        print(
            f"Warning: pages {parsed.scanned_pages} contain almost no text and may "
            f"need OCR before they can be matched.",
            file=sys.stderr,
        )

    print(
        f"Checking {len(items)} checklist items against "
        f"{parsed.page_count} page(s) using {settings.model} "
        f"({settings.strategy})...",
        file=sys.stderr,
    )

    try:
        with OllamaClient(settings) as client:
            outcome = MatchingEngine(client, settings).analyse(
                items, parsed, args.instruction
            )
    except ModelUnavailableError as exc:
        print(f"Model backend unavailable: {exc}", file=sys.stderr)
        return EXIT_BACKEND_ERROR
    except ContextOverflowError as exc:
        print(f"Input too large: {exc}", file=sys.stderr)
        return EXIT_USER_ERROR

    if outcome.refused:
        print(outcome.refusal.reason)
        return EXIT_REFUSED

    report = outcome.report
    assert report is not None
    renderers = {"text": to_text, "json": to_json, "csv": to_csv}
    rendered = renderers[args.output_format](report, settings.model)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
        print(f"Report written to {args.out}", file=sys.stderr)
    else:
        print(rendered)
    return EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return EXIT_USER_ERROR

    if args.command == "health":
        return _run_health(settings)

    if getattr(args, "strategy", None):
        settings = Settings(
            **{**settings.__dict__, "strategy": args.strategy}
        )
    return _run_check(args, settings)


if __name__ == "__main__":
    raise SystemExit(main())
