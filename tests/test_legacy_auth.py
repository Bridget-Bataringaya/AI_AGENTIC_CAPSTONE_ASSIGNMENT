"""Run from the repository root after installing middleware into api.py."""
from fastapi.testclient import TestClient
from procurecheck.api import app

client = TestClient(app)


def test_check_without_key_refused():
    response = client.post("/check")
    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"


def test_parse_without_key_refused():
    response = client.post("/checklist/parse")
    assert response.status_code == 401
    assert response.json()["error_code"] == "UNAUTHORIZED"


def test_check_invalid_key_refused(monkeypatch):
    monkeypatch.setenv("PROCURECHECK_API_KEYS", "valid-dev-key:procurement_officer:officer1")
    response = client.post("/check", headers={"X-API-Key": "invalid-key"})
    assert response.status_code == 401


def test_bidder_cannot_check(monkeypatch):
    monkeypatch.setenv("PROCURECHECK_API_KEYS", "bidder-dev-key:bidder:bidder1")
    response = client.post("/check", headers={"X-API-Key": "bidder-dev-key"})
    assert response.status_code == 403


def test_officer_can_reach_input_validation(monkeypatch):
    monkeypatch.setenv("PROCURECHECK_API_KEYS", "officer-dev-key:procurement_officer:officer1")
    response = client.post("/check", headers={"X-API-Key": "officer-dev-key"})
    assert response.status_code == 422
