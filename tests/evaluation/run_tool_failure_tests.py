"""Run the tool-calling failure tests and write the evaluation table.

    python tests/evaluation/run_tool_failure_tests.py

Runs tests/test_tool_failures.py, records the outcome of every TF case beside
what the case expects, adds the live runs against the real model found in
evidence/traces/tools/live-*.json, and writes:

    docs/evaluation/tool-failure-tests.csv
    docs/evaluation/tool-failure-tests.md    (source, in tools/build_report.py form)
    docs/evaluation/tool-failure-tests.docx  (Document Format Standard)

The expectations below were written with the tests, before the first run.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_DIR = REPO_ROOT / "docs" / "evaluation"
LIVE_DIR = REPO_ROOT / "evidence" / "traces" / "tools"
TEST_FILE = REPO_ROOT / "tests" / "test_tool_failures.py"
STEM = "tool-failure-tests"

MISSING = "Missing or unusable parameters"
UNAUTHORIZED = "Unauthorized requests"
UNAVAILABLE = "Unavailable services"
UNEXPECTED = "Unexpected tool and model responses"
CATEGORIES = (MISSING, UNAUTHORIZED, UNAVAILABLE, UNEXPECTED)


@dataclass(frozen=True)
class Case:
    case_id: str
    category: str
    scenario: str
    expected: str


CASES: Tuple[Case, ...] = (
    Case("TF-01", MISSING, "Check tool called without document_type", "MISSING_PARAMETER naming document_type"),
    Case("TF-02", MISSING, "Check tool called without required_items", "MISSING_PARAMETER naming required_items"),
    Case("TF-03", MISSING, "Checklist holds only blank entries", "MISSING_CHECKLIST; no model call"),
    Case("TF-04", MISSING, "Report tool called with no results", "NO_ANALYSIS_RESULTS"),
    Case("TF-05", MISSING, "Model omits document_type, then retries", "MISSING_PARAMETER sent back to the model; retry succeeds"),
    Case("TF-06", MISSING, "required_items sent as a string, not a list", "INVALID_ARGUMENTS"),
    Case("TF-07", MISSING, "Model adds an undeclared parameter", "INVALID_ARGUMENTS naming it"),
    Case("TF-08", MISSING, "Raw PDF bytes sent as document_text", "UNSUPPORTED_DOCUMENT"),
    Case("TF-09", MISSING, "Blank document_text", "EMPTY_DOCUMENT"),
    Case("TF-10", UNAUTHORIZED, "Anonymous caller runs a check", "UNAUTHORIZED with the specified message; no model call"),
    Case("TF-11", UNAUTHORIZED, "Bidder calls either tool", "UNAUTHORIZED with each tool's specified message"),
    Case("TF-12", UNAUTHORIZED, "Evaluation committee member calls both tools", "Check refused; report allowed"),
    Case("TF-13", UNAUTHORIZED, "Bidder calls with empty arguments", "UNAUTHORIZED; no parameter names disclosed"),
    Case("TF-14", UNAUTHORIZED, "Caller with an unknown role", "UNAUTHORIZED"),
    Case("TF-15", UNAUTHORIZED, "Bidder drives the agent", "Tool call UNAUTHORIZED; run ends UNAUTHORIZED; no findings"),
    Case("TF-16", UNAUTHORIZED, "Request to rank bidders", "REFUSED before any model call"),
    Case("TF-17", UNAVAILABLE, "Model backend fails during a check", "SERVICE_UNAVAILABLE"),
    Case("TF-18", UNAVAILABLE, "Orchestrating model is down", "SERVICE_UNAVAILABLE; no tool run"),
    Case("TF-19", UNAVAILABLE, "Real client against a closed port", "ModelUnavailableError, not a crash"),
    Case("TF-20", UNAVAILABLE, "Backend answers HTTP 500, or HTML instead of JSON", "ModelUnavailableError in both cases"),
    Case("TF-21", UNAVAILABLE, "Document larger than the context window", "ANALYSIS_FAILED; no model call"),
    Case("TF-22", UNEXPECTED, "Tool returns a percentage of 150", "UNEXPECTED_TOOL_RESPONSE; output discarded"),
    Case("TF-23", UNEXPECTED, "Tool returns prose instead of its schema", "UNEXPECTED_TOOL_RESPONSE"),
    Case("TF-24", UNEXPECTED, "Tool raises an unhandled KeyError", "ANALYSIS_FAILED naming the fault type only; no crash"),
    Case("TF-25", UNEXPECTED, "Report percentage contradicts its results", "INVALID_RESULTS naming both figures"),
    Case("TF-26", UNEXPECTED, "Report results list an item twice", "INVALID_RESULTS"),
    Case("TF-27", UNEXPECTED, "Report result has status \"Probably\"", "INVALID_RESULTS"),
    Case("TF-28", UNEXPECTED, "Model calls a tool that does not exist", "UNKNOWN_TOOL; run continues"),
    Case("TF-29", UNEXPECTED, "Model arguments are broken JSON, or a list", "INVALID_ARGUMENTS in both cases"),
    Case("TF-30", UNEXPECTED, "Model tool_calls field is malformed", "INVALID_ARGUMENTS in both cases"),
    Case("TF-31", UNEXPECTED, "Model never stops calling tools", "STEP_LIMIT_REACHED after 3 turns"),
    Case("TF-32", UNEXPECTED, "Model tries to replace the document and checklist", "Model values discarded; uploaded document checked"),
    Case("TF-33", UNEXPECTED, "Model's final answer recommends an award", "Answer withheld; tool results kept"),
    Case("TF-34", UNEXPECTED, "Model requests a report before any check", "NO_ANALYSIS_RESULTS, then check and report succeed"),
)


class _Collector:
    """A pytest plugin that records each TF case's outcome."""

    def __init__(self) -> None:
        self.outcomes: Dict[str, List[str]] = defaultdict(list)
        self.failures: Dict[str, str] = {}

    def pytest_runtest_logreport(self, report) -> None:
        if report.when != "call" and not (report.when == "setup" and report.failed):
            return
        match = re.search(r"test_tf(\d\d)_", report.nodeid)
        if not match:
            return
        case_id = f"TF-{match.group(1)}"
        self.outcomes[case_id].append(report.outcome)
        if report.failed:
            self.failures[case_id] = str(report.longrepr).splitlines()[-1][:200]


def _actual(case: Case, collector: _Collector) -> Tuple[str, str]:
    outcomes = collector.outcomes.get(case.case_id, [])
    if not outcomes:
        return "Not run", "The test was not found."
    if all(o == "passed" for o in outcomes):
        variants = f" ({len(outcomes)} variants)" if len(outcomes) > 1 else ""
        return "Met", f"As expected{variants}."
    return "Not met", collector.failures.get(case.case_id, "Failed.")


def _live_rows() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for path in sorted(LIVE_DIR.glob("live-*.json")):
        trace = json.loads(path.read_text(encoding="utf-8"))
        calls = trace.get("tool_calls", [])
        steps = ", ".join(
            f"{c['tool']} {c['status'] if c['status'] == 'success' else c['error_code']}" for c in calls
        ) or "no tool call"
        outcome = trace["error"]["error_code"] if trace.get("error") else "success"
        report = (trace.get("report") or {}).get("report") or {}
        checks = [c["result"] for c in calls if c["status"] == "success" and "results" in c["result"]]
        if report:
            summary = f"{report.get('overall_status')}, {report.get('completeness_percentage')}%"
        elif checks:
            summary = f"No report; check gave {checks[-1]['completeness_percentage']}%"
        else:
            summary = "-"
        role = (trace.get("principal") or {}).get("role", "-")
        rows.append({
            "run": path.stem, "role": role, "request": trace.get("request", ""),
            "calls": steps, "outcome": outcome, "report": summary,
            "seconds": str(trace.get("seconds", "-")), "turns": str(trace.get("model_turns", "-")),
        })
    return rows


def _markdown(results: List[Tuple[Case, str, str]], live: List[Dict[str, str]], stamp: str) -> str:
    met = sum(1 for _, status, _ in results if status == "Met")
    lines = [
        "---",
        "title: Tool-Calling Failure Tests",
        "subtitle: Missing Parameters, Unauthorized Requests, Unavailable Services and Unexpected Responses",
        "line: **Public Procurement Document-Completeness Agent (ProcureCheck)**",
        "line: BSE4104 AI-Native and Agentic Engineering Capstone, Group H (Evening)",
        f"line: Run {stamp}",
        "---",
        "",
        "[[TOC]]",
        "",
        "[[TABLES]]",
        "",
        "# 1. Scope",
        "",
        "The tests cover the tool-calling layer added in Week 4. It runs the two tools in the team's "
        "tool specification: check_document_completeness and generate_completeness_report. Every "
        "call passes through one executor. The executor checks that the tool exists, that the caller "
        "is permitted, that the arguments match the schema, and that the answer matches the schema.",
        "",
        "Each case states its expected behaviour before it runs. A case is Met only when every "
        "assertion in its test passes. The rule behind every case is the same. A failure must end "
        "in a structured error with a named code, never in a crash, an empty result or an invented one.",
        "",
        "The cases run without a model server, against a scripted model, so each one is repeatable. "
        "Section 4 adds live runs against the real model.",
        "",
        "# 2. Summary",
        "",
        f"{met} of {len(results)} cases met their expected behaviour. Table 1 gives the count by category.",
        "",
        "<!-- Table: Cases met by failure category -->",
        "| Category | Cases | Met |",
        "| --- | --- | --- |",
    ]
    for category in CATEGORIES:
        in_category = [r for r in results if r[0].category == category]
        met_here = sum(1 for _, status, _ in in_category if status == "Met")
        ids = f"{in_category[0][0].case_id} to {in_category[-1][0].case_id}"
        lines.append(f"| {category} | {ids} | {met_here} of {len(in_category)} |")
    lines += ["", "# 3. Expected and Actual Behaviour", ""]
    for number, category in enumerate(CATEGORIES, start=1):
        table_no = number + 1
        lines += [
            f"## 3.{number} {category}",
            "",
            f"Table {table_no} lists each case, its expected behaviour and the result.",
            "",
            f"<!-- Table: {category}: expected and actual behaviour -->",
            "| Case | Scenario | Expected | Result |",
            "| --- | --- | --- | --- |",
        ]
        for case, status, note in results:
            if case.category == category:
                lines.append(f"| {case.case_id} | {case.scenario} | {case.expected} | {status}. {note} |")
        lines.append("")
    lines += ["# 4. Live Runs Against the Model", ""]
    if live:
        lines += [
            f"Table {len(CATEGORIES) + 2} lists runs of the agent command against the real model, "
            "Meta Llama 3.1 8B through Ollama on a CPU-only laptop. The traces are in evidence/traces/tools/.",
            "",
            "<!-- Table: Live agent runs -->",
            "| Run | Role | Tool calls | Outcome | Report | Seconds |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        lines += [
            f"| {r['run']} | {r['role']} | {r['calls']} | {r['outcome']} | {r['report']} | {r['seconds']} |"
            for r in live
        ]
    else:
        lines.append("No live runs were recorded.")
    skipped_report = [
        r["run"] for r in live
        if r["outcome"] == "success" and "generate_completeness_report" not in r["calls"]
    ]
    if skipped_report:
        lines += [
            "",
            "## 4.1 Observations",
            "",
            f"In {', '.join(skipped_report)}, the model called the check tool and then answered "
            "directly. It did not call the report tool, although the request asked for a report. "
            "The check results were correct and were carried in the trace. The model's answer "
            "also gave the tool's status, success, as if it were the document's overall status.",
            "",
            "Neither behaviour broke a safety rule, and no finding was invented. Both are "
            "weaknesses of the orchestration prompt, orchestrator-v1.0, with an 8B model. A "
            "later version should either state the tool order more firmly or have the application "
            "call the report tool itself after a successful check.",
        ]
    lines += [
        "",
        "# 5. Reproducing the Results",
        "",
        "The scripted cases run with python tests/evaluation/run_tool_failure_tests.py, which also "
        "rewrites this document. The live runs use python run.py agent with the options recorded "
        "at the top of each trace file.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    collector = _Collector()
    exit_code = pytest.main([str(TEST_FILE), "-q", "-p", "no:cacheprovider"], plugins=[collector])
    results = [(case, *_actual(case, collector)) for case in CASES]
    live = _live_rows()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    with (EVALUATION_DIR / f"{STEM}.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case", "category", "scenario", "expected", "result", "note"])
        writer.writerows([c.case_id, c.category, c.scenario, c.expected, s, n] for c, s, n in results)

    source = EVALUATION_DIR / f"{STEM}.md"
    source.write_text(_markdown(results, live, stamp), encoding="utf-8")
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from build_report import build  # noqa: E402

    build(source, source.with_suffix(".docx"))
    met = sum(1 for _, status, _ in results if status == "Met")
    print(f"{met} of {len(results)} cases met. Wrote {source} and .docx", file=sys.stderr)
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
