"""The `tools` and `agent` commands.

    python run.py tools                          list the tools and their contracts
    python run.py agent --submission FILE        let the model drive the tools

`agent` reads the submission and checklist, holds them in the session, and
lets the model choose which tool to call. Every call it proposes is run by the
executor, and the whole run is written to evidence/traces/tools/ so the
sequence of calls, arguments and results can be inspected afterwards.

The command line is a local, trusted entry point: the operator is the caller,
so the role is taken from --role (default: procurement_officer). Passing
--role bidder is the quickest way to watch the authorization check refuse.
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

from .. import checklists
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
from .authorization import ROLE_PERMISSIONS, ROLE_PROCUREMENT_OFFICER, Principal
from .completeness import ToolContext
from .contracts import ErrorCode
from .orchestrator import DEFAULT_MAX_TURNS, AgentRun, AgentSession, ToolCallingAgent
from .registry import ToolExecutor, default_registry

TRACE_DIR: Final[Path] = REPO_ROOT / "evidence" / "traces" / "tools"
DEFAULT_REQUEST: Final[str] = "Check this document for completeness and give me the report."

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_BACKEND_ERROR = 2
EXIT_REFUSED = 3


def add_parsers(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser("tools", help="List the agent's tools and their contracts")

    agent = subparsers.add_parser("agent", help="Let the model call the tools on one submission")
    agent.add_argument("--submission", required=True, type=Path)
    agent.add_argument("--checklist", default=checklists.STANDARD)
    agent.add_argument("--request", default=DEFAULT_REQUEST, help="What to ask the agent")
    agent.add_argument(
        "--role", default=ROLE_PROCUREMENT_OFFICER, choices=sorted(ROLE_PERMISSIONS),
        help="The caller's role, which decides which tools may run",
    )
    agent.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    agent.add_argument("--trace", type=Path, default=None, help="Where to write the run trace")


def run_tools() -> int:
    described = [spec.describe() for spec in default_registry().specs.values()]
    print(json.dumps(described, indent=2))
    return EXIT_OK


def _trace_path(submission: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", submission.stem.lower()).strip("-")[:48]
    return TRACE_DIR / f"{stamp}-{slug}.json"


def _print_run(run: AgentRun) -> None:
    for number, result in enumerate(run.tool_results, start=1):
        outcome = "success" if result.ok else f"error {result.error.error_code.value}"
        print(f"[call {number}] {result.tool}: {outcome} ({result.duration_ms / 1000:.0f}s)", file=sys.stderr)
        if not result.ok:
            print(f"          {result.error.message}", file=sys.stderr)
    if run.discarded_arguments:
        print(f"Ignored model-supplied arguments: {', '.join(run.discarded_arguments)}", file=sys.stderr)
    if run.error is not None:
        print(f"Run ended: {run.error.error_code.value}: {run.error.message}")
    if run.report is not None:
        print(json.dumps(run.report.model_dump(mode="json"), indent=2))
    if run.final_message:
        print(f"\nAgent: {run.final_message}")


def run_agent(args: argparse.Namespace, settings: Settings) -> int:
    try:
        checklist_path, _label, _is_template = checklists.resolve(args.checklist)
        items = parse_checklist(checklist_path)
        parsed = parse_submission(args.submission)
    except (checklists.UnknownChecklistError, UnsupportedDocumentError,
            EmptyChecklistError, EmptyDocumentError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return EXIT_USER_ERROR

    session = AgentSession(
        document_name=args.submission.name,
        document_text=parsed.as_marked_text(),
        required_items=tuple(item.description for item in items),
    )
    principal = Principal(user_id=getpass.getuser(), role=args.role)
    print(
        f"Agent run on {args.submission.name}: {len(items)} checklist items, "
        f"{parsed.page_count} page(s), role {args.role}, model {settings.model}.",
        file=sys.stderr,
    )

    with OllamaClient(settings) as client:
        executor = ToolExecutor(default_registry(), ToolContext(settings, client))
        agent = ToolCallingAgent(client, executor, max_turns=args.max_turns)
        started = datetime.now()
        run = agent.run(args.request, principal, session)
        seconds = (datetime.now() - started).total_seconds()

    destination = args.trace or _trace_path(args.submission)
    destination.parent.mkdir(parents=True, exist_ok=True)
    trace = {
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
    if run.error is None:
        return EXIT_OK
    if run.error.error_code is ErrorCode.REFUSED:
        return EXIT_REFUSED
    if run.error.error_code is ErrorCode.SERVICE_UNAVAILABLE:
        return EXIT_BACKEND_ERROR
    return EXIT_USER_ERROR
