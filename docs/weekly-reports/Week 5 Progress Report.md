---
title: Week 5 Progress Report
subtitle: A Bounded Multi-Step Workflow
line: **Public Procurement Document-Completeness Agent (ProcureCheck)**
line: BSE4104 AI-Native and Agentic Engineering Capstone
line: Group H (Evening)
line: Jonathan Katongole, Makmot Johnson, Isaac Mwesigwa, Bataringaya Bridget
line: School of Computing and Informatics Technology, Makerere University
line: Reporting period: 30 September to 6 October 2026
---

[[TOC]]

[[TABLES]]

# Abstract

**Introduction.** Week 5 aimed to turn the completeness check into a bounded multi-step workflow. **Methods.** One task that needs several decisions was defined. A loop of sense, plan, act, observe and stop or re-plan was designed. A task contract set the limits, the approved tools, the stop conditions and the points of human hand-off and approval. The workflow was implemented by direct orchestration, with the application choosing every step. Six execution traces were captured against the real model. **Results.** All 42 workflow tests passed, within a suite of 339. Six traces were recorded. One run recovered by itself from an outage of the model server. One stopped safely when the server stayed down, with no item recorded as checked. The check gave the same result for the same submission in three runs. **Conclusion.** Every run ended inside its limits and in a hand-off to an officer. The implemented task was simpler than the task the team defined, and that gap is the main work remaining.

# 1. Introduction and Objectives

ProcureCheck checks a tender submission against a procurement checklist. It reports which required documents are present, missing or in need of human review. It never scores, ranks or recommends an award.

In Week 4 the model was given tools and allowed to choose among them. It checked the document correctly and then skipped the report. Week 5 therefore asked a different question. How should a task of several steps be run, so that no step is skipped? How is a run kept from going on for ever?

The objectives for Week 5 were:

1. To define one task that genuinely benefits from multi-step decision making.
2. To design the loop: sense or context, plan or decide, act or tool, observe, and stop or re-plan.
3. To set the maximum iterations, the approved tools, the stop conditions and the human hand-off and approval conditions.
4. To implement the workflow using direct orchestration or a framework.
5. To capture at least three execution traces, including one failure and recovery case.

Table 1 gives the five tasks, who was assigned each, and what was delivered.

<!-- Table: Week 5 tasks, assignment and deliverable -->
| Objective | Assigned to | Deliverable |
| --- | --- | --- |
| 1. Task definition | Isaac Mwesigwa | Multi-step decision task definition |
| 2. Loop design | Bataringaya Bridget | Agent workflow document |
| 3. Limits and conditions | Isaac Mwesigwa and Bataringaya Bridget | Agent task contract |
| 4. Implementation | Jonathan Katongole | The workflow package, its tests and a design document |
| 5. Execution traces | Makmot Johnson | Six traces and a trace document, captured by Jonathan Katongole |

# 2. Background

An agent loop lets a system act, look at the result and decide again. The ReAct pattern showed that a language model could interleave reasoning with actions in such a loop (Yao et al., 2023). The loop gives flexibility, and it also gives the model control of the order of work.

That control is not always wanted. Schluntz and Zhang (2024) separate workflows, where code fixes the path, from agents, where the model directs itself. They advise the simplest design that works, and keeping the model's freedom for tasks that need it. A completeness check has steps that must always happen in the same order, which places it nearer the workflow end.

Long documents add a second pressure. Models use information at the start and end of a long context better than information in the middle (Liu et al., 2024). Splitting a task into narrow steps keeps each model call small, which the team's task definition relied on.

# 3. Methodology and Procedure

## 3.1 The Task Definition

The task defined was conditional and cross-referenced requirement verification (Mwesigwa, 2026). Two features make it a task of several steps. First, some requirements apply only to some bidders. A joint venture agreement is required of a consortium and not of a single company. Second, a document can point to another. A power of attorney may rest on a board resolution in an annexure many pages away.

The definition set out six steps. The checklist rules are formalised and the bidder is classified. Candidate clauses are retrieved, and each is grounded and searched for cross-references. Each cross-reference is followed, and the status is assigned. A safety boundary was stated for every step. The definition also named the failure it was designed to prevent. A mention of an annexure in a summary can be taken as proof that the annexure is attached.

## 3.2 The Loop Design

The loop was designed in five stages (Bataringaya, 2026a). Sense establishes the document, the checklist and a working state. Plan selects the next necessary action from that state. Act runs one approved tool. Observe records the result in the state before any further decision. Stop or re-plan ends the run when every check is done, or chooses another permitted action after a failure.

The design bounded the loop. A failure could be re-planned at most three times. Only approved tools could be used. The agent could not invent information, and anything it could not verify had to be reported as uncertain.

## 3.3 The Task Contract

The task contract fixed the controls in one place (Mwesigwa and Bataringaya, 2026). Table 2 summarises it.

<!-- Table: Controls set by the task contract -->
| Control | Rule set by the contract |
| --- | --- |
| Maximum iterations | Three action or re-plan attempts after a processing failure |
| Approved tools | Document content extraction and document completeness checking |
| Successful stop | All required completeness checks are done |
| Failure stop | The attempt limit is reached, or reliable processing is no longer possible |
| Human hand-off | Unresolved ambiguity, repeated failure, a missing or unclear rule, or an action outside scope |
| Human approval | Before findings are used for any official procurement decision |

## 3.4 The Implementation

The workflow was implemented by direct orchestration (Katongole, 2026a). The application's own code ran the loop and no agent framework was added. The model did one thing only: it read the submission inside the check tool. Choosing the next step was ordinary code.

The planner was a pure function of the state. It applied fixed rules in order and wrote a reason for each decision. There were five actions. Every item was checked. Items that came back Unclear were checked again. A review ticket was opened for each item still Unclear. The report was generated. It was published only after an officer's sign-off. Every tool call passed through the Week 4 executor, so each kept its permission, argument and approval checks.

After a failure the planner re-planned. An outage of the model server was retried after a wait. A failed re-check or failed tickets were dropped, and the run carried on with what it had. A refused permission and a declined sign-off were never retried.

## 3.5 The Traces

Every run wrote a trace. For each iteration it recorded what was sensed, the decision and its reason, each tool call with its result and time, and the outcome. Six runs against the real model were recorded (Katongole, 2026b). The model was Meta Llama 3.1 8B through Ollama on a CPU-only laptop.

One failure was induced. The workflow was pointed at an address with nothing listening, and a forwarder to the model server was started fifteen seconds later. The second failure was not induced: the model server returned errors while loading the model.

## 3.6 Problems Encountered

A code review of the workflow found five weaknesses, all fixed before release. A declined publication read as a success. Anonymous uploads were parsed before identity was checked. A repeated checklist line failed the run after the slow check. A fault inside the loop could escape as a crash. The hand-off at the iteration limit did not mention a report already made.

The model server failed once without being asked to. It returned errors to the first requests of a run while memory was short. The run stopped safely and was repeated once the server answered.

The traces were captured at the end of the period, on 6 October 2026. By then the build was version 0.4.0, which adds the Week 6 case history. The workflow's loop, planner and limits were unchanged from version 0.3.1.

# 4. Results

## 4.1 Automated Tests

All 42 workflow tests passed, run against a scripted model so each case was repeatable. Thirty-one tested the planner and the loop, and eleven tested the command and the API route. The full suite of 339 tests passed. Coverage of the tools and workflow packages was 99%.

## 4.2 Execution Traces

Table 3 lists the six traces. Five used the same three checklist items.

<!-- Table: The six execution traces -->
| Trace | Kind | Iterations | Stop reason | Seconds |
| --- | --- | --- | --- | --- |
| T1 | Normal run, then a declined sign-off | 3 | not_published | 523.9 |
| T2 | Failure and recovery | 3 | report_ready | 623.7 |
| T3 | Failure, stopped safely | 2 | service_unavailable | 63.4 |
| T4 | Refused caller | 1 | unauthorized | 0.0 |
| T5 | Normal run | 2 | report_ready | 507.6 |
| T6 | Normal run on a resubmission | 2 | report_ready | 672.5 |

T2 was the failure and recovery case. Table 4 gives its iterations.

<!-- Table: Trace T2, failure and recovery, iteration by iteration -->
| Iteration | Sensed | Decision | Outcome | Seconds |
| --- | --- | --- | --- | --- |
| 1 | No check has run | Check all 3 items | SERVICE_UNAVAILABLE | 2.2 |
| 2 | Last step failed as SERVICE_UNAVAILABLE | Wait 45 seconds, then repeat the check; retry 1 of 1 | Success: 2 present, 1 missing | 576.5 |
| 3 | Checked, no report | Generate the report | Success: Incomplete, 66.7% | 0.0 |

The outage cost the run 47 seconds. The run then finished as report_ready, with the same findings as the runs that met no failure.

In T3 the server answered with an error to the check and to its one retry. The run stopped as service_unavailable. The hand-off told the officer to start the server and run again, and stated that no item had been recorded as checked. The repeat of that run is T5.

In T4 a bidder was refused at the first step. The step was not retried and the submission was never sent to the model.

The check itself was stable. T1, T2 and T5 covered the same submission. Each reported the same two items present and the anti-bribery declaration missing, as the Week 4 live run had. T6 checked a resubmission with that declaration added and reported all three present.

## 4.3 The Design Beside the Implementation

Table 5 sets each control of the task contract beside what was implemented.

<!-- Table: The task contract beside the implementation -->
| Control | Contract | Implementation | Agreement |
| --- | --- | --- | --- |
| Attempts after a failure | Three | A failed step is retried once; a run has at most seven iterations | Differs; both are settings |
| Approved tools | Extraction and checking | Check, review ticket, report and publish; extraction runs before the loop | Differs in form |
| Successful stop | All checks done | report_ready or published | Agrees |
| Failure stop | Limit reached or processing unreliable | service_unavailable, tool_failed or iteration_limit | Agrees |
| Unsupported or empty document | Stop and ask for a valid one | Refused before the loop starts | Agrees |
| Unresolved uncertainty | Refer to a human | A review ticket for each Unclear item, listed in the hand-off | Agrees |
| Action outside scope | Do not perform it | tool_not_approved; a refusal before any model call | Agrees |
| Human approval | Before any official decision | Publishing needs an officer's sign-off; every report is advisory | Agrees |

Two controls differed. The contract allowed three attempts after a failure, and the implementation retried once. The contract named extraction as a tool, and the implementation extracts the text before the loop begins. Neither difference broke a rule of the contract, and the retry count is a command-line setting.

The larger difference was in the task. The implemented workflow checks every item, re-checks unclear ones, opens tickets and reports. It does not classify the bidder, activate conditional items or follow a cross-reference to an annexure. Those steps of the task definition were not implemented.

# 5. Discussion

Moving the order of steps into code closed the gap found in Week 4. The report was generated in every run that completed a check. It was a step of the plan, not a choice of the model.

The bounds held in practice, not only in tests. No run exceeded its iterations. The two failures ended as the design intended: one cost under a minute and the other stopped with nothing recorded. A stop was never silent. Each named its reason and told an officer what to do next.

The written reason for each decision made the traces readable. A reader could follow a run without the code, which matters for a system whose output an officer must be able to question.

The team's design and the implementation were produced in parallel, and it shows. The loop and the contract described a two-tool agent with three attempts. The implementation followed the course pattern with four tools and one retry. The two agree on every safety rule and differ in detail.

The task definition asked for more than was built. Conditional requirements and cross-references are where a single pass fails, and they remain unhandled. A power of attorney that cites a missing annexure would still be reported present.

Two limits remained. The re-check and the review tickets were not seen in any live trace, because the model returned no Unclear item. They are covered by scripted tests only. A sign-off by an officer at the terminal was also not recorded live.

# 6. Conclusion

In Week 5 the completeness check became a bounded workflow of several steps. A task was defined, a loop designed, a contract of limits written, the workflow implemented and six traces captured. All five objectives were met.

The main lesson was that reliability came from the bounds, not from the model. Fixed planning rules, a retry budget, a list of approved tools and a hand-off at every stop made each run predictable. The model was left with the one job that needs it.

# 7. Recommendations

- The workflow should be extended to the task the team defined: classifying the bidder, activating conditional items and following cross-references to annexures.
- The contract's figure of three attempts should be adopted as the default, or the contract amended to the one retry implemented.
- The task contract should list the review ticket, report and publish tools, so the approved list matches the system.
- A live trace should be captured with an Unclear item, to show the re-check and the review ticket outside scripted tests.
- A live run with an officer signing off at the terminal should be recorded.
- Traces should be captured in the week the workflow is built, so the evidence and the build share a version.

# References

Bataringaya, B. (2026a). *Public procurement document completeness agent: Workflow* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Katongole, J. (2026a). *Workflow implementation* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Katongole, J. (2026b). *Workflow execution traces* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Liu, N. F., Lin, K., Hewitt, J., Paranjape, A., Bevilacqua, M., Petroni, F., and Liang, P. (2024). Lost in the middle: How language models use long contexts. *Transactions of the Association for Computational Linguistics, 12*, 157-173. https://doi.org/10.1162/tacl_a_00638

Mwesigwa, I. (2026). *Public procurement completeness agent: Multi-step decision task definition* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Mwesigwa, I., and Bataringaya, B. (2026). *Agent task contract: Public procurement document completeness agent* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Schluntz, E., and Zhang, B. (2024). *Building effective agents*. Anthropic. https://www.anthropic.com/research/building-effective-agents

Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., and Cao, Y. (2023). ReAct: Synergizing reasoning and acting in language models. In *Proceedings of the 11th International Conference on Learning Representations*. https://arxiv.org/abs/2210.03629
