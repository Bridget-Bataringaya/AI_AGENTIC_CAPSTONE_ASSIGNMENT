"""The `workflow` command and the POST /workflow route, with the model stood in."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from procurecheck import __version__, api
from procurecheck.cli import main
from procurecheck.workflow import commands

from tool_fakes import DOCUMENT, ITEMS, FakeOllama

OFFICER_KEY = "officer-key"
BIDDER_KEY = "bidder-key"


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(commands, "OllamaClient", FakeOllama)
    submission = tmp_path / "bid.txt"
    submission.write_text(DOCUMENT, encoding="utf-8")
    checklist = tmp_path / "checklist.txt"
    checklist.write_text("\n".join(ITEMS), encoding="utf-8")
    return submission, checklist, tmp_path / "trace.json"


def workflow(files, *extra):
    submission, checklist, trace = files
    return main(["workflow", "--submission", str(submission), "--checklist", str(checklist),
                 "--trace", str(trace), "--retry-delay", "0", *extra])


def test_workflow_writes_a_trace_and_prints_the_handoff(files, capsys):
    assert workflow(files) == 0
    trace = json.loads(files[2].read_text(encoding="utf-8"))
    assert trace["version"] == __version__ and trace["stop_reason"] == "report_ready"
    assert [s["plan"]["action"] for s in trace["steps"]] == ["check", "generate_report"]
    out = capsys.readouterr().out
    assert "Incomplete" in out and "Hand-off to procurement_officer" in out


def test_a_bidder_is_refused_and_exits_1(files):
    assert workflow(files, "--role", "bidder") == 1
    trace = json.loads(files[2].read_text(encoding="utf-8"))
    assert trace["stop_reason"] == "unauthorized"


def test_a_backend_that_stays_down_exits_2(files, monkeypatch):
    class DownOllama(FakeOllama):
        def __init__(self, settings=None):
            super().__init__(settings)
            self.unavailable = True

    monkeypatch.setattr(commands, "OllamaClient", DownOllama)
    assert workflow(files) == 2


def test_impossible_limits_are_an_input_error(files):
    assert workflow(files, "--max-iterations", "0") == 1


def test_a_missing_submission_is_an_input_error(tmp_path):
    assert main(["workflow", "--submission", str(tmp_path / "absent.pdf")]) == 1


def test_version_flag_prints_the_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert __version__ in capsys.readouterr().out


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(
        "PROCURECHECK_API_KEYS", f"{OFFICER_KEY}:procurement_officer:alice,{BIDDER_KEY}:bidder:bob"
    )
    monkeypatch.setattr(api, "OllamaClient", FakeOllama)
    return TestClient(api.app)


def post_workflow(client, tmp_path, key):
    submission = tmp_path / "bid.txt"
    submission.write_text(DOCUMENT, encoding="utf-8")
    checklist = tmp_path / "checklist.txt"
    checklist.write_text("\n".join(ITEMS), encoding="utf-8")
    headers = {"X-API-Key": key} if key else {}
    with submission.open("rb") as s, checklist.open("rb") as c:
        return client.post("/workflow", headers=headers, files={"submission": s, "checklist": c})


def test_workflow_route_returns_the_trace(client, tmp_path):
    response = post_workflow(client, tmp_path, OFFICER_KEY)
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == __version__ and body["report"]["report"]["completeness_percentage"] == 50.0


def test_workflow_route_refuses_a_bidder_with_403(client, tmp_path):
    response = post_workflow(client, tmp_path, BIDDER_KEY)
    assert response.status_code == 403
    assert response.json()["stop_reason"] == "unauthorized"


def test_workflow_route_without_a_key_is_401_before_the_upload_is_read(client, tmp_path, monkeypatch):
    def fail(*_args):
        raise AssertionError("the upload was read for an anonymous caller")

    monkeypatch.setattr(api, "_read_uploads", fail)
    response = post_workflow(client, tmp_path, None)
    assert response.status_code == 401
    assert response.json()["detail"]["error_code"] == "UNAUTHORIZED"


def test_an_oversized_upload_is_refused_with_413(client, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "MAX_UPLOAD_BYTES", 10)
    assert post_workflow(client, tmp_path, OFFICER_KEY).status_code == 413


def test_the_api_announces_its_version(client):
    assert client.get("/openapi.json").json()["info"]["version"] == __version__


class _Terminal:
    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


@pytest.mark.parametrize("answer,stop,exit_code", [
    ("APPROVE", "published", 0),
    ("no", "not_published", 4),
])
def test_publish_asks_the_officer_at_the_terminal(files, monkeypatch, capsys, answer, stop, exit_code):
    monkeypatch.setattr("sys.stdin", _Terminal(True))
    monkeypatch.setattr("builtins.input", lambda _prompt: answer)
    assert workflow(files, "--publish") == exit_code
    trace = json.loads(files[2].read_text(encoding="utf-8"))
    assert trace["stop_reason"] == stop
    assert "Sign-off needed for publish_completeness_report" in capsys.readouterr().err


def test_an_approval_piped_in_by_a_script_does_not_publish(files, monkeypatch):
    monkeypatch.setattr("sys.stdin", _Terminal(False))
    monkeypatch.setattr("builtins.input", lambda _prompt: "APPROVE")
    assert workflow(files, "--publish") == 4
    trace = json.loads(files[2].read_text(encoding="utf-8"))
    assert trace["stop_reason"] == "not_published" and trace["record"] is None


def test_without_publish_the_officer_is_never_asked(files, monkeypatch):
    def fail(_prompt):
        raise AssertionError("the officer was asked without --publish")

    monkeypatch.setattr("builtins.input", fail)
    assert workflow(files) == 0


def test_publishing_through_the_api_needs_a_person_and_is_refused_with_428(client):
    report = {
        "document_name": "bid.pdf", "document_type": "Bid Document", "overall_status": "Incomplete",
        "completeness_percentage": 50.0, "present_items": ["Tax clearance"],
        "missing_items": ["Bid securing declaration"], "unclear_items": [], "recommendations": [],
    }
    response = client.post(
        "/tools/publish_completeness_report", headers={"X-API-Key": OFFICER_KEY},
        json={"submission_id": "bid", "report": report},
    )
    assert response.status_code == 428
    assert response.json()["error_code"] == "APPROVAL_REQUIRED"
