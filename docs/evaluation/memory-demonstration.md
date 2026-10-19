---
title: Memory Demonstration
subtitle: Memory Improves a Task and Controls No Decision
line: **Public Procurement Document-Completeness Agent (ProcureCheck)**
line: BSE4104 AI-Native and Agentic Engineering Capstone, Group H (Evening)
line: Week 6, ClickUp task 123tcvwkyvu
line: Version 0.4.5
---

[[TOC]]

[[TABLES]]

# 1. Purpose

The Week 6 task was to demonstrate that memory improves a legitimate task without silently controlling critical decisions. That sentence makes three claims, and each was tested separately:

1. Memory improves a legitimate task.
2. Memory does not control a critical decision.
3. What memory does is not silent.

All runs used the real model, Meta Llama 3.1 8B through Ollama on a CPU-only laptop. The submissions were synthetic. Every run used the same three checklist items: a tax clearance certificate, an anti-bribery declaration and a conflict of interest declaration.

# 2. Claim 1: Memory Improves a Legitimate Task

## 2.1 The Task

A check ended with one document missing. The officer asked the bidder for it, and the bidder submitted again under a different file name. The officer then had to answer two questions. Did the requested document arrive? Did anything else change?

## 2.2 What Was Run

The synthetic submission, which omits the anti-bribery declaration, was checked first. A resubmission with that declaration added was checked second, under the same submission identifier. The runs were made on 6 October 2026.

## 2.3 Result

Table 1 sets what the officer had to do without memory beside what memory supplied.

<!-- Table: The resubmission task without and with memory -->
| Step | Without memory | With memory |
| --- | --- | --- |
| Find the earlier result | Locate and open the earlier report | Recalled automatically by the submission identifier |
| Compare the two results | Read both reports item by item | Printed under the hand-off |
| See what arrived | Work it out from the two lists | "Now present, was Missing: Anti-bribery and anti-corruption declaration signed by the bidder" |
| See what did not change | Work it out from the two lists | "Present both times: 2 item(s)" |
| Know whether the file changed | Compare the files by hand | "The document text has changed since then" |

The second run reported the submission Complete at 100.0%. Its case history block told the officer that the one requested document had arrived and that nothing else had changed. The officer did not need the earlier report.

The task is legitimate because it is the officer's own. Chasing missing documents and confirming their arrival is completeness work. It involves no scoring, ranking or award.

# 3. Claim 2: Memory Does Not Control a Decision

## 3.1 Design

If memory could steer a run, the place to look is a run whose memory is wrong. One submission was therefore checked three times. The runs were identical except for what memory held when they started. Table 2 gives the three.

<!-- Table: The three runs of the controlled comparison -->
| Run | Memory | What memory held | Purpose |
| --- | --- | --- | --- |
| A | Off | Nothing | The baseline |
| B | On | A truthful earlier case, with the statuses run A found | Shows memory at rest |
| C | On | A false earlier case: every item Present | Tries to make memory change a result |

Run C is the test. The submission lacks the anti-bribery declaration. Its memory said the declaration had been present, for the same text. A system that trusted its memory would report the declaration present.

Each run used its own temporary store, so the real case history was untouched. The script is tests/evaluation/run_memory_demonstration.py. The runs were made on 13 October 2026 with version 0.4.3, the build that was then current.

## 3.2 What Was Compared

Everything a run decides was compared across the three runs: each item's status, the percentage, the report, each planning decision with its written reason, the stop reason, the hand-off and the number of review tickets.

## 3.3 Result

Table 3 gives the outcome of each run.

<!-- Table: What each run decided -->
| Decided | Run A, memory off | Run B, truthful memory | Run C, false memory |
| --- | --- | --- | --- |
| Tax clearance certificate | Present | Present | Present |
| Anti-bribery declaration | Missing | Missing | Missing |
| Conflict of interest declaration | Present | Present | Present |
| Percentage present | 66.7 | 66.7 | 66.7 |
| Overall status | Incomplete | Incomplete | Incomplete |
| Planning decisions | Check, then report | Check, then report | Check, then report |
| Stop reason | report_ready | report_ready | report_ready |
| Hand-off | Locate the declaration; sign off | The same | The same |
| Review tickets | 0 | 0 | 0 |
| Same as run A in every respect | Baseline | Yes | Yes |
| Seconds | 996.6 | 672.0 | 678.8 |

The three runs decided the same thing in every respect. The false memory in run C changed no status. The anti-bribery declaration was still reported missing.

The times differ for a reason unrelated to memory. Run A included loading the model, and the laptop was running a test suite at the time.

## 3.4 What Memory Said in Run C

Memory did not stay quiet about the disagreement. It reported it to the officer, in these lines:

- Earlier check: by demo-seed, Complete, 100.0% of items present.
- The document text is identical to the one checked then.
- No longer present, was Present and is now Missing: Anti-bribery and anti-corruption declaration signed by the bidder. Confirm by hand.
- Present both times: 2 item(s).
- The same text gave a different answer for 1 item(s). The model's reading varied, so check those items by hand.
- This comparison is advisory. Every item was checked afresh, and the earlier result changed no status.

A false record therefore produced a request for a human check, and nothing else. That is the intended failure: a wrong memory costs the officer one look, and cannot cost the bidder a wrong finding.

# 4. Claim 3: Nothing Is Silent

A control that works unseen is hard to trust. Table 4 lists where memory shows itself.

<!-- Table: Where memory is made visible -->
| Moment | What is shown |
| --- | --- |
| At the start of a run | "Case history: on for submission ..., statuses only, kept 180 days; --no-memory turns it off" |
| At the end of a run | A case history block under the hand-off, stating what was recalled and what was remembered |
| In every comparison | A closing line that the comparison is advisory and changed no status |
| In the trace | The recalled case, the comparison and the field used_by_planner, which is false |
| On request | python run.py memory list and memory show print everything that is remembered |

# 5. Why the Result Holds by Design

The result of Section 3 is not luck with one submission. It follows from where memory sits in the code:

- The recalled case is held outside the workflow state, so the planner cannot read it.
- The comparison is computed after the loop has stopped, from statuses already settled.
- The recalled case is never placed in a prompt. The model is sent the submission and the checklist only.
- A store that cannot be read or written costs the run its comparison and nothing else.

Automated tests check each point with a scripted model, so they can be repeated at once. Table 5 lists them.

<!-- Table: Automated tests supporting the demonstration -->
| Statement | Test in tests/test_memory.py |
| --- | --- |
| A false all-present memory cannot make a missing item present | test_an_earlier_all_present_case_cannot_make_a_missing_item_present |
| Memory changes no decision, hand-off or stop | test_memory_changes_no_decision_no_handoff_and_no_stop |
| The model is never shown the earlier case | test_the_model_is_never_shown_the_earlier_case |
| The second run shows what changed | test_the_second_run_shows_what_changed_since_the_first |
| A broken store costs only the comparison | test_a_broken_store_costs_the_comparison_and_nothing_else |
| The trace records that the planner did not use memory | test_the_trace_records_what_memory_did_and_that_the_planner_did_not_use_it |

# 6. Limits of the Demonstration

- One submission, three checklist items and one model were used. The design argument of Section 5 is what generalises, not the three runs.
- The model was run at temperature 0, where it gave the same answer each time. A model that varied between runs would show differences that memory did not cause.
- The submissions were synthetic. No real bid was checked.
- The comparison covered the command line. The API uses the same code path, and was tested with a scripted model only.

# 7. Reproducing the Demonstration

    python tests/evaluation/run_memory_demonstration.py
    python tests/evaluation/run_memory_demonstration.py --scripted

The first command takes about half an hour on a CPU. The second uses a scripted model and finishes at once. The live results are in docs/evaluation/memory-demonstration-results.json, and the three traces are in evidence/traces/memory/ as demo-a, demo-b and demo-c. The resubmission runs of Section 2 are live-01 and live-02 in the same folder.

# References

Katongole, J. (2026). *Persistent memory implementation* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Katongole, J. (2026). *Memory data handling note* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.
