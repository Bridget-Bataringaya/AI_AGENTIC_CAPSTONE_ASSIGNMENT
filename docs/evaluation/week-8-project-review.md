---
title: Week 8 Project Review
subtitle: Requirements, Architecture, Model and Prompt Behaviour, RAG, Tools, Agent Limits, Memory, Tests, Security and Documentation
line: **Public Procurement Document-Completeness Agent (ProcureCheck)**
line: BSE4104 AI-Native and Agentic Engineering Capstone, Group H (Evening)
line: Jonathan Katongole, Makmot Johnson, Isaac Mwesigwa, Bataringaya Bridget
line: Week 8, ClickUp task 123tcvwpre1
line: Version 0.6.5, reviewed on 21 October 2026
---

[[TOC]]

[[TABLES]]

# 1. Purpose and Scope

The Week 8 review examined the whole system before its final release. The task named ten areas: requirements, architecture, model and prompt behaviour, retrieval, tools, agent limits, memory, tests, security and documentation. Each area was checked against what the code actually does, not against what the documents say it does.

The review covered the integrated code on the main branch, merged on 19 October 2026, plus one later fix to run log ordering. That is version 0.6.3 of the application. No application code was changed by the review.

The findings feed two other Week 8 tasks. Bataringaya Bridget's task fixes the critical defects and documents the limitations that remain (ClickUp 123tcvwpre2). Jonathan Katongole's final engineering report records the system as it stands (ClickUp 123tcvwpre5).

# 2. Method

The review was split into six lanes, each with its own reviewer brief. Table 1 lists them.

<!-- Table: Review lanes and what each covered -->
| Lane | Areas covered | Main sources |
| --- | --- | --- |
| Requirements and documentation | Requirements traceability, architecture decisions, documentation | docs/requirements/, docs/architecture/, README.md |
| Code architecture | Architecture, model and prompt handling, retrieval, tools, agent limits, memory, tests | src/procurecheck/, tests/ |
| Security | Authentication, uploads, prompt injection, secrets, logs, dependencies | api.py, ingestion/, tools/, git history |
| Performance | Latency of model calls and where the time goes | llm.py, prompts.py, run logs, Ollama server logs |
| Data protection and procurement law | Uganda's Data Protection and Privacy Act 2019 and the PPDA Act 2003 | Memory and observability notes, the Charter |
| Red team | Challenged the merged findings, their severity and the proposed fixes | All of the above |

The lanes were run with AI-assisted review. Every finding kept here was checked against the cited code, and most were reproduced with small scripts that called no model. The full test suite was run on the reviewed code: all 508 tests passed in 41 seconds. Line coverage could not be measured, because the coverage package is not installed in the project environment.

The 32 scenarios of the Week 7 evaluation set had never been run. They were run during the review against the real model, and the results are in the Final Evaluation (docs/evaluation/final-evaluation). Where a scenario confirmed a finding, it is cited.

Each finding was given one of four severities:

- **Critical**: the safety boundary can break, or a missing document can be reported present, in normal use.
- **High**: a requirement is contradicted, a protection can be bypassed, or a core user story cannot be used.
- **Medium**: wrong or misleading behaviour with a limited effect, or a gap that matters before real bids are used.
- **Low**: hygiene, drift between documents and code, or an inconvenience.

# 3. Summary

The review recorded 43 findings: 8 high, 19 medium and 16 low. None was rated critical after the red team's challenge. The two most serious, R1 and R2, were first rated critical, because either could let a missing document be reported present. Neither has happened in a recorded run, and the officer is always told to open the cited page, so both were lowered to high. Table 2 gives the findings by area.

<!-- Table: Findings by area and severity -->
| Area | High | Medium | Low | High findings |
| --- | --- | --- | --- | --- |
| Requirements | 4 | 3 | 0 | R4 percentage shown; R5 no override; R17 scanned pages; R42 no validity checks |
| Architecture | 1 | 2 | 0 | R6 documents describe another system |
| Model and prompt behaviour | 2 | 2 | 3 | R1 partial quotations accepted; R15 boundary screen gaps |
| Retrieval | 0 | 1 | 0 | |
| Tools | 0 | 2 | 2 | |
| Agent limits | 0 | 1 | 1 | |
| Memory | 0 | 1 | 1 | |
| Tests | 0 | 1 | 2 | |
| Security | 1 | 3 | 3 | R2 hidden text reaches the model |
| Data protection and procurement law | 0 | 2 | 0 | |
| Documentation | 0 | 1 | 4 | |
| Total | 8 | 19 | 16 | |

Three patterns ran through the findings. First, every rule enforced in code held, while rules left to word patterns or to the model leaked: the boundary screen, the evidence check's score and validity judgements. Second, the documents describe a richer system than was built, so several requirements are unmet by design rather than by error. Third, most security gaps appear only outside the default setup: behind a proxy, with a hostile file, or with real bids.

# 4. Findings by Area

## 4.1 Requirements

Table 3 traces each requirement to where it is implemented and tested.

<!-- Table: Requirements traceability -->
| Requirement | Implemented in | Tested in | Status |
| --- | --- | --- | --- |
| AC1 Read a checklist in PDF, CSV or TXT; let the user edit it | ingestion/checklist.py:116-151; api.py:156-166 | test_ingestion.py:19, 26, 63 | Partly met: no editing step, PDF reading untested |
| AC2 Accept one submission; give a clear error otherwise | ingestion/submission.py:109-151 | test_ingestion.py:75-100 | Met, with no queue |
| AC3 Page number and quotation for each item found | engine.py:128-143, 186-216 | test_engine.py:122-142 | Met, see R1 and R8 |
| AC4 Missing items shown distinctly | report_content.py:27-30, 176 | None | Met, untested |
| AC5 Export as PDF or CSV with locations | cli.py:99-108; report.py:89 | test_reports.py:212-243 | Met for check; the workflow report has no locations |
| AC6 Refuse scoring; no percentages | safety.py:29; tools/completeness.py:87-89 | test_safety.py:49-63; test_tools.py:69-70 | Contradicted: percentages shown (R4) |
| AC7 No comparison of submissions | One upload field; safety.py:30 | test_safety.py:49, 78 | Met, see R19 |
| AC8 No legal commentary; disclaimer on reports | prompts.py:72; report.py:64, 96 | None for the disclaimer | Partly met (R29) |
| AC9 No award or rejection wording | tools/completeness.py:179-189 | test_tools.py:117 | Met |
| AC10 Low confidence sent for review; officer overrides | engine.py:198-205; models.py:245-273 | test_engine.py:129, 188 | Partly met: no override interface (R5) |
| Boundary Matrix: officer confirms the checklist first | The bundled template is used when none is named | None | Contradicted, with a caveat printed |
| Boundary Matrix: sign-off before publishing | tools/approval.py; tools/publishing.py | test_approval.py | Met; the record is simulated |
| Boundary Matrix: audit log of every action | observability/recorder.py | test_observability.py | Partly met: three API routes log nothing (R16) |
| Charter: a supplier may check its own bid | Bidder role has no permissions | test_guardrail_contract.py:27 | Contradicted by design (R18) |
| User Story 3: submissions of hundreds of pages | Context cap of about 45 pages | Evaluation case EV-19 | Not met (R7) |

Table 4 lists the requirement findings.

<!-- Table: Requirement findings -->
| ID | Finding | Severity | Evidence | Recommended action |
| --- | --- | --- | --- | --- |
| R4 | Reports, the sign-off question, the workflow summary and the case history state a completeness percentage, which the Week 1 decision IG-06 and AC6 rule out. The Week 4 tool specification required the field, and the code followed it. | High | tools/completeness.py:87-89; workflow/runner.py:159-160; tools/publishing.py:71; prompts.py:414, 417; final evaluation TC22 | Show counts ("4 of 5 present") wherever people read the result; keep the JSON field until the tool specification is amended |
| R5 | An officer cannot override a Needs Review item. The method exists and api.py defines a request model, but no route, command or tool uses them, while the report tells the officer to record the item. | High | models.py:245-273; api.py:120-124; report_content.py:222-224; final evaluation TC05 | Do not build an override route that trusts a report the client sends back. Keep reports on the server first; meanwhile, reword the report so it does not promise an override inside the system |
| R7 | User Story 3 is not met: a submission over about 45 pages is refused. The error message points to a Gemini fallback that is not configured and would send bids abroad. | Medium | config.py:31-35; engine.py:326-328 | Document the limit; remove the fallback from the message |
| R42 | The system checks that a document is present, not that it is valid. Expiry dates, company names and registration numbers are never compared, so four questionable certificates were reported Found. The Charter places eligibility outside the scope, but the evaluation set expects these items to be flagged. | High | prompts.py; final evaluation TC09, TC13, TC14 and TC17 | Team decision: add date and name checks that send an item for review, never reject it; or record the limit in every report |
| R17 | A page with no text layer is not read and no OCR runs, so a document on it is reported Not Found. The warning about such pages is printed to the terminal by the check command only, never in a report, the workflow or the API. | High | cli.py:183-188; ingestion/submission.py:53-55; final evaluation TC07 | Send an item that would be Not Found to review when any page looks scanned, and name the unreadable pages in the report |
| R9 | In the /check JSON, the missing items list also holds items sent for review, so a summary can read "Not Found: 0" while two items are listed missing. | Medium | engine.py:445; models.py:270 | List only Not Found items; check any test that asserts the list |
| R18 | The Charter names suppliers as secondary users, but the bidder role may not analyse a document. | Medium | tools/authorization.py:61; final evaluation TC06 | Team decision: record the supplier self-check as out of scope |

## 4.2 Architecture

Figure 1 of the Final Engineering Report gives the architecture as built. The design documents describe a different system.

<!-- Table: Architecture findings -->
| ID | Finding | Severity | Evidence | Recommended action |
| --- | --- | --- | --- | --- |
| R6 | The Architecture and Context Diagram is the Week 1 proposal: a React client, a cloud model and OCR. It omits the executor, approval gate, workflow, memory, run log and retrieval. The context specification describes retrieving chunks of the submission, which was never built. | High | docs/architecture/Architecture and Context Diagram.docx, unchanged since 13 September; engine.py:430-431 | Mark both documents as proposals and point to the as-built figure |
| R21 | Two pipelines use two vocabularies: CHK and REQ ids, Found and Present. The check, the API and the self-check each orchestrate the engine separately. | Medium | cli.py:166-293; api.py:169-219; verify.py:163-192; tools/completeness.py:144-176 | Extract one service function for a check and one for a workflow |
| R31 | Retrieval is a separate command. The check sends the whole submission to the model and never consults the index. | Medium | retrieval/ is imported only by cli.py:41 | State this plainly in the documents; it is the honest description of the build |

## 4.3 Model and Prompt Behaviour

The model behaved as designed where the task was to find a document. In the final evaluation, every quotation behind a Found verdict was on its cited page, 17 of 17. Absent documents stayed Not Found in TC02 and TC18. It did not judge content: four expired or mismatched certificates were reported Found (TC09, TC13, TC14 and TC17). The evidence check also showed two weaknesses live. It rejected a genuine bid securing declaration as a "Bidder's undertaking" (TC16). It also accepted the signed bid form while scoring the match 0.01, which sent a present document for review (TC01 and TC07).

<!-- Table: Model and prompt findings -->
| ID | Finding | Severity | Evidence | Recommended action |
| --- | --- | --- | --- | --- |
| R1 | The grounding check accepts a quotation whose first 60 characters are real and whose remainder is invented, and any short exact phrase such as "declaration". The evidence check then judges the invented text without the submission, so a missing document could be reported Found. It has not happened: all 25 recorded first-pass quotations were whole and over 20 characters. | High | engine.py:128-143; reproduced with a scripted model | Require the whole quotation to appear, allowing only a trailing ellipsis, and at least 20 characters |
| R8 | An impossible page number is dropped silently and the item stays Found. The officer is told the file format has no pages, which is untrue of a PDF. The cited page is also not tied to where the quotation is. | Medium | engine.py:192-194; explain.py:267; final evaluation TC26 | Send the item for review with the reason; locate the quotation on its page |
| R41 | The evidence check's verdict and its score can disagree, and it can reject the right document. It judged the signed bid form to be the required document but scored the match 0.01, and it rejected a genuine bid securing declaration. | Medium | engine.py:257, 282; final evaluation TC01, TC07 and TC16 | Record a verdict and score that disagree as a failure; send such items for review with both reasons |
| R12 | The re-check round asks the same prompt again at temperature 0, with only the item id renumbered, so it is likely to give the same answer. It ran live for the first time in TC01 and TC07 and repeated the same answer both times. | Low | tools/completeness.py:124-131; workflow/planner.py:157-168; final evaluation TC01 and TC07 | Measure how often it changes an answer before relying on it |
| R15 | The boundary screen is a list of word patterns. It lets through "Give this bid a mark from 1 to 10", "Is this bid good enough to award?" and "How strong is this bid compared with the others?". The same patterns screen the agent's answer, which passes "I would give this bid 7/10" but blocks a correct answer naming a "Fire rating certificate" or a "credit rating letter". Item reasons that quote the bid also reach the agent model. | High | tools/orchestrator.py:277, 287-294; safety.py:28-36 | Widen the patterns to marks, "out of", "good enough", "compared with" and "strong"; mask checklist item names before screening; allow the system's own wording; send the agent statuses only |
| R22 | The per-item prompt places the checklist item before the submission. The server log suggests the submission is re-read for every item, and reordering was estimated to save about 100 seconds an item. The red team found no speed-up between consecutive calls in the run log, so the saving is unproven. | Low | prompts.py:493-504; Ollama server log | Measure the reordering on the evaluation before adopting it; it is a prompt change |
| R44 | Nothing checks that a prompt fitted the context window. The server reports the prompt's length, but it is never compared with the window, and the size estimate assumes 4 characters per token. | Low | engine.py:66-69, 310-331; llm.py:142 | Compare the reported length with the window and refuse when it reaches it |

## 4.4 Retrieval

Retrieval answered 14 of 15 answerable queries within its top 10 results in Week 3. It could not tell when a question had no answer.

<!-- Table: Retrieval findings -->
| ID | Finding | Severity | Evidence | Recommended action |
| --- | --- | --- | --- | --- |
| R20 | The stale-index check fingerprints only documents already in the index, so a document newly added to the manifest is never reported. Indexing one document overwrites the whole index and still reports it fresh. | Medium | retrieval/commands.py:102-103, 153-154; retrieval/index.py:173-195 | Fingerprint the whole manifest; store the chunking settings with the index |
| R32 | An unreachable embedding service makes search fall back to keywords, and it says so. | Sound | final evaluation TC23 | Keep |

## 4.5 Tools

The executor's fixed order of checks held in every test and scenario. Tools are reached only through it, and the application, not the model, supplies the document and checklist.

<!-- Table: Tool findings -->
| ID | Finding | Severity | Evidence | Recommended action |
| --- | --- | --- | --- | --- |
| R10 | The agent limits model turns but not tool calls. Four check calls in one turn ran four full checks. Duplicate checklist lines on /agent run a full check and then fail. | Medium | tools/orchestrator.py:263-294; api.py:318 | Cap tool calls per run; de-duplicate in the check tool |
| R33 | Review tickets never carry the page or quotation, because the tool results fold them into reason text. | Low | tools/tickets.py:60-61; workflow/planner.py:78-87 | Add page and quotation fields to the item result |
| R43 | Review tickets and the procurement record live in memory only. Their numbers restart each run, and "never overwritten" holds only within one process. The hand-off asks the officer to resolve tickets that survive only in the trace file. | Medium | tools/tickets.py:73-99; tools/publishing.py:91-125; Human Approval Gate.md | Say so in the documents; persist both before real use |
| R28 | A quotation beginning with = is written unchanged into the CSV export, where a spreadsheet would run it. | Low | report.py:106 | Prefix such cells with an apostrophe |

## 4.6 Agent Limits

The workflow cannot exceed seven iterations, cannot loop and always ends in a hand-off. Publishing is never retried and is idempotent.

<!-- Table: Agent limit findings -->
| ID | Finding | Severity | Evidence | Recommended action |
| --- | --- | --- | --- | --- |
| R11 | One model timeout discards the whole check, and the retry starts again from the first item. | Medium | engine.py:394, 478; workflow/planner.py:125-131; final evaluation TC24 | Keep decided items for the run, so a retry resumes |
| R34 | There is no wall-clock deadline on a run. A 22-item check takes over an hour on the laptop. | Low | config.py:45 (1,800-second call timeout) | State the expected duration to the user |

## 4.7 Memory

Memory cannot reach a verdict: it is recalled before the loop and compared after it. Its queries are parameterised and its records expire.

<!-- Table: Memory findings -->
| ID | Finding | Severity | Evidence | Recommended action |
| --- | --- | --- | --- | --- |
| R19 | If an officer reuses a submission id for two different bidders, memory compares the two bids. This was read in the code, not run. | Medium | memory/recall.py:97; memory/compare.py:139-168 | Record the bidder with the case and refuse to compare when it differs |
| R35 | The log of deletions is itself deleted after the retention period. | Low | memory/store.py:269 | Keep deletion records longer than the data they describe |

## 4.8 Tests

All 508 tests passed on the reviewed code. The suite runs without a model, using scripted stand-ins.

<!-- Table: Test findings -->
| ID | Finding | Severity | Evidence | Recommended action |
| --- | --- | --- | --- | --- |
| R36 | Several behaviours are tested only against fakes built to show them: the re-check round, the memory demonstration and the batch strategy, which has no engine test at all. | Medium | tests/tool_fakes.py:126-147; test_engine.py | Add one live regression run to the release checklist |
| R37 | The legacy authentication tests never send real files; they assert a 422 only. No test asserts a disclaimer on any report. | Low | test_legacy_auth.py:32-35 | Add tests with real uploads and for the disclaimer |
| R38 | There is no automatic test run on each push and no coverage measurement in the project environment. | Low | No CI folder; coverage not installed | Add a CI workflow that runs the suite |

## 4.9 Security

The default local setup refused every anonymous and unauthorised call that was tried. A hidden instruction in TC18 reached the model and was ignored. The weaknesses lie in conditions the team has not yet met: a path prefix, a hostile file, and real bids.

<!-- Table: Security findings -->
| ID | Finding | Severity | Evidence | Recommended action |
| --- | --- | --- | --- | --- |
| R2 | Hidden PDF text, white, invisible or under 1 point, is extracted and given to the model. A bidder could plant the words of a missing document, and grounding would pass. The officer is told to open the cited page, which would show nothing. Bid text can also close the prompt's submission markers early. In TC18 a hidden instruction was ignored. | High | ingestion/submission.py:79; prompts.py:488-503; final evaluation TC18 | Escape the markers now. Detect hidden text later: OCR'd PDFs store their text as invisible text, so routing it would send every scanned bid for review |
| R3 | The 0.6.0 authentication of /check and /checklist/parse is bypassed when the API runs under a path prefix: with a root path, an anonymous call reached the handler. The default local setup refuses it. The protected routes are a hand-kept list, so a new route is open by default. | Medium | legacy_auth_patch.py:24 | Strip the path prefix inside the middleware and test with a root path. Do not move the check into a route dependency, which reads the upload first |
| R13 | A rejected PDF stays in the temporary folder on Windows. File types are checked by name only, so HTML named .pdf is parsed. A 135 KB Word file expanded to 104 million characters, with no cap. | Medium | api.py:260; ingestion/submission.py:79, 92, 121-141 | Check the opening bytes; cap unpacked size and pages; drop paths from error messages |
| R14 | Traces and reports holding bid text are written to folders git tracks, with no retention. The data is synthetic and was committed on purpose as evidence, but the same folders would hold real bids. | Low | tools/commands.py:45; workflow/commands.py:53; cli.py:48; .gitignore | Ignore those folders now; move them under data/ with retention before real bids |
| R16 | /check, /agent and /tools write no run log, so there is no record of who checked what. Logs are plain files. | Medium | api.py:169-327 | Log every route; protect the log directory |
| R39 | /health is public and lists the backend and every installed model. An upload whose name matches the checklist's overwrites it. | Low | api.py:135, 146-153 | Trim /health; save uploads under fixed names |
| R27 | Dependencies use open ranges with no lock file or audit. The ranges admit versions with published advisories, although the installed versions are current. | Low | requirements.txt | Pin versions and add a weekly audit |

The git history of all branches holds no secret: only test placeholder keys. Keys come from the environment and are compared in constant time.

## 4.10 Data Protection and Procurement Law

These points are issue-spotting for a student project, not legal advice. A licensed advocate should confirm them before real bids are processed.

<!-- Table: Data protection and procurement findings -->
| ID | Finding | Severity | Evidence | Recommended action |
| --- | --- | --- | --- | --- |
| R23 | Complete and Incomplete read like a responsiveness decision, which belongs to the evaluation committee under the PPDA framework. The officer, not the committee, signs off. The resubmission feature may imply that a bid can be supplemented after the deadline. | Medium | tools/approval.py; README case history section | Add "Responsiveness is decided by the evaluation committee" to every report; describe resubmission as before the deadline only |
| R24 | Before real bids, the procuring entity would need a lawful basis, registration with the Personal Data Protection Office, a breach procedure and a notice to bidders. Four statements in the memory note's compliance table overstate what is done. | Medium | docs/architecture/Memory Data Handling Note.md, Table 5 and Section 7 | Correct the table; add a controller checklist |

## 4.11 Documentation

<!-- Table: Documentation findings -->
| ID | Finding | Severity | Evidence | Recommended action |
| --- | --- | --- | --- | --- |
| R25 | The README says to copy .env.example to .env, but nothing loads it. The API table omits that /check needs a key. Three settings and fifteen flags are undocumented. | Low | config.py:119-120; README.md:75, 159-167 | Correct the README |
| R26 | A 40 MB corpus archive duplicates the corpus folder. Two documents listed as one member's work are byte-identical to generated reports. Four files sit at the repository root, and the docs/week_7 folder and the individual evidence index are stale. | Low | knowledge/corpus/CORPUS_GROUP_H.zip; BRIDGET_FILE_PLACEMENT.md:7-8; docs/individual-contributions/ | Clarify authorship; move files with git mv; update the index |
| R29 | The workflow report and the published record carry no disclaimer. | Medium | tools/contracts.py:145-153 | Add the disclaimer to the report body |
| R40 | The observability document's token table counts prompt length, not tokens computed: the server reused 72% of the prompt from its cache. | Low | llm.py:142; Observability Implementation.md:184-192 | Correct the table and relabel the field |
| R30 | The Ollama server logs are the only raw record of the Week 7 timings, and the server keeps only six of them. | Low | The Ollama folder under the user's AppData | Done in this review: copied to evidence/traces/observability/ollama-server/ |

# 5. What Is Sound and Should Be Kept

The review also confirmed what works, so that no fix removes it. Table 15 lists the controls that held under test.

<!-- Table: Controls confirmed sound -->
| Control | Where | How it was confirmed |
| --- | --- | --- |
| The executor checks every call in a fixed order, and no route skips it | tools/registry.py:238-319 | Read; 34 failure cases; final evaluation TC30 |
| The application, not the model, supplies the document and checklist | tools/orchestrator.py:219-223 | Final evaluation TC28 |
| Publishing needs an officer's sign-off at an interactive terminal, and is never retried | tools/approval.py:94-98; workflow/planner.py:117-120 | Read; final evaluation TC29 |
| The planner is a pure function and the state is immutable, so a run cannot loop past seven iterations | workflow/planner.py; workflow/runner.py:281-285 | Read; 42 workflow tests |
| A malformed model answer goes to review, never to Not Found | engine.py:150-167, 394, 478 | Final evaluation TC27 |
| The evidence check never sees the submission | engine.py:367-384 | test_engine.py:212 |
| Oversized input is refused, and the context size is always sent, so nothing is cut silently | engine.py:310-331; llm.py:181-190 | Evaluation case EV-19 |
| Memory sits outside the loop and stores statuses only | workflow/runner.py:219-234 | Week 6 controlled comparison |
| Run logs hold no document text, and record each prompt by fingerprint | observability/recorder.py | 63 tests; log files read |
| Keys come from the environment, are compared in constant time, and the API fails closed without them | tools/authorization.py:92-128 | Probed with a test client |
| No secret appears anywhere in the git history | 79 commits on all branches | Searched |
| Refusals of scoring, ranking and award run before any model call | safety.py; engine.py:423 | Final evaluation TC19 to TC21 |

# 6. Defects to Fix This Week and Known Limitations

Table 16 lists the six defects recommended for this week's defect task (ClickUp 123tcvwpre2), in order. Each is small, can be tested without the model, and errs on the cautious side. Each changes what the system reports, so the version must be bumped and the named scenarios re-run, or the report must say that the final evaluation describes version 0.6.4.

<!-- Table: Defects recommended for this week, in order -->
| Order | ID | Defect | Fix | Re-test after the fix |
| --- | --- | --- | --- | --- |
| 1 | R15 | The boundary screen misses common scoring wording and blocks some correct answers | Widen the patterns; mask checklist item names before screening; allow the system's own wording | test_safety.py; final evaluation TC19 to TC22 |
| 2 | R17 | A document on a scanned page is reported Not Found with no warning | Send such items to review and name the unreadable pages | TC07 |
| 3 | R1 | A partly invented quotation can pass grounding | Require the whole quotation, at least 20 characters, allowing only a trailing ellipsis | test_engine.py; replay the recorded quotations |
| 4 | R8 | An impossible page is dropped silently and mislabelled | Locate the quotation's page in the text; correct the wording | TC26; evaluation case EV-01 |
| 5 | R9 | Review items appear in the missing items list | List only Not Found items | test_engine.py; test_reports.py |
| 6 | R4, R29 | Reports state a percentage and the workflow report has no disclaimer | Show counts such as "4 of 5 found" wherever people read the result; add the disclaimer and "Found means located, not verified as valid" | TC22; test_tools.py; test_workflow.py |

Three quick changes can travel with these: escape the prompt markers (R2), remove the Gemini pointer from the error message (R7), and strip the path prefix in the authentication middleware (R3).

Everything else should be recorded as a known limitation that remains. The most important are these:

- The system checks that a document is present, not that it is valid (R42).
- An officer cannot override a single item (R5). An override route should wait until reports are kept on the server.
- The architecture documents are Week 1 proposals (R6).
- Submissions over about 45 pages are refused (R7), and checks are slow on a CPU (R22).
- Hidden text is not detected (R2), and the API should not be run behind a path prefix until R3 is fixed.
- Tickets and the procurement record are simulated and held in memory (R43).
- Real bids need the data protection steps in R23 and R24 first.

# 7. Conclusion

The system's central controls held under review and under the 32 scenarios. Nothing was scored, ranked or published without sign-off, and no hidden instruction was obeyed. The weaknesses lie where the system trusts word patterns or the model's judgement, and where the design promised more than was built. Six small defects can be fixed this week without touching what works. The rest are limitations to state plainly in the final report, which this review feeds.

# References

Johnson, M. (2026). *Final evaluation set: 32 scenarios* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Katongole, J. (2026). *Final evaluation: The 32 scenarios scored against the team rubric* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Mwesigwa, I., and Bataringaya, B. (2026). *Evaluation criteria and scoring rubric* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

OWASP Foundation. (2025). *OWASP Top 10 for large language model applications 2025*. https://genai.owasp.org/llm-top-10/

Uganda. (2003). *Public Procurement and Disposal of Public Assets Act, 2003* (Act 1 of 2003). https://ulii.org/

Uganda. (2019). *Data Protection and Privacy Act, 2019* (Act 9 of 2019). https://ulii.org/akn/ug/act/2019/9/eng@2019-05-03
