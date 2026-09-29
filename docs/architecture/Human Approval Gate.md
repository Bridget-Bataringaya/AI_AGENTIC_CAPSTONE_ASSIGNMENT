---
title: Human Approval Gate
subtitle: Human Sign-off Before a Higher-Impact Action
line: **Public Procurement Document-Completeness Agent (ProcureCheck)**
line: BSE4104 AI-Native and Agentic Engineering Capstone, Group H (Evening)
line: Week 4, ClickUp task 123tcvwfnzg
line: Version 0.3.1
---

[[TOC]]

[[TABLES]]

# 1. Purpose

This document describes the human approval step added to ProcureCheck in Week 4. The requirement was that a person must approve any higher-impact action before it runs.

The step was built into the tool executor, which every tool call already passes through. A call that needs approval therefore cannot reach its tool by any route without it: not from the model, not from the workflow, not from the API.

# 2. Which Action Is Higher-Impact

The team's AI Boundary Matrix (Week 1) sorted every task into four categories. Two tasks fell under Human Approval Required: deciding unclear items, and report sign-off. The matrix states that a completeness report cannot be added to the official procurement record, or sent to the evaluation committee, without explicit sign-off from an authorised officer.

Adding a report to the record is the step that makes it official. From then on the evaluation committee works from it. A wrong report on the record could send a complete bid to evaluation with a document missing, or hold back a complete one. Every other tool only reads, calculates or drafts. Table 1 shows how each tool was classed.

<!-- Table: Tools by impact and the control applied -->
| Tool | What it changes | Impact | Control |
| --- | --- | --- | --- |
| check_document_completeness | Nothing; it reads the submission | Low | Role permission |
| generate_completeness_report | Nothing; it counts results | Low | Role permission |
| create_review_ticket | Adds a draft note to the session's review queue | Low | Role permission; the agent cannot resolve a ticket |
| publish_completeness_report | Adds the report to the procurement record | Higher | Role permission and a person's sign-off |

publish_completeness_report was added for this task. Its record is simulated: an append-only store held for the session, like the review queue. No real procurement system is touched. The control around it is real.

# 3. How the Gate Works

## 3.1 Place in the Executor

The executor applies its checks in a fixed order. The approval check was inserted after the arguments are validated and before the tool runs. Table 2 gives the order.

<!-- Table: Checks applied by the tool executor, in order -->
| Order | Check | Error code on failure |
| --- | --- | --- |
| 1 | The tool exists | UNKNOWN_TOOL |
| 2 | The caller holds the tool's permission | UNAUTHORIZED |
| 3 | The arguments match the input schema | MISSING_PARAMETER or INVALID_ARGUMENTS |
| 4 | A person with sign-off rights approves, if the tool requires it | APPROVAL_REQUIRED or APPROVAL_DENIED |
| 5 | The tool runs | The tool's own code |
| 6 | The answer matches the output schema | UNEXPECTED_TOOL_RESPONSE |

The order matters. A caller without permission is refused before anyone is disturbed. Malformed arguments are refused before a person is asked to approve something that could not run.

## 3.2 The Question the Person Sees

The person is shown what will happen in words, not the raw arguments. For a report, the question names the document, its overall status, the percentage present, and the missing and unclear items. It also states that a published report is never overwritten. The officer types APPROVE to sign off. Any other answer declines.

The question is put only at an interactive terminal. An answer piped in by a script is never read, so a run cannot approve itself. Text taken from a filename or a checklist has its control characters removed before it is shown, so it cannot draw a false status line beneath the real one.

## 3.3 Failing Closed

Every outcome other than a clear yes from an authorised person refuses the action. Table 3 lists them.

<!-- Table: Outcomes of an approval request -->
| Situation | Result | Record changed |
| --- | --- | --- |
| An officer signs off | The report is published and names who signed off | Yes |
| No approver is available | APPROVAL_REQUIRED | No |
| The approver declines | APPROVAL_DENIED | No |
| The terminal gets no answer | APPROVAL_DENIED | No |
| The answer is piped in by a script, not typed at a terminal | APPROVAL_DENIED | No |
| A yes comes from someone without sign-off rights | APPROVAL_DENIED | No |
| The approval step itself fails | APPROVAL_REQUIRED | No |

Sign-off rights were given to the procurement officer role only, following the Boundary Matrix. An evaluation committee member, a bidder or a guest cannot approve.

The publishing tool also checks the approval itself, including that the approver holds sign-off rights. If it were ever called some other way than through the executor, it would still refuse.

## 3.4 What Is Recorded

Every decision is kept on the tool result, and so in every trace: whether it was approved, who decided, their role, a note and the time. A published record carries the identifier of the officer who signed off.

## 3.5 What the Model Can Do

Nothing. The publishing tool is never offered to the model. If the model names it anyway, the agent answers that no such tool is available and nothing is asked or run.

# 4. The Record

The simulated procurement record keeps one report per submission. The same report sent twice returns the first record, so a retried step publishes nothing twice. A different report for a submission already on the record is refused as ALREADY_PUBLISHED. A published report is never overwritten.

Before publishing, the tool checks that the report is consistent. A report whose percentage disagrees with its own lists of items is refused as INVALID_RESULTS.

# 5. Where It Is Used

The workflow command asks for sign-off when run with --publish. The report is generated first, then the officer at the terminal is asked. A decline, or any other failure to publish, stops the run as not_published with exit code 4, so a script can tell it apart from a publication. It is never retried, so the officer is never asked twice. The report is kept in the trace, and the hand-off says it is not on the record.

The API has no person to ask during a request, so a publish call through the API ends as APPROVAL_REQUIRED, with HTTP status 428. An approval queue that an officer could answer later through the API is open work.

# 6. Verification

The gate was verified by automated tests in tests/test_approval.py. They cover each outcome in Table 3, the order of the checks, the question shown, the record rules, the terminal approver and the workflow step. All 31 passed. Five more tests ran the gate end to end: sign-off and decline at the terminal, an approval piped in by a script, a run without --publish that never asked anyone, and a publish call through the API, refused with HTTP 428. The full suite of 339 tests passed, and coverage of the tools and workflow packages was 99%. In no test did a report reach the record without an officer's sign-off.

A code review of the gate found no route to publish without an approval through the executor. It found two weaknesses, both fixed before release, each with a regression test:

- The publishing tool's own check accepted an approval from someone without sign-off rights, if the tool was called directly.
- An approval piped in by a script counted as a person's sign-off.

A run live against the real model, left unattended with --publish, is reported in the workflow implementation document.

# 7. Open Work

- An approval queue for the API, so a request can wait for an officer's decision instead of being refused.
- Separation of duties: the officer who runs a check may currently also sign it off. A second officer could be required.
- Deciding unclear items, the matrix's other Human Approval Required task, is still done outside the system, through the review tickets.
- A real procurement record in place of the simulated one, with its own audit log.

# References

Bataringaya, B. (2026). *Tool / function specification for the Public Procurement Document Completeness Agent* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Group H (Evening). (2026). *Public Procurement Completeness Agent: AI boundary matrix* [Unpublished project document]. BSE4104, Makerere University.

Johnson, M. (2026). *Third tool specification: create_review_ticket* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.
