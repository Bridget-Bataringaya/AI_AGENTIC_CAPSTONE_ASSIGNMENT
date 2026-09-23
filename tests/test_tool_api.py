"""The tool routes over HTTP: authentication, status codes and envelopes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from procurecheck import api
from procurecheck.tools import TOOL_CHECK, TOOL_REPORT

from tool_fakes import DOCUMENT, FINAL, ITEMS, FakeOllama, tool_call

OFFICER_KEY = "officer-key"
BIDDER_KEY = "bidder-key"
REPORT_ARGS = {
    "document_name": "bid.pdf", "document_type": "Bid Document", "completeness_percentage": 50.0,
    "completeness_results": [
        {"item": "Tax clearance", "status": "Present", "reason": "p. 2"},
        {"item": "Bid securing declaration", "status": "Missing", "reason": "none"},
    ],
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PROCURECHECK_API_KEYS", f"{OFFICER_KEY}:procurement_officer:alice,{BIDDER_KEY}:bidder:bob")
    monkeypatch.setattr(api, "OllamaClient", FakeOllama)
    return TestClient(api.app)


def post_tool(client, name, arguments, key=OFFICER_KEY):
    headers = {"X-API-Key": key} if key else {}
    return client.post(f"/tools/{name}", json=arguments, headers=headers)


def test_tools_are_listed_with_their_contracts(client):
    listed = client.get("/tools").json()
    assert [t["name"] for t in listed] == [TOOL_CHECK, TOOL_REPORT]
    assert all({"input_schema", "output_schema", "permission"} <= set(t) for t in listed)


def test_officer_runs_a_check(client):
    response = post_tool(client, TOOL_CHECK, {
        "document_text": DOCUMENT, "document_type": "Bid Document", "required_items": ITEMS,
    })
    assert response.status_code == 200
    assert response.json()["completeness_percentage"] == 50.0


def test_no_key_is_401_with_the_specification_envelope(client):
    response = post_tool(client, TOOL_REPORT, REPORT_ARGS, key=None)
    assert response.status_code == 401
    assert response.json() == {
        "status": "error", "error_code": "UNAUTHORIZED",
        "message": "You do not have permission to generate or access this report.",
    }


def test_wrong_key_is_treated_as_no_key(client):
    assert post_tool(client, TOOL_REPORT, REPORT_ARGS, key="guess").status_code == 401


def test_bidder_key_is_403(client):
    response = post_tool(client, TOOL_CHECK, {}, key=BIDDER_KEY)
    assert response.status_code == 403 and response.json()["error_code"] == "UNAUTHORIZED"


def test_unknown_tool_is_404(client):
    assert post_tool(client, "delete_submission", {}).status_code == 404


def test_missing_parameter_is_422(client):
    response = post_tool(client, TOOL_CHECK, {"document_text": DOCUMENT})
    assert response.status_code == 422 and response.json()["error_code"] == "MISSING_PARAMETER"


def test_inconsistent_results_are_422(client):
    response = post_tool(client, TOOL_REPORT, {**REPORT_ARGS, "completeness_percentage": 10})
    assert response.status_code == 422 and response.json()["error_code"] == "INVALID_RESULTS"


def test_unconfigured_keys_fail_closed(client, monkeypatch):
    monkeypatch.delenv("PROCURECHECK_API_KEYS")
    assert post_tool(client, TOOL_REPORT, REPORT_ARGS).status_code == 401


def test_malformed_key_config_is_a_server_error_not_an_open_door(client, monkeypatch):
    # A typo that drops the user id. The key must not come back to the caller.
    monkeypatch.setenv("PROCURECHECK_API_KEYS", "sk-live-secret-123:procurement_officer")
    response = post_tool(client, TOOL_REPORT, REPORT_ARGS, key=None)
    assert response.status_code == 500
    assert "sk-live-secret-123" not in response.text


def _agent_call(client, tmp_path, key):
    submission = tmp_path / "bid.txt"
    submission.write_text(DOCUMENT, encoding="utf-8")
    with submission.open("rb") as s:
        return client.post("/agent", headers={"X-API-Key": key} if key else {},
                           files={"submission": ("bid.txt", s, "text/plain")})


def test_agent_route_refused_throughout_is_403_not_200(client, tmp_path):
    FakeOllama.script = [
        {"tool_calls": [tool_call(TOOL_CHECK, {"document_type": "Bid"})]},
        {"content": "I was not permitted to run the check."},
    ]
    response = _agent_call(client, tmp_path, BIDDER_KEY)
    assert response.status_code == 403
    assert response.json()["error"]["error_code"] == "UNAUTHORIZED"


def test_agent_route_without_a_key_is_401(client, tmp_path):
    FakeOllama.script = [
        {"tool_calls": [tool_call(TOOL_CHECK, {"document_type": "Bid"})]},
        {"content": "Not permitted."},
    ]
    assert _agent_call(client, tmp_path, None).status_code == 401


def test_agent_route_runs_the_model_driven_loop(client, tmp_path):
    FakeOllama.script = [
        {"tool_calls": [tool_call(TOOL_CHECK, {"document_type": "Bid Document"})]},
        {"tool_calls": [tool_call(TOOL_REPORT)]},
        FINAL,
    ]
    submission = tmp_path / "bid.txt"
    submission.write_text(DOCUMENT, encoding="utf-8")
    checklist = tmp_path / "checklist.txt"
    checklist.write_text("\n".join(ITEMS), encoding="utf-8")
    with submission.open("rb") as s, checklist.open("rb") as c:
        response = client.post(
            "/agent", headers={"X-API-Key": OFFICER_KEY},
            files={"submission": ("bid.txt", s, "text/plain"), "checklist": ("checklist.txt", c, "text/plain")},
        )
    trace = response.json()
    assert response.status_code == 200, trace
    assert [call["tool"] for call in trace["tool_calls"]] == [TOOL_CHECK, TOOL_REPORT]
    assert trace["report"]["report"]["overall_status"] == "Incomplete"
