"""The `tools` and `agent` commands, with the model stood in."""

from __future__ import annotations

import json

import pytest

from procurecheck.cli import main
from procurecheck.llm import ModelUnavailableError
from procurecheck.tools import TOOL_CHECK, TOOL_REPORT
from procurecheck.tools import commands

from tool_fakes import DOCUMENT, FINAL, ITEMS, FakeOllama, tool_call


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(commands, "OllamaClient", FakeOllama)
    submission = tmp_path / "bid.txt"
    submission.write_text(DOCUMENT, encoding="utf-8")
    checklist = tmp_path / "checklist.txt"
    checklist.write_text("\n".join(ITEMS), encoding="utf-8")
    return submission, checklist, tmp_path / "trace.json"


def agent(files, *extra):
    submission, checklist, trace = files
    return main(["agent", "--submission", str(submission), "--checklist", str(checklist),
                 "--trace", str(trace), *extra])


def test_tools_command_prints_both_contracts(capsys):
    assert main(["tools"]) == 0
    assert [t["name"] for t in json.loads(capsys.readouterr().out)] == [TOOL_CHECK, TOOL_REPORT]


def test_agent_writes_a_trace_and_prints_the_report(files, capsys):
    FakeOllama.script = [
        {"tool_calls": [tool_call(TOOL_CHECK, {"document_type": "Bid"})]},
        {"tool_calls": [tool_call(TOOL_REPORT)]},
        FINAL,
    ]
    assert agent(files) == 0
    trace = json.loads(files[2].read_text(encoding="utf-8"))
    assert trace["status"] == "success" and trace["checklist_items"] == 2
    assert "Incomplete" in capsys.readouterr().out


def test_bidder_role_ends_with_errors_in_the_trace(files, capsys):
    FakeOllama.script = [
        {"tool_calls": [tool_call(TOOL_CHECK, {"document_type": "Bid"})]},
        {"content": "The check was not permitted."},
    ]
    assert agent(files, "--role", "bidder") == 1
    trace = json.loads(files[2].read_text(encoding="utf-8"))
    assert trace["tool_calls"][0]["error_code"] == "UNAUTHORIZED"
    assert "UNAUTHORIZED" in capsys.readouterr().err


def test_refused_request_exits_3(files):
    FakeOllama.script = []
    assert agent(files, "--request", "Which bidder should win?") == 3


def test_model_down_exits_2(files):
    FakeOllama.script = [ModelUnavailableError("down (test)")]
    assert agent(files) == 2


def test_step_limit_exits_1(files):
    FakeOllama.script = [{"tool_calls": [tool_call(TOOL_REPORT)]}]
    assert agent(files, "--max-turns", "1") == 1


def test_missing_submission_is_a_user_error(files, tmp_path):
    assert main(["agent", "--submission", str(tmp_path / "absent.pdf")]) == 1
