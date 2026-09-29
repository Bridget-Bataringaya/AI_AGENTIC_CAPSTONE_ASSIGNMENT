"""The `workflow` command.

    python run.py workflow --submission FILE [--checklist FILE|standard]

Runs the multi-step workflow on one submission and writes the full trace, one
record per Sense, Plan, Act and Observe iteration, to evidence/traces/workflow/.
As with `agent`, the command line is a local, trusted entry point and the role
comes from --role.
"""

from __future__ import annotations

import argparse
import getpass
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Final

from .. import __version__, checklists
from ..checklists import REPO_ROOT
from ..config import Settings
from ..ingestion import (
    EmptyChecklistError,
    EmptyDocumentError,
    UnsupportedDocumentError,
    parse_checklist,
    parse_submission,
)
from ..llm import OllamaClient
from ..tools.authorization import ROLE_PERMISSIONS, ROLE_PROCUREMENT_OFFICER, Principal
from ..tools.completeness import ToolContext
from ..tools.registry import ToolExecutor, default_registry
from ..tools.tickets import ReviewQueue
from .limits import (
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_MAX_RECHECK_ROUNDS,
    DEFAULT_MAX_SERVICE_RETRIES,
    DEFAULT_RETRY_DELAY_SECONDS,
    StopReason,
    WorkflowLimits,
)
from .runner import WorkflowRun, WorkflowRunner
from .state import WorkflowInput

TRACE_DIR: Final[Path] = REPO_ROOT / "evidence" / "traces" / "workflow"
DEFAULT_DOCUMENT_TYPE: Final[str] = "Bid Document"

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_BACKEND_ERROR = 2


def add_parsers(subparsers: argparse._SubParsersAction) -> None:
    workflow = subparsers.add_parser(
        "workflow", help="Run the multi-step completeness workflow on one submission"
    )
    workflow.add_argument("--submission", required=True, type=Path)
    workflow.add_argument("--checklist", default=checklists.STANDARD)
    workflow.add_argument("--document-type", default=DEFAULT_DOCUMENT_TYPE)
    workflow.add_argument(
        "--role", default=ROLE_PROCUREMENT_OFFICER, choices=sorted(ROLE_PERMISSIONS),
        help="The caller's role, which decides which tools may run",
    )
    workflow.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS)
    workflow.add_argument("--max-retries", type=int, default=DEFAULT_MAX_SERVICE_RETRIES,
                          help="Retries of a step after the model backend is unavailable")
    workflow.add_argument("--max-rechecks", type=int, default=DEFAULT_MAX_RECHECK_ROUNDS,
                          help="Rounds of re-checking items that came back Unclear")
    workflow.add_argument("--retry-delay", type=float, default=DEFAULT_RETRY_DELAY_SECONDS,
                          help="Seconds to wait before a retry")
    workflow.add_argument("--trace", type=Path, default=None, help="Where to write the run trace")


def _trace_path(submission: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", submission.stem.lower()).strip("-")[:48]
    return TRACE_DIR / f"{stamp}-{slug}.json"


def _print_run(run: WorkflowRun) -> None:
    for step in run.steps:
        outcomes = ", ".join(
            "success" if r.ok else f"error {r.error.error_code.value}" for r in step.results
        )
        seconds = sum(r.duration_ms for r in step.results) / 1000
        print(f"[iteration {step.iteration}] {step.decision.action.value}: {outcomes} ({seconds:.0f}s)",
              file=sys.stderr)
        print(f"             {step.decision.reason}", file=sys.stderr)
    print(f"Stopped: {run.stop_reason.value}. {run.stop_detail}")
    if run.report is not None:
        print(json.dumps(run.report.model_dump(mode="json"), indent=2))
    print(f"\nHand-off to {run.handoff.to}: {run.handoff.reason}")
    for action in run.handoff.actions:
        print(f"  - {action}")


def run_workflow(args: argparse.Namespace, settings: Settings) -> int:
    try:
        limits = WorkflowLimits(
            max_iterations=args.max_iterations,
            max_service_retries=args.max_retries,
            max_recheck_rounds=args.max_rechecks,
            retry_delay_seconds=args.retry_delay,
        )
        checklist_path, _label, _is_template = checklists.resolve(args.checklist)
        items = parse_checklist(checklist_path)
        parsed = parse_submission(args.submission)
    except (ValueError, checklists.UnknownChecklistError, UnsupportedDocumentError,
            EmptyChecklistError, EmptyDocumentError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return EXIT_USER_ERROR

    workflow_input = WorkflowInput(
        submission_id=args.submission.stem,
        document_name=args.submission.name,
        document_type=args.document_type,
        document_text=parsed.as_marked_text(),
        required_items=tuple(item.description for item in items),
    )
    principal = Principal(user_id=getpass.getuser(), role=args.role)
    print(
        f"ProcureCheck {__version__} workflow on {args.submission.name}: {len(items)} checklist items, "
        f"{parsed.page_count} page(s), role {args.role}, model {settings.model}.",
        file=sys.stderr,
    )

    with OllamaClient(settings) as client:
        context = ToolContext(settings, client, review_queue=ReviewQueue())
        runner = WorkflowRunner(ToolExecutor(default_registry(), context), limits)
        started = datetime.now()
        run = runner.run(workflow_input, principal)
        seconds = (datetime.now() - started).total_seconds()

    destination = args.trace or _trace_path(args.submission)
    destination.parent.mkdir(parents=True, exist_ok=True)
    trace = {
        "version": __version__,
        "run_at": started.isoformat(timespec="seconds"),
        "seconds": round(seconds, 1),
        "model": settings.model,
        "pipeline": settings.pipeline_label,
        "submission": args.submission.name,
        "checklist_items": len(items),
        **run.to_trace(),
    }
    destination.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Trace written to {destination}", file=sys.stderr)

    _print_run(run)
    if run.ok:
        return EXIT_OK
    if run.stop_reason is StopReason.SERVICE_UNAVAILABLE:
        return EXIT_BACKEND_ERROR
    return EXIT_USER_ERROR
