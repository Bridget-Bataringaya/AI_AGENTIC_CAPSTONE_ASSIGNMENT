---
title: Release Note v1.0.0
subtitle: Public Procurement Document-Completeness Agent (ProcureCheck)
line: **Week 8 Final Release**
line: BSE4104 AI-Native and Agentic Engineering Capstone
line: Group H (Evening)
line: Makmot Johnson Kabira (23/U/26794/EVE)
line: Mwesigwa Isaac (23/U/12539/PS)
line: Bataringaya Bridget (23/U/07471/EVE)
line: Jonathan Katongole (23/U/27072/EVE)
line: School of Computing and Informatics Technology, Makerere University
line: 23 October 2026
---

[[TOC]]

[[TABLES]]

# Abstract

**Introduction.** This note records the v1.0.0 release of ProcureCheck. The release packages the existing completeness agent so that a clean checkout of the annotated tag can be installed and verified without a live model. **Methods.** Version 1.0.0 was locked in the package metadata. A one-command verification script, a Docker image, and these notes were added. The unit suite, the scripted memory demonstration and the deterministic self-check were run on a clean install. **Results.** 511 tests passed in 4.67 seconds. The scripted three-arm memory demonstration left every decision unchanged and recorded used_by_planner as false. The fail-closed approval gate and the Unclear re-check branch were covered by the suite. **Conclusion.** Tag v1.0.0 is reproducibly runnable. The completeness workflow's decisions are unchanged. Known limits from Weeks 6 to 8 remain: CPU inference latency, unencrypted local stores pending legal review, role-level access control, and an Unclear re-check path validated only by scripted tests.

# 1. Release Identification

<!-- Table: Release identification for v1.0.0 -->
| Field | Value |
| --- | --- |
| Tag | v1.0.0 |
| Branch | main |
| Date | 23 October 2026 |
| Package version | 1.0.0 |
| Course | BSE4104 AI-Native and Agentic Engineering Capstone |
| Group | Group H (Evening) |
| Repository | https://github.com/Bridget-Bataringaya/AI_AGENTIC_CAPSTONE_ASSIGNMENT |

Authors, listed as human team members only:

- Makmot Johnson Kabira, jmakmot51@gmail.com, Reg No 23/U/26794/EVE
- Mwesigwa Isaac, mwesigwaisaac40@gmail.com, Reg No 23/U/12539/PS
- Bataringaya Bridget, bridgetbataringaya7@gmail.com, Reg No 23/U/07471/EVE
- Jonathan Katongole, jonathaninnocentkatongolejr@gmail.com, Reg No 23/U/27072/EVE

The annotated tag names Mwesigwa Isaac as tagger. No automated or tool name appears in the package metadata, this document, or the git identity used for the release commit.

# 2. What Is Included in v1.0.0

v1.0.0 is the Week 8 freeze of the agent that already existed on main, plus two Week 8 corrections merged from `week8-123tcvwpre2-upload-isolation`: uploaded inputs are isolated so one request cannot collide with another, run logs are listed in chronological order, and a page citation that does not exist in the submission is routed to human review rather than reported as found.

## 2.1 Completeness verification workflow

`workflow` runs the task on one submission by direct orchestration. The application, not the model, chooses each next step:

1. Check every required item.
2. Re-check items that came back Unclear, while the rest are kept.
3. Open a review ticket for any item that stays Unclear.
4. Generate the completeness report.
5. If publishing was asked for, hold `publish_completeness_report` until a procurement officer signs off.
6. Stop and hand off to the officer. The report is ready, or it has been published.

The Unclear re-check and the review-ticket step are implemented and covered by `tests/test_workflow.py`. Live traces against Llama 3.1 8B did not produce an Unclear item.

## 2.2 Layout-aware chunking and hybrid retrieval

Documents in the controlled corpus are split into blocks in reading order, each carrying its heading and page, then packed into passages of about 220 words that never cross a heading (`src/procurecheck/retrieval/chunking.py`, `segment.py`). Search fuses BM25 keyword ranking with `nomic-embed-text` vectors by reciprocal rank. Every result names its document, page, section heading and chunk id.

## 2.3 Fail-closed human approval gate

Publishing a report is the one higher-impact action. The executor holds `publish_completeness_report` after permission and argument checks and before the tool runs (`src/procurecheck/tools/approval.py`, `publishing.py`). No approver, a decline, no answer, piped input, or a yes from someone without sign-off rights all refuse the action, and nothing is recorded. Over the API a publish call ends as APPROVAL_REQUIRED (HTTP 428). Only the `procurement_officer` role may sign off.

## 2.4 SQLite case memory

Each workflow run that reaches a report remembers the submission's item statuses, never the document text, in `data/memory/case-history.sqlite3`. The earlier case is recalled before the loop and compared only after the loop has stopped. The trace records `used_by_planner` as false. Retention is 180 days. Only a procurement officer may read, write or delete.

## 2.5 Captured traces

Live and scripted traces already in the repository remain under `evidence/traces/`: completeness checks, workflow runs, memory demonstrations, tool-calling runs, retrieval searches, observability logs and the Week 7 failure re-tests.

## 2.6 Safety boundary

The system will not score, grade or rate a submission; rank or compare bidders; comment on the legal validity of a clause; or recommend awarding, rejecting or disqualifying a bid.

# 3. Reproducible Execution Instructions

Python 3.11 or later is required. Option A and Option C need no Ollama and no GPU.

## 3.1 Option A: one-command local verification

```bash
git clone --branch v1.0.0 https://github.com/Bridget-Bataringaya/AI_AGENTIC_CAPSTONE_ASSIGNMENT.git
cd AI_AGENTIC_CAPSTONE_ASSIGNMENT
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
bash scripts/verify_release.sh
```

## 3.2 Option B: live model run (Meta Llama 3.1 8B via Ollama)

```bash
ollama pull llama3.1:8b
ollama serve
python run.py health
python run.py check --submission knowledge/samples/synthetic-submission.pdf
python tests/evaluation/run_memory_demonstration.py
python run.py workflow --submission knowledge/samples/synthetic-submission.pdf --publish
```

`workflow --publish` asks the officer to type APPROVE at an interactive terminal. Piped input is never treated as sign-off. A live check on CPU-only hardware takes several minutes per item.

## 3.3 Option C: Docker

```bash
docker build -t procurecheck:v1.0.0 .
docker run --rm procurecheck:v1.0.0
```

The image's default command is `bash scripts/verify_release.sh`.

# 4. Verification Results on Clean Checkout

Verification was run from a local checkout of `main` after `pip install -r requirements.txt && pip install -e .`, using `bash scripts/verify_release.sh`. The interpreter was Python 3.14.4. The package reported version 1.0.0. The script exited 0.

<!-- Table: Verification results for v1.0.0 -->
| Check | Result |
| --- | --- |
| Package version | procurecheck 1.0.0 |
| pytest -q | 511 passed, 8 warnings in 4.67 s |
| tests/test_approval.py | Included in the 511; fail-closed publish gate |
| tests/test_memory.py | Included in the 511; used_by_planner is false; 180-day retention |
| tests/test_workflow.py | Included in the 511; Unclear re-check and review tickets |
| Scripted memory demonstration | Exit 0. Arms A, B and C decided the same. Memory changed nothing the run decided. |
| python run.py verify --quick | 5 checks passed, 4 skipped (model checks skipped under --quick) |

The scripted memory demonstration printed:

- A (memory off): Present, Missing; report_ready
- B (truthful earlier case): same as A; comparison advisory; earlier result changed no status
- C (false earlier case that said every item Present): same as A; the item that memory called Present and the run called Missing was flagged for a check by hand

No coverage tool is installed. Coverage was not collected, so no coverage percentage is claimed.

The same script was then run inside the release image:

```bash
docker build -t procurecheck:v1.0.0 .
docker run --rm procurecheck:v1.0.0
```

That run used Python 3.11.17, reported procurecheck 1.0.0, passed 511 tests in 4.81 seconds (1 warning), repeated the scripted memory demonstration with identical decisions, and exited 0.

# 5. Known Limitations Remaining at v1.0.0

These limits are consistent with the Week 6 and Week 7 progress reports, the Memory Data Handling Note, the Observability Implementation note, and the workflow execution traces.

1. **CPU inference latency.** On the development laptop a median model call took 168.2 seconds. A live workflow check of three items took 680.6 seconds. Other live runs fall in about 500 to 680 seconds. The Week 7 latency target (95th percentile of 10 seconds) cannot be met on that hardware.
2. **Unencrypted local SQLite and traces.** Case history is a local SQLite file with no encryption. Trace files under `evidence/traces/` retain the first 200 characters of a submission and the quotation behind each finding. Neither is deleted when a case is forgotten. Both remain pending legal review under the Data Protection and Privacy Act 2019 of Uganda before real bids are checked.
3. **Role-level access control.** Access is by role, not by submission. Any procurement officer can read any case. A person with access to the machine's folder can also open the SQLite file with other software.
4. **Unclear re-check branch.** The re-check of Unclear items and the opening of review tickets are implemented and covered by scripted tests. They have not been captured on a live Llama 3.1 8B run, because those runs returned no Unclear item.
5. **Completeness percentage.** The report still states a percentage of items present. Week 1 ruled out scores. This conflict is recorded as an open point in the Week 7 report (scenario TC22) and is not resolved in v1.0.0.

# 6. What This Release Does Not Change

No new product feature was added for packaging. The two Week 8 corrections (upload isolation, chronological logs, invalid page citations) were merged because they were already completed on a teammate branch and are part of the freeze. The planner, the approval gate, the memory store and the safety refusals behave as they did at the end of Week 7, with the page-citation routing noted above.

# References

Bataringaya, B., Katongole, J., Mwesigwa, I., and Kabira, M. J. (2026). *Public Procurement Document-Completeness Agent*, source repository, tag v1.0.0.

Katongole, J. (2026a). *Persistent memory implementation*. Group H (Evening), BSE4104.

Katongole, J. (2026b). *Memory data handling note*. Group H (Evening), BSE4104.

Katongole, J. (2026c). *Observability implementation*. Group H (Evening), BSE4104.

Katongole, J. (2026d). *Human approval gate*. Group H (Evening), BSE4104.

Katongole, J. (2026e). *Week 6 progress report*. Group H (Evening), BSE4104.

Katongole, J. (2026f). *Week 7 progress report*. Group H (Evening), BSE4104.

The Data Protection and Privacy Act, 2019 (Uganda).
