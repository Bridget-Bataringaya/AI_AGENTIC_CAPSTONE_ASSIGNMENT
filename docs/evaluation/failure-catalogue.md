---
title: Failure Catalogue
subtitle: Five Recorded Failures, Their Fixes and Their Re-tests
line: **Public Procurement Document-Completeness Agent (ProcureCheck)**
line: BSE4104 AI-Native and Agentic Engineering Capstone, Group H (Evening)
line: Week 7, ClickUp task 123tcvwp3g0
line: Version 0.5.1
---

[[TOC]]

[[TABLES]]

# 1. Purpose

The Week 7 task was to create a failure catalogue with at least five genuine failures and to re-test each one after its fix. A failure counts here only if the repository holds a record of it: a trace, a results table, a test or a commit. Each entry gives what happened, why, what was changed, and a re-test run on 19 October 2026 against version 0.5.0.

This catalogue was compiled from the repository's own records. It accompanies the catalogue submitted for the task, which analyses failure modes of a different retrieval design (Mwesigwa, 2026). Section 8 explains how the two relate.

All model runs used Meta Llama 3.1 8B through Ollama on a CPU-only laptop. The submissions were synthetic.

# 2. Summary

Table 1 lists the five failures.

<!-- Table: The five failures -->
| ID | Failure | Found | Fixed in | Re-test on 19 October 2026 |
| --- | --- | --- | --- | --- |
| F1 | Every absent document was reported as present | Week 2 baseline, 13 September 2026 | Prompt v2.0 | Neither absent document was reported present |
| F2 | A missing document was reported present, quoting a different document | Week 2 evaluation of prompt v2.0 | Evidence check, v2.1, commit 17418ce | With the fix, neither absent document was reported present; with it switched off, both were |
| F3 | The two oldest API routes accepted anonymous callers | Week 7 guardrails review, 12 October 2026 | Bridget Bataringaya's branch, commit b50a1b3 | Four of five checks failed on the current code; all twelve passed with the fix |
| F4 | The run log overstated the median latency | Week 7 code review, 13 October 2026 | Version 0.5.0 | The regression test passed; the old rule fails it |
| F5 | Text with a stray half-character could not be remembered | Week 6 code review, 13 October 2026 | Version 0.4.0 | Both regression tests passed; the old call raises an error |

# 3. F1: Every Absent Document Reported as Present

**What happened.** The first prompt, v1.0, asked the model to find each checklist item in the submission. Across the 19 built-in evaluation cases it never once answered Not Found. Six cases concerned a document that was absent, and all six were reported Found. In case TG-02 the anti-bribery declaration, which the synthetic submission leaves out, was reported Found on page 7 at confidence 1.00 (Katongole, 2026a). The quoted text was real, but it was the conflict of interest declaration.

**Why.** Asked to find a document, the model always found the nearest passage. Nothing in the prompt made Not Found an answer it was expected to give.

**What was changed.** Prompt v2.0 added an ordered decision procedure, an identity test that separates the required document from a merely related one, an explicit statement that absence is an expected answer, and anchored confidence bands. Absent documents reported absent rose from 0 of 6 to 4 of 6, and cases meeting expectation from 15 of 19 to 17 of 19.

**Re-test.** The re-test of F2 below also re-tests F1. Of the two absent documents, one was reported Not Found and the other was sent for human review. Neither was reported present, and both documents that are present were found. With the evidence check switched off, prompt v2.0 alone reported both absent documents present, so the remaining protection against F1 for these two items is the fix for F2.

**Evidence.** docs/evaluation/evaluation-synthetic-submission.md (case TG-02); docs/weekly-reports/Week 2 Progress Report (Table 2); evidence/traces/failures/.

# 4. F2: A Missing Document Reported Present, Quoting a Different Document

**What happened.** Prompt v2.0 still failed on two of the six absent documents, cases EV-05 and EV-07. The anti-bribery declaration was again reported Found, quoting the conflict of interest declaration on page 7. The certificate of non-blacklisting was reported Found, quoting the certificate of registration on page 2. Both were given confidence 0.95 (Katongole, 2026a). This is the most serious error the system can make, because it hides a gap in the bid.

**Why.** Neither safeguard in the code could see it. The quotation check asks only whether the quoted text is in the submission, and it was. The confidence threshold of 0.85 asks only what the model claimed, and it claimed 0.95. Three rewordings of the prompt changed which passage was quoted, never whether one was. A model asked to search and to judge in the same call judges in favour of what it has just found.

**What was changed.** A second model call, the evidence check, was added for every item reported present (commit 17418ce). It is shown the requirement and the quoted passage, and never the submission. It must first name what the passage is, and only then say whether it satisfies the requirement. With nothing left to search, the question becomes a comparison.

**Re-test.** The same four items were checked twice on 19 October 2026: once as the system now stands, and once with the evidence check switched off. The checklist held two documents the submission contains, the tax clearance certificate and the conflict of interest declaration, and the two it lacks. Table 2 gives the results.

<!-- Table: F2 re-test, with the evidence check on and off -->
| Item | In the submission | Evidence check on | Evidence check off |
| --- | --- | --- | --- |
| CHK-02 Tax clearance certificate | Yes, page 3 | Found, page 3, 0.95 | Found, page 3, 0.95 |
| CHK-05 Anti-bribery declaration | No | Requires Human Review, 0.01 | Found, page 7, 0.95, quoting the conflict of interest declaration |
| CHK-08 Conflict of interest declaration | Yes, page 7 | Found, page 7, 0.90 | Found, page 7, 0.95 |
| CHK-10 Non-blacklisting certificate | No | Not Found | Found, page 2, 0.95, quoting the certificate of registration |
| Run time | | 1,123.7 seconds | 617.9 seconds |

With the fix switched off, the failure returned exactly as first recorded: both absent documents were reported present, on the same pages, quoting the same wrong passages. With the fix on, neither was reported present, and both documents that are present were still found.

The two absent items were stopped in different ways. For CHK-10 the evidence check named the quoted passage as a certificate of registration and rejected it, so the item was reported Not Found with the rejected passage named. For CHK-05 the evidence check named the passage as a director and shareholder declaration, yet judged it to be the required document. Its match score was 0.01, and the final confidence is the lower of the two calls' scores, so the item fell below the 0.85 threshold and went to a person. In Week 2 the same item was reported Not Found. The fix held, but on this run through the confidence floor and not through the verdict.

The run logs of both runs record twelve model calls with no failure: eight first-pass calls and four evidence checks. The median call took 142.8 seconds. The four evidence checks took 221.8 seconds in all. Most of the rest of the difference between the runs came from the first call of the first run, which took 384.3 seconds against 173.3 for the same call in the second.

**Evidence.** evidence/traces/failures/F2-retest-with-evidence-check.json and .log; evidence/traces/failures/F2-retest-fix-switched-off.json and .log; the run logs of both runs.

# 5. F3: The Oldest API Routes Accepted Anonymous Callers

**What happened.** The routes POST /check and POST /checklist/parse were written in Week 2, before the API had authentication. The routes added later all require an API key, but these two did not. Anyone who could reach the server could upload a submission and have it checked.

**Why.** Authentication was added route by route in Week 4. The two older routes were left as they were, and a code comment said so.

**What was changed.** Bridget Bataringaya added a check in front of both routes, on her branch (Bataringaya, 2026). A call with no key or an unknown key is refused with HTTP 401. A caller whose role may not analyse documents, such as a bidder, is refused with HTTP 403. If the key setting is broken, the routes refuse every call with HTTP 500 rather than open.

**Re-test.** Her tests were run on 19 October 2026 against two versions of the code. Table 3 gives the results.

<!-- Table: F3 re-test -->
| Test | Current shared code, without the fix | Bridget's branch, with the fix |
| --- | --- | --- |
| /check with no key is refused | Failed: HTTP 422, the call reached the upload check | Passed: HTTP 401 |
| /checklist/parse with no key is refused | Failed: HTTP 422 | Passed: HTTP 401 |
| /check with an unknown key is refused | Failed: HTTP 422 | Passed: HTTP 401 |
| /check by a bidder is refused | Failed: HTTP 422 | Passed: HTTP 403 |
| /check by an officer reaches input validation | Passed: HTTP 422 | Passed: HTTP 422 |
| Seven checks of existing guardrails | Not run | Passed |

With the fix, all twelve of her tests passed, and so did the whole suite of 442 tests on her branch. Her branch also merges with the current development branch without a conflict. The fix is not yet on the main branch.

**Evidence.** tests/test_legacy_auth.py and tests/test_guardrail_contract.py on the Bridget-Bataringaya branch; docs/week_7/Guardrails_Installation.md on the same branch.

# 6. F4: The Run Log Overstated the Median Latency

**What happened.** The run log's summary reports the median and the 95th percentile of model call times. For an even number of calls it picked the upper of the two middle values. For two calls of 1 and 2 seconds it reported a median of 2 seconds, and for six calls of 1 to 6 seconds it reported 4. When the Week 7 run logs were first summarised, the median model call was reported as 168.8 seconds.

**Why.** The rank was computed as round(fraction times count, plus a half). Python rounds a half to the nearest even number, so the rank came out one too high whenever the count was even.

**What was changed.** The rank is now the nearest rank, rounded up: ceiling(fraction times count). The summary in the observability document was recomputed and reported 168.2 seconds.

**Re-test.** The regression test test_percentiles_use_the_nearest_rank passed. Applied to the same test values, the old rule returns 2.0 and 4.0 where 1.0 and 3.0 are correct, so the test would have failed before the fix. This matters for Week 7, because latency is one of the six evaluation criteria and the run log is where it is measured.

**Evidence.** src/procurecheck/observability/commands.py (percentile); tests/test_observability.py.

# 7. F5: Text With a Stray Half-Character Could Not Be Remembered

**What happened.** Case history stores a fingerprint of each submission's text, so that a later run can tell whether the document changed. Text extracted from a damaged file can contain a lone surrogate, half of a character pair. The fingerprint could not be computed for such text, and the case was not remembered.

**Why.** The text was encoded as UTF-8 before hashing, and UTF-8 refuses a lone surrogate. Python raised UnicodeEncodeError.

**What was changed.** The text is encoded with the surrogatepass error handler, which keeps the stray code unit instead of refusing it. The fingerprint stays the same for every ordinary text.

**Re-test.** Both regression tests passed: one fingerprints text containing a lone surrogate, and one runs a whole workflow on such a document and confirms its case is remembered. Run on the same text, the old call still raises "surrogates not allowed".

**Evidence.** src/procurecheck/memory/store.py (fingerprint); tests/test_memory.py.

# 8. The Submitted Catalogue

The catalogue submitted for this task describes five failures: a clause split across two pages, legal boilerplate matched to the wrong affidavit, a compliance table flattened into text, a subcontractor's certificate accepted for the bidder, and a reference to an annexure that was not attached (Mwesigwa, 2026). Each is a real risk for a completeness checker, and three of them are close to failures this catalogue records. F2 is the boilerplate case, and F1 is the case of a document reported present because something like it was found.

The failures it records could not be traced to this system. It names test files, such as synthetic_tender_bid_04.pdf, that are not in the repository. Its fixes include a layout-aware chunker, a cross-encoder reranker, a table parser and a build check that runs on every pull request, and none of these exists in the code. Its error rates were not produced by any recorded run.

It is therefore read here as an analysis of failure modes to test for, not as a record of failures. Two of its cases are not yet covered by the evaluation set and should be added to it: a subcontractor's credential offered for the bidder, and a reference to an annexure that is missing.

# 9. Open Failure

The evaluation set found one further failure, which has not been fixed (Johnson, 2026). The Week 1 decision was that a report contains no score, percentage or grade. The report states a completeness percentage, for example Incomplete at 66.7%, and case history stores it. Scenario TC22 tests this rule and is expected to fail. Whether to remove the percentage or to change the rule is a team decision, and it should be taken before the evaluation set is run.

# 10. Reproducing the Re-tests

The live re-test of F1 and F2 is run from the repository root:

    python run.py check --checklist evidence/traces/failures/retest-checklist.csv --submission knowledge/samples/synthetic-submission.pdf --format json --out <file>
    python run.py check ... --no-evidence-check --out <file>

The second command switches the evidence check off, which reproduces the single-pass behaviour of F2. The first run took about 19 minutes on the development laptop and the second about 10. F4 and F5 are re-tested by the full test suite. F3 is re-tested on the Bridget-Bataringaya branch with:

    PYTHONPATH=src python -m pytest tests/test_legacy_auth.py tests/test_guardrail_contract.py

# References

Bataringaya, B. (2026). *Week 7 guardrails implementation* [Unpublished project code and document]. Group H (Evening), BSE4104, Makerere University.

Johnson, M. (2026). *Final evaluation set: 32 scenarios* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Katongole, J. (2026a). *Week 2 progress report* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Mwesigwa, I. (2026). *Failure catalogue: Five genuine technical failures and post-fix re-test verification* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.
