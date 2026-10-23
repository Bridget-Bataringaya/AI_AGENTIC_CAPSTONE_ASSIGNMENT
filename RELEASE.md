# Release v1.0.0

Public Procurement Document-Completeness Agent (ProcureCheck). Week 8 final. Tag `v1.0.0`, branch `main`, 23 October 2026.

Authors: Makmot Johnson Kabira (23/U/26794/EVE), Mwesigwa Isaac (23/U/12539/PS), Bataringaya Bridget (23/U/07471/EVE), Jonathan Katongole (23/U/27072/EVE). Group H (Evening), BSE4104, Makerere University.

The formatted Word copy of this note is `docs/Release Note v1.0.0.docx`.

## 1. Release Identification

| Field | Value |
| --- | --- |
| Tag | v1.0.0 |
| Branch | main |
| Date | 23 October 2026 |
| Package | procurecheck 1.0.0 |
| Repository | https://github.com/Bridget-Bataringaya/AI_AGENTIC_CAPSTONE_ASSIGNMENT |

## 2. What Is Included in v1.0.0

- Six-step completeness workflow by direct orchestration: check every item, re-check Unclear items, open review tickets, generate the report, hold `publish_completeness_report` for a `procurement_officer` sign-off, hand off.
- Layout-aware AST chunking and hybrid retrieval (`src/procurecheck/retrieval/`).
- Fail-closed human approval gate (`src/procurecheck/tools/approval.py`, `publishing.py`). Piped input is never sign-off.
- SQLite case memory (`data/memory/case-history.sqlite3`), `used_by_planner: false`, 180-day retention, officer-only access.
- Captured live and scripted traces under `evidence/traces/`.
- Week 8 corrections: isolated uploads, chronological log listing, invalid page citations routed to human review.
- Safety boundary unchanged: no bid scoring, no multi-bid ranking, no legal validity opinions, no award or disqualification recommendations.

## 3. Reproducible Execution Instructions

### Option A — One-command local verification (no Ollama/GPU, <30s)

```bash
git clone --branch v1.0.0 https://github.com/Bridget-Bataringaya/AI_AGENTIC_CAPSTONE_ASSIGNMENT.git
cd AI_AGENTIC_CAPSTONE_ASSIGNMENT
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
bash scripts/verify_release.sh
```

### Option B — Live model run (Meta Llama 3.1 8B via Ollama)

```bash
ollama pull llama3.1:8b
ollama serve
python run.py health
python run.py check --submission knowledge/samples/synthetic-submission.pdf
python tests/evaluation/run_memory_demonstration.py
python run.py workflow --submission knowledge/samples/synthetic-submission.pdf --publish
```

### Option C — Docker

```bash
docker build -t procurecheck:v1.0.0 .
docker run --rm procurecheck:v1.0.0
```

## 4. Verification Results on Clean Checkout

`bash scripts/verify_release.sh` exited 0.

| Check | Result |
| --- | --- |
| Python | 3.14.4 (local). Docker image is python:3.11-slim. |
| Package | procurecheck 1.0.0 |
| pytest -q | **511 passed**, 8 warnings, 4.67 s |
| Approval gate | `tests/test_approval.py` included; fail-closed |
| Memory | `tests/test_memory.py` included; `used_by_planner` is false |
| Workflow | `tests/test_workflow.py` included; Unclear re-check covered |
| Scripted memory demonstration | Exit 0. Arms A, B and C decided the same. Memory changed no decision. |
| `python run.py verify --quick` | 5 passed, 4 skipped |

No coverage package is installed; no coverage percentage is claimed.

Docker: `docker build -t procurecheck:v1.0.0 .` succeeded. `docker run --rm procurecheck:v1.0.0` used Python 3.11.17, reported procurecheck 1.0.0, passed 511 tests in 4.81 s (1 warning), repeated the scripted memory demonstration with identical decisions, and exited 0.

## 5. Known Limitations Remaining at v1.0.0

1. CPU inference latency of about 500 to 680 seconds on live Llama 3.1 8B (median model call 168.2 s; a three-item workflow 680.6 s).
2. Unencrypted local SQLite and traces that retain verbatim quotes, pending Data Protection and Privacy Act 2019 legal review before real bids are checked.
3. Role-level rather than per-submission access control.
4. Unclear re-check branch validated via scripted tests, not a live Unclear trace.
5. The report still states a completeness percentage, which Week 1 ruled out (open point, Week 7 scenario TC22).
