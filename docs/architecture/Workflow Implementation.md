---
title: Workflow Implementation
subtitle: The Multi-Step Completeness Workflow by Direct Orchestration
line: **Public Procurement Document-Completeness Agent (ProcureCheck)**
line: BSE4104 AI-Native and Agentic Engineering Capstone, Group H (Evening)
line: Week 5, ClickUp task 123tcvwhmcc
line: Version 0.3.1
---

[[TOC]]

[[TABLES]]

# 1. Purpose

This document describes how the multi-step workflow was implemented in Week 5. The task was to implement the workflow using direct orchestration or a framework. Direct orchestration was chosen: the application's own code runs the loop, and no agent framework was added.

# 2. The Task the Workflow Performs

The workflow takes one tender submission from upload to a report an officer can act on. The task needs several decisions in a row, and the right next step depends on what the last one found:

- Some items may come back Unclear, and those should be looked at again.
- Items that stay Unclear need a person to decide them.
- The model server may stop answering partway through.
- A report should reach the procurement record only after an officer signs it off.

The team's own definition of the task is a separate Week 5 task (123tcvwhmc6), and so are its loop design (123tcvwhmc7) and its limits (123tcvwhmca). This implementation used the course's loop pattern and set every limit as a parameter, so the team's choices can be adopted as configuration.

# 3. Why Direct Orchestration

In the Week 4 live run the model, left to choose its tools, checked the document correctly and then never called the report tool. Steps that must always happen, in an order that never changes, were therefore taken away from the model.

In this workflow the model does only what needs a language model: reading the submission inside the check tool. Choosing the next step is ordinary code. It is reproducible, it can be tested case by case, and a document cannot talk it out of a step. A framework was not needed for a loop of five actions, and it would have added a dependency the team would have to learn.

# 4. The Loop

## 4.1 One Iteration

Each iteration passes through the five stages in Table 1.

<!-- Table: The stages of one iteration -->
| Stage | Component | What happens |
| --- | --- | --- |
| Sense | WorkflowState.sense | The state is summarised: whether a check has run, the item counts, tickets open, whether a report exists, the last error |
| Plan / Decide | planner.decide | The next action is chosen from the state by fixed rules, with a written reason |
| Act | ToolExecutor.execute | The action's tool calls run through the Week 4 executor, with all its checks |
| Observe | state.observe | The results are folded into a new state; the old state is never edited |
| Stop or re-plan | planner.decide again | The next decision either continues, changes the plan after a failure, or stops |

Every tool call still passes through the executor. The workflow therefore inherits every Week 4 check: the tool must exist, the caller must be permitted, the arguments and answers must match their schemas, and a higher-impact action needs a person's sign-off.

## 4.2 The Planning Rules

The planner applies its rules in order. Table 2 lists them.

<!-- Table: Planning rules, in the order they are applied -->
| Order | Condition | Decision |
| --- | --- | --- |
| 1 | The publication was declined or failed | Stop with the report unpublished; never retried, so the officer is asked once |
| 2 | The last step was refused for permission | Stop; retrying cannot grant a permission |
| 3 | The last step failed because the model server was unavailable, and retries remain | Wait, then repeat the step |
| 4 | A re-check or the tickets failed | Drop that step and carry on |
| 5 | The check or the report failed | Stop; there is nothing to carry on with |
| 6 | No check has run | Check every checklist item |
| 7 | Items came back Unclear and re-check rounds remain | Check only those items again |
| 8 | Items are still Unclear | Open a review ticket for each |
| 9 | No report exists | Generate the report |
| 10 | Publication was asked for | Ask an officer to sign off, then publish |
| 11 | Otherwise | Stop; the report is ready, or published |

A re-check can only change the items it was asked about. The results for every other item are kept.

## 4.3 Limits

Table 3 gives the bounds every run stays inside. Each can be changed on the command line.

<!-- Table: Workflow limits and their defaults -->
| Limit | Default | Effect |
| --- | --- | --- |
| Maximum iterations | 7 | The run stops after this many acting iterations, whatever the plan says |
| Retries after an outage | 1 | A step that fails because the model server is down is repeated this many times |
| Retry delay | 5 seconds | The wait before a retry |
| Re-check rounds | 1 | How many times Unclear items are checked again |
| Approved tools | check, ticket, report, publish | A planned call to any other tool is never made |
| Publish | Off | Whether to ask for sign-off and publish at the end |

# 5. Stop Conditions and Hand-off

Every run ends by handing the case to a procurement officer. A report is advisory until an officer confirms it. Table 4 lists the ways a run can stop.

<!-- Table: How a run can stop -->
| Stop reason | When | What the officer is told to do |
| --- | --- | --- |
| report_ready | The report exists and was not published | Chase each missing item, resolve each ticket, sign off the report |
| published | An officer signed off and the report went on the record | Chase each missing item and resolve each ticket |
| not_published | Publication was asked for but declined or failed | As for report_ready; the report is not on the record |
| unauthorized | The caller's role may not run a step | Ask a procurement officer to run the workflow |
| service_unavailable | The model server stayed down after the retries | Start it and run again; nothing was recorded as checked |
| tool_failed | The check or the report failed for another reason | Check the submission by hand |
| iteration_limit | The run used all its iterations | Read the trace, then finish by hand or run again |
| tool_not_approved | The plan needed a tool outside the approved list | Check the submission by hand |

Unclear items reach the officer twice: as review tickets, and in the report's list of unclear items. If the tickets could not be opened, the hand-off lists those items to be flagged by hand.

# 6. Traces

Every run writes a trace to evidence/traces/workflow/. For each iteration it records what was sensed, the decision and its reason, each tool call with its arguments, result and time, and the outcome. The trace also records the version, the limits, the caller, the tickets, the report, any publication and the hand-off. Long text such as the submission is shortened in the trace.

# 7. Using It

The workflow is run from the command line:

    python run.py workflow --submission FILE [--checklist FILE] [--publish]

The command exits with 0 when the report is ready or published, 1 when the run was refused or failed, 2 when the model server stayed down, and 4 when a publication was asked for but not made.

It is also available as POST /workflow, which returns the whole trace. The API cannot ask a person for sign-off during a request, so it does not publish.

# 8. Verification

## 8.1 Automated Tests

The workflow was verified by 42 automated tests, run against a scripted model so each case is repeatable. Thirty-one test the planner and the loop, and eleven test the command and the API route. Table 5 lists what they cover. Ten more tests cover the review ticket tool, and 36 cover the approval gate. The full suite of 339 tests passed, and coverage of the tools and workflow packages was 99%.

<!-- Table: What the workflow tests cover -->
| Area | Cases |
| --- | --- |
| Normal run | Check, then report, then stop; the report is never skipped; every iteration records sense, plan, act and observe |
| Re-plan on Unclear items | An item settled by the re-check needs no ticket; an item still Unclear gets one; the re-check asks only about Unclear items and keeps the rest |
| Recovery | An outage is retried after a wait and the run recovers; a lasting outage stops after the retry budget; a failed re-check is dropped and the first results kept; tickets that cannot be opened are listed for flagging by hand |
| Stops | A bidder, a committee member and an anonymous caller are refused at the first step; the iteration limit holds; an unapproved tool is never called; an empty document ends as a tool failure; a fault inside the loop still ends in a hand-off |
| Input | Blank and repeated checklist lines are dropped, so a repeated line no longer breaks the report |
| Entry points | The command writes its trace and prints the hand-off, with the right exit code for each stop; the API returns the trace, refuses a bidder with 403 and an anonymous caller with 401 before reading the upload, and refuses an upload over the size cap with 413 |

A code review of the workflow found no infinite loop, retry-counting error or off-by-one in the iteration limit. It did find five weaknesses, all fixed before release: a declined publication read as a success, anonymous uploads were parsed before identity was checked, a repeated checklist line failed the run late, a fault inside the loop could escape as a crash, and the iteration-limit hand-off did not mention a report already made.

## 8.2 Run Against the Real Model

The workflow was run once against the real model, Meta Llama 3.1 8B through Ollama on a CPU-only laptop. It used the synthetic submission and the same three checklist items as the Week 4 live run, with --publish, and no one at the terminal. Table 6 gives the iterations.

<!-- Table: Live workflow run, unattended, with publishing requested -->
| Iteration | Action | Outcome | Seconds |
| --- | --- | --- | --- |
| 1 | Check all 3 items | Success: 2 present, 1 missing, none unclear | 523.9 |
| 2 | Generate the report | Success: Incomplete, 66.7% present | 0.0 |
| 3 | Publish, after sign-off | Declined: no answer was given; nothing published | 0.0 |

The run stopped as not_published with exit code 4. The hand-off asked the officer to locate or request the anti-bribery declaration, and to sign off and publish the report once reviewed. The trace and log are in evidence/traces/workflow/.

The check gave the same result as in Week 4: the tax clearance certificate and the conflict of interest declaration present, the anti-bribery declaration missing. This time the report was generated, because it was a step of the plan rather than a choice left to the model. That closes the gap found in the Week 4 live run.

One observation concerned the sign-off prompt. The run's input was the Windows null device, which Windows reports as a terminal, so the prompt was shown and read. Reading it returned no answer, and the action was declined. The gate still failed closed, but the decline was recorded as no answer rather than as no terminal.

# 9. Open Work

- The team's task definition, loop design and limits (123tcvwhmc6, 123tcvwhmc7, 123tcvwhmca) should be compared with this implementation and adopted as configuration.
- At temperature 0 a re-check sends the same question again, so it mostly helps when the first answer was unusable. Its benefit should be measured on real Unclear items.
- Makmot Johnson's Week 5 task is to capture at least three execution traces, including a failure and recovery case. The workflow writes traces in the form that task needs.
- On Windows the terminal check should confirm a real console, since the null device also reports itself as a terminal.
- A signed-off publication has been tested only with a scripted approver. A live run with an officer at the terminal is still to be recorded.

# References

Johnson, M. (2026). *Third tool specification: create_review_ticket* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Katongole, J. (2026). *Tool calling implementation* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.
