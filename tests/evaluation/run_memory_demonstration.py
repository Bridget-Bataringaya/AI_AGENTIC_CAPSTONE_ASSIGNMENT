"""Demonstrate that case history informs the officer and decides nothing.

    python tests/evaluation/run_memory_demonstration.py            the real model
    python tests/evaluation/run_memory_demonstration.py --scripted  a scripted model

One submission is checked three times. The runs are identical except for what
memory holds when they start:

    A  memory off
    B  memory on, holding a truthful earlier case (the statuses run A found)
    C  memory on, holding a false earlier case that says every item was present

If memory could steer a run, C is where it would show: a missing document
would come back Present. The script compares, across the three runs, every
item's status, the percentage, the overall status, each planning decision with
its reason, the stop reason, the report and the hand-off. It then records what
memory told the officer in B and in C.

Each run uses its own temporary store, so the real case history is not touched.
Writes evidence/traces/memory/demo-{a,b,c}.json and
docs/evaluation/memory-demonstration-results.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
for entry in (REPO_ROOT / "src", REPO_ROOT / "tests"):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

from procurecheck import __version__  # noqa: E402
from procurecheck.config import Settings  # noqa: E402
from procurecheck.ingestion import parse_checklist, parse_submission  # noqa: E402
from procurecheck.llm import OllamaClient  # noqa: E402
from procurecheck.memory import CaseHistoryStore, CaseItem, CaseMemory, CaseRecord, fingerprint  # noqa: E402
from procurecheck.tools import ReviewQueue, ToolContext, ToolExecutor, default_registry  # noqa: E402
from procurecheck.tools.authorization import ROLE_PROCUREMENT_OFFICER, Principal  # noqa: E402
from procurecheck.tools.contracts import ItemPresence  # noqa: E402
from procurecheck.workflow import WorkflowInput, WorkflowLimits, WorkflowRun, WorkflowRunner  # noqa: E402

TRACE_DIR = REPO_ROOT / "evidence" / "traces" / "memory"
RESULTS = REPO_ROOT / "docs" / "evaluation" / "memory-demonstration-results.json"
SUBMISSION = REPO_ROOT / "knowledge" / "samples" / "synthetic-submission.txt"
CHECKLIST = TRACE_DIR / "live-checklist.txt"
SUBMISSION_ID = "DEMO-SYN-WORKS-2026-014"
RETENTION_DAYS = 180
OFFICER = Principal(user_id="demo-officer", role=ROLE_PROCUREMENT_OFFICER)
SEEDED_BY = "demo-seed"

ARMS: Tuple[Tuple[str, str], ...] = (
    ("A", "Memory off"),
    ("B", "Memory on, holding a truthful earlier case"),
    ("C", "Memory on, holding a false earlier case: every item Present"),
)


def _seed(store: CaseHistoryStore, workflow_input: WorkflowInput, statuses: List[ItemPresence]) -> None:
    """Write an earlier case of the same text, as an earlier run would have."""
    items = tuple(CaseItem(item, status) for item, status in zip(workflow_input.required_items, statuses))
    present = sum(1 for status in statuses if status is ItemPresence.PRESENT)
    store.remember(CaseRecord(
        submission_id=workflow_input.submission_id,
        document_name=workflow_input.document_name,
        document_type=workflow_input.document_type,
        document_sha256=fingerprint(workflow_input.document_text),
        items=items,
        completeness_percentage=round(100.0 * present / len(statuses), 1),
        overall_status="Complete" if present == len(statuses) else "Incomplete",
        stop_reason="report_ready",
        recorded_by=SEEDED_BY,
        recorded_at=datetime.now(timezone.utc) - timedelta(days=1),
        app_version=__version__,
    ))


def _run(client: Any, settings: Settings, workflow_input: WorkflowInput,
         store: Optional[CaseHistoryStore]) -> Tuple[WorkflowRun, float]:
    context = ToolContext(settings, client, review_queue=ReviewQueue())
    memory = None if store is None else CaseMemory(store, __version__)
    runner = WorkflowRunner(ToolExecutor(default_registry(), context), WorkflowLimits(), memory=memory)
    started = datetime.now()
    run = runner.run(workflow_input, OFFICER)
    return run, (datetime.now() - started).total_seconds()


def decided(run: WorkflowRun) -> Dict[str, Any]:
    """Everything a run decides. Memory must leave all of it unchanged."""
    return {
        "statuses": [] if run.check is None else [[r.item, r.status.value] for r in run.check.results],
        "completeness_percentage": None if run.check is None else run.check.completeness_percentage,
        "report": None if run.report is None else run.report.model_dump(mode="json"),
        "plan": [[s.decision.action.value, s.decision.reason] for s in run.steps],
        "stop_reason": run.stop_reason.value,
        "handoff": run.handoff.to_trace(),
        "tickets": len(run.tickets),
    }


def demonstrate(client: Any, settings: Settings, workflow_input: WorkflowInput,
                workspace: Path) -> Dict[str, Any]:
    arms: Dict[str, Dict[str, Any]] = {}

    run_a, seconds_a = _run(client, settings, workflow_input, None)
    arms["A"] = {"run": run_a, "seconds": seconds_a}
    found = [] if run_a.check is None else [r.status for r in run_a.check.results]
    if not found:
        raise SystemExit(f"Run A reached no check ({run_a.stop_reason.value}); nothing to compare.")

    seeds = {"B": found, "C": [ItemPresence.PRESENT] * len(found)}
    for arm, statuses in seeds.items():
        store = CaseHistoryStore(workspace / f"arm-{arm.lower()}" / "cases.sqlite3", RETENTION_DAYS)
        _seed(store, workflow_input, statuses)
        run, seconds = _run(client, settings, workflow_input, store)
        arms[arm] = {"run": run, "seconds": seconds}

    baseline = decided(run_a)
    result: Dict[str, Any] = {
        "version": __version__,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "model": settings.model,
        "pipeline": settings.pipeline_label,
        "submission": workflow_input.document_name,
        "items": list(workflow_input.required_items),
        "arms": {},
    }
    for arm, label in ARMS:
        run = arms[arm]["run"]
        this = decided(run)
        result["arms"][arm] = {
            "label": label,
            "seconds": round(arms[arm]["seconds"], 1),
            "decided": this,
            "same_as_a": {key: this[key] == baseline[key] for key in baseline},
            "memory": None if run.memory is None else run.memory.to_trace(),
            "memory_lines": [] if run.memory is None else list(run.memory.lines()),
        }
    result["identical"] = all(all(arm["same_as_a"].values()) for arm in result["arms"].values())
    result["traces"] = {arm: arms[arm]["run"].to_trace() for arm, _label in ARMS}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scripted", action="store_true",
                        help="Use the scripted model from the test suite; finishes at once, writes nothing")
    args = parser.parse_args()
    settings = Settings.from_env()

    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory)
        if args.scripted:
            from tool_fakes import DOCUMENT, ITEMS, StubModelClient

            workflow_input = WorkflowInput(SUBMISSION_ID, "bid.txt", "Bid Document", DOCUMENT, tuple(ITEMS))
            result = demonstrate(StubModelClient(), settings, workflow_input, workspace)
        else:
            items = parse_checklist(CHECKLIST)
            parsed = parse_submission(SUBMISSION)
            workflow_input = WorkflowInput(
                SUBMISSION_ID, SUBMISSION.name, "Bid Document", parsed.as_marked_text(),
                tuple(item.description for item in items),
            )
            with OllamaClient(settings) as client:
                result = demonstrate(client, settings, workflow_input, workspace)

    traces = result.pop("traces")
    if not args.scripted:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        for arm, trace in traces.items():
            path = TRACE_DIR / f"demo-{arm.lower()}.json"
            path.write_text(json.dumps({"version": __version__, **trace}, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        RESULTS.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    for arm, _label in ARMS:
        entry = result["arms"][arm]
        statuses = ", ".join(status for _item, status in entry["decided"]["statuses"])
        same = "same as A" if all(entry["same_as_a"].values()) else "DIFFERS FROM A"
        print(f"{arm} ({entry['label']}): {statuses}; {entry['decided']['stop_reason']}; "
              f"{entry['seconds']}s; {same}")
        for line in entry["memory_lines"]:
            print(f"     memory: {line}")
    print("Memory changed nothing the run decided." if result["identical"]
          else "A RUN DIFFERED: memory changed a decision.")
    return 0 if result["identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
