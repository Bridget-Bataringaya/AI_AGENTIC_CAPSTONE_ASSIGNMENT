---
title: Workflow Execution Traces
subtitle: Six Recorded Runs, Including Failure and Recovery
line: **Public Procurement Document-Completeness Agent (ProcureCheck)**
line: BSE4104 AI-Native and Agentic Engineering Capstone, Group H (Evening)
line: Week 5, ClickUp task 123tcvwhmcf
line: Versions 0.3.1 and 0.4.0
---

[[TOC]]

[[TABLES]]

# 1. Purpose

This document records the execution traces captured for the Week 5 workflow. The task was to capture at least three execution traces, including one failure and recovery case. Six were captured. Two show a failure, and one of those shows the run recovering by itself.

Each trace is set out the same way: what had to happen, what the workflow did at each iteration, and whether the two agree.

# 2. How a Trace Is Captured

Every run of the workflow command writes a trace file. No extra step is needed. For each iteration the trace records four things:

- Sense: the state the decision was made from.
- Plan: the action chosen, with a written reason.
- Act: each tool call, with its arguments, result and time.
- Observe: whether each call succeeded, or its error code.

The trace also records the version, the limits in force, the caller's role, the stop reason and the hand-off. A log of what the operator saw at the terminal is kept beside each trace.

All six runs used the real model, Meta Llama 3.1 8B through Ollama on a CPU-only laptop. Five used the same three checklist items: a tax clearance certificate, an anti-bribery declaration and a conflict of interest declaration. The synthetic submission holds the first and third and omits the second.

# 3. Summary of the Traces

Table 1 lists the six traces. The files are in evidence/traces/workflow/ and evidence/traces/memory/.

<!-- Table: The six recorded traces -->
| Trace | File | Kind | Iterations | Stop reason | Seconds |
| --- | --- | --- | --- | --- | --- |
| T1 | workflow/live-01-officer-unattended-publish-refused | Normal run, then a declined sign-off | 3 | not_published | 523.9 |
| T2 | workflow/live-02-outage-retried-and-recovered | Failure and recovery | 3 | report_ready | 623.7 |
| T3 | workflow/live-03-backend-error-stopped-safely | Failure, stopped safely | 2 | service_unavailable | 63.4 |
| T4 | workflow/live-04-bidder-refused | Refused caller | 1 | unauthorized | 0.0 |
| T5 | memory/live-01-first-check | Normal run | 2 | report_ready | 507.6 |
| T6 | memory/live-02-resubmission-compared | Normal run on a resubmission | 2 | report_ready | 672.5 |

# 4. The Traces

## 4.1 T1: Normal Run With a Declined Sign-off

**What had to happen.** The workflow had to check every item, generate the report, and ask an officer to sign off before publishing. With nobody at the terminal, nothing had to be published.

**What happened.** Table 2 gives the iterations.

<!-- Table: Trace T1, iteration by iteration -->
| Iteration | Sensed | Decision and reason | Outcome | Seconds |
| --- | --- | --- | --- | --- |
| 1 | No check has run | Check all 3 items | Success: 2 present, 1 missing | 523.9 |
| 2 | Checked, no report | Generate the report | Success: Incomplete, 66.7% | 0.0 |
| 3 | Report ready, publishing asked for | Ask an officer to sign off, then publish | APPROVAL_DENIED: no answer was given | 0.0 |

The run stopped as not_published. The hand-off asked the officer to locate the anti-bribery declaration, and to sign off and publish the report once reviewed.

**Agreement.** The run did what it had to. The declined publication was not retried, so the officer was asked once.

## 4.2 T2: Failure and Recovery

**What had to happen.** The model server was unreachable when the run started. The workflow had to report the failure, wait, and repeat the step once. If the server had returned, the run had to carry on to its report as if nothing had failed.

**How the failure was produced.** The outage was induced. The workflow was pointed at a local address with nothing listening. Fifteen seconds later a forwarder to the real model server was started on that address. From the workflow's side, the server came back during its 45-second wait. The script is tests/evaluation/run_outage_recovery.py. Everything after the outage was real.

**What happened.** Table 3 gives the iterations.

<!-- Table: Trace T2, iteration by iteration -->
| Iteration | Sensed | Decision and reason | Outcome | Seconds |
| --- | --- | --- | --- | --- |
| 1 | No check has run | Check all 3 items | SERVICE_UNAVAILABLE | 2.2 |
| 2 | Last step failed as SERVICE_UNAVAILABLE | Wait 45 seconds, then repeat the check; retry 1 of 1 | Success: 2 present, 1 missing | 576.5 |
| 3 | Checked, no report | Generate the report | Success: Incomplete, 66.7% | 0.0 |

The run stopped as report_ready with exit code 0, after 623.7 seconds in all. The hand-off asked the officer to locate the anti-bribery declaration and to sign off the report.

**Agreement.** The run did what it had to. The failure was reported in the trace with its error code, not hidden. The retry was the same step, made once, after the wait. The outage cost the run 47 seconds: 2.2 seconds to fail and 45 to wait. The result was the same as in T1 and T5, so the failure left no mark on the findings.

## 4.3 T3: Failure, Stopped Safely

**What had to happen.** The model server answered with an error. The workflow had to retry once. If the retry also failed, it had to stop without recording any item as checked, and tell the officer what to do.

**How the failure was produced.** This failure was not induced. On 6 October 2026 the Ollama server returned HTTP 500 to the first requests of a run. It was loading the model at the time, with little free memory.

**What happened.** Table 4 gives the iterations.

<!-- Table: Trace T3, iteration by iteration -->
| Iteration | Sensed | Decision and reason | Outcome | Seconds |
| --- | --- | --- | --- | --- |
| 1 | No check has run | Check all 3 items | SERVICE_UNAVAILABLE | 40.7 |
| 2 | Last step failed as SERVICE_UNAVAILABLE | Repeat the check; retry 1 of 1 | SERVICE_UNAVAILABLE | 17.6 |

The retry budget of one was then spent. The run stopped as service_unavailable with exit code 2. The hand-off read: the model backend stayed unavailable after 1 retry; start it and run the workflow again; no item has been recorded as checked.

**Agreement.** The run did what it had to. No report was produced and no status was invented. The officer followed the hand-off: the run was repeated eight minutes later, once the server answered, and that repeat is trace T5. Recovery here was by a person, as the hand-off intended.

## 4.4 T4: Refused Caller

**What had to happen.** A bidder must not be able to run a completeness check. The workflow had to refuse at the first step and not retry, since a retry cannot grant a permission.

**What happened.** The run made one iteration. The check was planned and the executor refused it as UNAUTHORIZED in under a tenth of a second. The planner then stopped the run, with the reason that the caller may not check and that retrying cannot change that. The run ended as unauthorized with exit code 1. The hand-off told the caller to ask a procurement officer to run the workflow.

**Agreement.** The run did what it had to. The submission was never sent to the model.

## 4.5 T5: Normal Run

**What had to happen.** The workflow had to check every item, generate the report and stop, with the report ready for the officer.

**What happened.** Table 5 gives the iterations.

<!-- Table: Trace T5, iteration by iteration -->
| Iteration | Sensed | Decision and reason | Outcome | Seconds |
| --- | --- | --- | --- | --- |
| 1 | No check has run | Check all 3 items | Success: 2 present, 1 missing | 507.6 |
| 2 | Checked, no report | Generate the report | Success: Incomplete, 66.7% | 0.0 |

The run stopped as report_ready. The hand-off asked the officer to locate the anti-bribery declaration and to sign off the report.

**Agreement.** The run did what it had to. Its result matched T1 and the Week 4 live run: the same two items present and the same one missing.

## 4.6 T6: Normal Run on a Resubmission

**What had to happen.** The submission was checked again after the missing declaration was added. The workflow had to find all three items and report the submission complete.

**What happened.** The run took the same two steps as T5. The check took 672.5 seconds and found all three items. The report read Complete, 100.0%. The run stopped as report_ready, and the hand-off asked only for sign-off.

**Agreement.** The run did what it had to. The model found the added declaration, which it had correctly reported missing in T5.

# 5. Observations

- The planner's reasons made each trace readable without the code. Every decision in the six traces states why it was taken.
- The two failures ended differently, as designed. A server that returned within the retry wait cost the run under a minute. A server that stayed down stopped the run with nothing recorded as checked.
- No trace shows a retry of a refused step. A permission failure and a declined sign-off were each final.
- The check gave the same result for the same submission in T1, T2 and T5, across two versions and two file formats.
- Check times varied between 507.6 and 672.5 seconds for three items on the same machine. The model's speed on a CPU depends on what else the machine is doing.
- No trace exercises the re-check of Unclear items or the review tickets. The model returned no Unclear item in these runs. Those paths are covered by the automated tests, which use a scripted model.

# 6. Reproducing the Traces

    python run.py workflow --submission knowledge/samples/synthetic-submission.txt --checklist evidence/traces/workflow/live-checklist.txt
    python run.py workflow --submission knowledge/samples/synthetic-submission.pdf --checklist evidence/traces/workflow/live-checklist.txt --publish
    python tests/evaluation/run_outage_recovery.py
    python run.py workflow --submission knowledge/samples/synthetic-submission.txt --checklist evidence/traces/workflow/live-checklist.txt --role bidder

A trace is written to evidence/traces/workflow/ unless --trace names another file.

# References

Katongole, J. (2026). *Workflow implementation* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Katongole, J. (2026). *Persistent memory implementation* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.
