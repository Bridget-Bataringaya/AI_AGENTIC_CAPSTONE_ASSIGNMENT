"""The memory demonstration script, run against the scripted model."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from procurecheck.config import Settings
from procurecheck.workflow import WorkflowInput

from tool_fakes import DOCUMENT, ITEMS, StubModelClient

SCRIPT = Path(__file__).parent / "evaluation" / "run_memory_demonstration.py"


def load_script():
    spec = importlib.util.spec_from_file_location("run_memory_demonstration", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_three_runs_decide_the_same_whatever_memory_holds(tmp_path):
    script = load_script()
    workflow_input = WorkflowInput("demo", "bid.txt", "Bid Document", DOCUMENT, tuple(ITEMS))
    result = script.demonstrate(StubModelClient(), Settings(), workflow_input, tmp_path)
    assert result["identical"] is True
    assert [arm for arm in result["arms"]] == ["A", "B", "C"]
    assert result["arms"]["A"]["memory"] is None
    statuses = [status for _item, status in result["arms"]["C"]["decided"]["statuses"]]
    assert statuses == ["Present", "Missing"]
    assert any("Confirm by hand" in line for line in result["arms"]["C"]["memory_lines"])
    assert result["arms"]["C"]["memory"]["used_by_planner"] is False


def test_the_scripted_command_exits_0_and_writes_nothing(monkeypatch, tmp_path, capsys):
    script = load_script()
    monkeypatch.setattr(script, "TRACE_DIR", tmp_path / "traces")
    monkeypatch.setattr(script, "RESULTS", tmp_path / "results.json")
    monkeypatch.setattr("sys.argv", ["run_memory_demonstration.py", "--scripted"])
    assert script.main() == 0
    assert "Memory changed nothing the run decided." in capsys.readouterr().out
    assert not (tmp_path / "traces").exists() and not (tmp_path / "results.json").exists()
