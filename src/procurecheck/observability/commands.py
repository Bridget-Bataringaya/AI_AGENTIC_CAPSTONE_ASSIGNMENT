"""The `logs` command: read the run logs back.

    python run.py logs list [--last N]
    python run.py logs show RUN|latest
    python run.py logs summary [--last N]

`list` gives one line per run. `show` prints one run event by event. `summary`
adds runs together: how they ended, how long the model took, how often it
failed, which tool errors occurred and which calls were slowest.

A log names the submissions checked and who checked them, so reading one needs
run_logs:read, which only a procurement officer holds.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..config import Settings
from ..tools.authorization import (
    PERMISSION_LOGS_READ,
    ROLE_PERMISSIONS,
    ROLE_PROCUREMENT_OFFICER,
    Principal,
)
from .recorder import (
    DECISION,
    ITEM_OUTCOME,
    LOG_SUFFIX,
    MODEL_CALL,
    MODEL_OUTPUT,
    RETRIEVAL,
    RUN_FINISHED,
    RUN_STARTED,
    STATUS_ERROR,
    TOOL_CALL,
    resolve_log_dir,
)

EXIT_OK = 0
EXIT_USER_ERROR = 1

DEFAULT_LAST = 20
SLOWEST_SHOWN = 5
LATEST = "latest"


@dataclass(frozen=True)
class RunLog:
    path: Path
    events: Tuple[Dict[str, Any], ...]

    def first(self, kind: str) -> Dict[str, Any]:
        return next((e for e in self.events if e.get("kind") == kind), {})

    def of(self, kind: str) -> List[Dict[str, Any]]:
        return [e for e in self.events if e.get("kind") == kind]

    @property
    def run_id(self) -> str:
        return str(self.first(RUN_STARTED).get("run_id") or self.path.stem.rsplit("-", 1)[-1])


def read_log(path: Path) -> RunLog:
    """A line that is not JSON is skipped, so one damaged line costs one event."""
    events: List[Dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return RunLog(path, ())
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return RunLog(path, tuple(events))


def load_logs(directory: Path, last: Optional[int] = None) -> List[RunLog]:
    """Newest first. File names start with the run's time, so they sort by it."""
    paths = sorted(directory.glob(f"*{LOG_SUFFIX}"), reverse=True) if directory.is_dir() else []
    return [read_log(path) for path in (paths if last is None else paths[:last])]


def percentile(values: Sequence[float], fraction: float) -> Optional[float]:
    """Nearest-rank percentile; None when there is nothing to rank."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, min(len(ordered), math.ceil(fraction * len(ordered))))
    return ordered[rank - 1]


def summarise(logs: Sequence[RunLog]) -> Dict[str, Any]:
    model = [e for log in logs for e in log.of(MODEL_CALL)]
    tools = [e for log in logs for e in log.of(TOOL_CALL)]
    outputs = [e for log in logs for e in log.of(MODEL_OUTPUT)]
    items = [e for log in logs for e in log.of(ITEM_OUTCOME)]
    searches = [e for log in logs for e in log.of(RETRIEVAL)]
    finished = [log.first(RUN_FINISHED) for log in logs]
    latencies = [float(e["latency_ms"]) for e in model if e.get("status") != STATUS_ERROR
                 and isinstance(e.get("latency_ms"), (int, float))]
    slowest = sorted(
        (e for e in model if isinstance(e.get("latency_ms"), (int, float))),
        key=lambda e: -e["latency_ms"],
    )[:SLOWEST_SHOWN]
    return {
        "runs": len(logs),
        "outcomes": dict(Counter(str(f.get("outcome", "not recorded")) for f in finished)),
        "commands": dict(Counter(str(log.first(RUN_STARTED).get("command", "unknown")) for log in logs)),
        "model_calls": len(model),
        "model_errors": sum(1 for e in model if e.get("status") == STATUS_ERROR),
        "model_error_kinds": dict(Counter(
            f"{e.get('error_kind')}" + (f" {e['http_status']}" if e.get("http_status") else "")
            for e in model if e.get("status") == STATUS_ERROR
        )),
        "model_latency_ms": {
            "p50": percentile(latencies, 0.50), "p95": percentile(latencies, 0.95),
            "max": max(latencies) if latencies else None,
        },
        "prompt_tokens": sum(int(e.get("prompt_tokens") or 0) for e in model),
        "output_tokens": sum(int(e.get("output_tokens") or 0) for e in model),
        "calls_by_prompt": dict(Counter(str(e.get("prompt_version") or "unlabelled") for e in model)),
        "invalid_outputs": sum(1 for e in outputs if e.get("valid") is False),
        "tool_calls": len(tools),
        "tool_errors": dict(Counter(str(e.get("error_code")) for e in tools if e.get("status") == STATUS_ERROR)),
        "item_outcomes": dict(Counter(str(e.get("status")) for e in items)),
        "items_for_human_review": sum(1 for e in items if e.get("requires_human_review")),
        "quotations_not_grounded": sum(1 for e in items if e.get("quotation_grounded") is False),
        "searches": len(searches),
        "searches_without_evidence": sum(1 for e in searches if e.get("evidence_sufficient") is False),
        "slowest_model_calls": [
            {"run_id": e.get("run_id"), "purpose": e.get("purpose"), "item_id": e.get("item_id"),
             "latency_ms": e.get("latency_ms"), "prompt_tokens": e.get("prompt_tokens")}
            for e in slowest
        ],
    }


def add_parsers(subparsers: argparse._SubParsersAction) -> None:
    logs = subparsers.add_parser("logs", help="Read the run logs: model, tool, search and outcome evidence")
    actions = logs.add_subparsers(dest="logs_action", required=True)

    def action(name: str, text: str) -> argparse.ArgumentParser:
        parser = actions.add_parser(name, help=text)
        parser.add_argument(
            "--role", default=ROLE_PROCUREMENT_OFFICER, choices=sorted(ROLE_PERMISSIONS),
            help="The caller's role, which decides whether the logs may be read",
        )
        return parser

    listing = action("list", "One line per run, newest first")
    listing.add_argument("--last", type=int, default=DEFAULT_LAST, help="How many runs to list")
    show = action("show", "Print one run, event by event")
    show.add_argument("run", help=f"A run id, the start of one, or {LATEST!r}")
    summary = action("summary", "Add runs together: outcomes, latency, errors, tokens")
    summary.add_argument("--last", type=int, default=None, help="Only the newest N runs")
    summary.add_argument("--json", action="store_true", help="Print the summary as JSON")


def _seconds(milliseconds: Any) -> str:
    return "-" if not isinstance(milliseconds, (int, float)) else f"{milliseconds / 1000:.1f}s"


def _list(directory: Path, args: argparse.Namespace) -> int:
    logs = load_logs(directory, max(1, args.last))
    if not logs:
        print(f"No run has been logged yet. Logs are written to {directory}")
        return EXIT_OK
    for log in logs:
        start, end = log.first(RUN_STARTED), log.first(RUN_FINISHED)
        totals = end.get("totals") or {}
        submission = (start.get("submission") or {}).get("name") or "-"
        print(
            f"{log.run_id}  {str(start.get('at', ''))[:19]}  {start.get('command', '?'):9} "
            f"{end.get('outcome', 'not recorded'):20} {end.get('seconds', '-')}s  "
            f"model {totals.get('model_calls', 0)} ({totals.get('model_errors', 0)} failed)  "
            f"tools {totals.get('tool_calls', 0)} ({totals.get('tool_errors', 0)} failed)  {submission}"
        )
    return EXIT_OK


def _line(event: Dict[str, Any]) -> str:
    kind = event.get("kind")
    if kind == RUN_STARTED:
        submission = event.get("submission")
        parts = [
            f"{event.get('command')} by {event.get('role') or 'the local operator'}",
            f"ProcureCheck {event.get('version')}", str(event.get("model")), str(event.get("pipeline")),
        ]
        if submission:
            parts.append(f"submission {submission.get('name')} ({submission.get('characters')} characters)")
        if event.get("checklist_items") is not None:
            parts.append(f"{event['checklist_items']} items")
        return ", ".join(parts)
    if kind == DECISION:
        stop = f" -> stop: {event['stop_reason']}" if event.get("stop_reason") else ""
        return f"iteration {event.get('iteration')}: {event.get('action')}{stop}. {event.get('reason')}"
    if kind == MODEL_CALL:
        failure = (f" FAILED {event.get('error_kind')} {event.get('http_status') or ''}".rstrip()
                   if event.get("status") == STATUS_ERROR else "")
        tokens = ("no tokens" if event.get("prompt_tokens") is None
                  else f"{event.get('prompt_tokens')} + {event.get('output_tokens')} tokens")
        return (f"{event.get('purpose') or 'unlabelled'} {event.get('item_id') or ''} "
                f"prompt {event.get('prompt_version')} #{event.get('system_prompt_sha256')}, "
                f"{event.get('input_chars')} chars in, {tokens}, {_seconds(event.get('latency_ms'))}{failure}")
    if kind == MODEL_OUTPUT:
        return (f"{event.get('schema')} attempt {event.get('attempt')}: "
                f"{'valid' if event.get('valid') else 'INVALID ' + str(event.get('error_kind'))}")
    if kind == ITEM_OUTCOME:
        return (f"{event.get('item_id')} {event.get('status')}, confidence {event.get('confidence')}, "
                f"quotation grounded: {event.get('quotation_grounded')}, evidence check: "
                f"{event.get('evidence_check')}, {event.get('seconds')}s. {event.get('item')}")
    if kind == RETRIEVAL:
        return (f"{event.get('mode') or event.get('requested_mode')} search, {len(event.get('hits') or [])} "
                f"hits, best cosine {event.get('best_cosine')}, evidence sufficient: "
                f"{event.get('evidence_sufficient')}, {_seconds(event.get('latency_ms'))}. {event.get('query')}")
    if kind == TOOL_CALL:
        outcome = "ok" if event.get("status") != STATUS_ERROR else f"FAILED {event.get('error_code')}"
        approval = f", approval {event['approval']}" if event.get("approval") else ""
        return f"{event.get('tool')} by {event.get('role')}: {outcome}{approval}, {_seconds(event.get('duration_ms'))}"
    if kind == RUN_FINISHED:
        return f"{event.get('outcome')} after {event.get('seconds')}s. Totals: {event.get('totals')}"
    return json.dumps(event, ensure_ascii=False)


def _show(directory: Path, args: argparse.Namespace) -> int:
    logs = load_logs(directory)
    wanted = args.run.strip().lower()
    matches = logs[:1] if wanted == LATEST else [log for log in logs if log.run_id.lower().startswith(wanted)]
    if not matches:
        print(f"No logged run matches {args.run!r}.")
        return EXIT_USER_ERROR
    if len(matches) > 1:
        print(f"{len(matches)} runs match {args.run!r}. Give more of the run id.")
        return EXIT_USER_ERROR
    log = matches[0]
    print(f"Run {log.run_id} ({log.path.name})")
    for event in log.events:
        print(f"  {event.get('seq', '?'):>3} {str(event.get('at', ''))[11:23]} {event.get('kind', '?'):13} {_line(event)}")
    return EXIT_OK


def _summary(directory: Path, args: argparse.Namespace) -> int:
    logs = load_logs(directory, None if args.last is None else max(1, args.last))
    if not logs:
        print(f"No run has been logged yet. Logs are written to {directory}")
        return EXIT_OK
    summary = summarise(logs)
    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return EXIT_OK
    latency = summary["model_latency_ms"]
    print(f"Runs: {summary['runs']}  by command: {summary['commands']}")
    print(f"Outcomes: {summary['outcomes']}")
    print(f"Model calls: {summary['model_calls']}, failed: {summary['model_errors']} {summary['model_error_kinds'] or ''}".rstrip())
    print(f"Model latency: median {_seconds(latency['p50'])}, 95th percentile {_seconds(latency['p95'])}, "
          f"slowest {_seconds(latency['max'])}")
    print(f"Tokens: {summary['prompt_tokens']} in, {summary['output_tokens']} out")
    print(f"Calls by prompt version: {summary['calls_by_prompt']}")
    print(f"Answers that did not match their schema: {summary['invalid_outputs']}")
    print(f"Tool calls: {summary['tool_calls']}, errors: {summary['tool_errors'] or 'none'}")
    print(f"Item outcomes: {summary['item_outcomes'] or 'none'}; for human review: "
          f"{summary['items_for_human_review']}; quotations not found in the submission: "
          f"{summary['quotations_not_grounded']}")
    print(f"Searches: {summary['searches']}, without sufficient evidence: {summary['searches_without_evidence']}")
    for call in summary["slowest_model_calls"]:
        print(f"  slow: run {call['run_id']} {call['purpose']} {call['item_id'] or ''} "
              f"{_seconds(call['latency_ms'])}, {call['prompt_tokens']} prompt tokens")
    return EXIT_OK


_ACTIONS = {"list": _list, "show": _show, "summary": _summary}


def run_logs(args: argparse.Namespace, settings: Settings) -> int:
    principal = Principal(user_id="local", role=args.role)
    if not principal.may(PERMISSION_LOGS_READ):
        print(f"Refused: the role {args.role} may not read the run logs.", file=sys.stderr)
        return EXIT_USER_ERROR
    return _ACTIONS[args.logs_action](resolve_log_dir(settings.log_dir), args)
