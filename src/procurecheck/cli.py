"""Command-line entry point.

Runs a completeness check without starting the API, so that the baseline model
interaction can be demonstrated and evaluated from a terminal.

Usage:
    python -m procurecheck.cli check --submission FILE [--checklist FILE|standard]
    python -m procurecheck.cli health
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import checklists
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

# Where reports land when the caller does not choose a path. Named after
# the submission so that checking a second document cannot silently
# overwrite the first one's report.
REPORTS_DIR = Path("evidence") / "reports"
EXTENSIONS = {"text": ".txt", "json": ".json", "csv": ".csv", "pdf": ".pdf"}

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
    check.add_argument(
        "--checklist",
        default=checklists.STANDARD,
        help=(
            "Path to a checklist file, or the name of a bundled one "
            f"({', '.join(checklists.bundled_names())}). Defaults to "
            f"{checklists.STANDARD!r}, so a new document can be checked without "
            "writing a checklist first."
        ),
    )
    check.add_argument("--submission", required=True, type=Path)
    check.add_argument("--instruction", default=None, help="Optional user instruction")
    check.add_argument(
        "--format",
        dest="output_format",
        choices=("text", "json", "csv", "pdf"),
        default="text",
        help="pdf produces a readable report for a non-technical reader",
    )
    check.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Where to write the report. Defaults to "
            "evidence/reports/<submission>-completeness-report.<ext>; "
            "text output goes to the terminal unless this is given."
        ),
    )
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


def _default_report_path(submission: Path, output_format: str) -> Path:
    """Build evidence/reports/<submission>-completeness-report.<ext>.

    Naming the report after its submission means checking a second document
    cannot quietly replace the first document's report, which matters when the
    reports are the evidence for a task.
    """
    suffix = EXTENSIONS.get(output_format, ".txt")
    return REPORTS_DIR / f"{submission.stem}-completeness-report{suffix}"


def _run_check(args: argparse.Namespace, settings: Settings) -> int:
    try:
        checklist_path, checklist_label, is_template = checklists.resolve(args.checklist)
        items = parse_checklist(checklist_path)
        parsed = parse_submission(args.submission)
    except (
        checklists.UnknownChecklistError,
        UnsupportedDocumentError,
        EmptyChecklistError,
        EmptyDocumentError,
    ) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return EXIT_USER_ERROR

    if is_template:
        print(f"Using {checklist_label}. {checklists.TEMPLATE_CAVEAT}", file=sys.stderr)

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

    if args.output_format == "pdf":
        destination = args.out or _default_report_path(args.submission, "pdf")
        from .report_pdf import write_check_pdf

        destination.parent.mkdir(parents=True, exist_ok=True)
        write_check_pdf(
            report,
            settings.model,
            parsed.page_count,
            destination,
            checklist_label=checklist_label,
            caveat=checklists.TEMPLATE_CAVEAT if is_template else "",
        )
        print(f"Report written to {destination}", file=sys.stderr)
        # Still show the findings in the terminal, so the run is not silent.
        print(to_text(report, settings.model))
        return EXIT_OK

    renderers = {"text": to_text, "json": to_json, "csv": to_csv}
    rendered = renderers[args.output_format](report, settings.model)

    # Text is the interactive format and goes to the terminal unless a path is
    # asked for. Machine formats are always written to a file, named after the
    # submission, because that is what a caller wants to keep.
    destination = args.out
    if destination is None and args.output_format != "text":
        destination = _default_report_path(args.submission, args.output_format)

    if destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
        print(f"Report written to {destination}", file=sys.stderr)
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
