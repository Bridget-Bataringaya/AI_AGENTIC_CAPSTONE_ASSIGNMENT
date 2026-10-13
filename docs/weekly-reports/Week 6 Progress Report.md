---
title: Week 6 Progress Report
subtitle: State, Memory and an MCP-Style Interface
line: **Public Procurement Document-Completeness Agent (ProcureCheck)**
line: BSE4104 AI-Native and Agentic Engineering Capstone
line: Group H (Evening)
line: Jonathan Katongole, Makmot Johnson, Isaac Mwesigwa, Bataringaya Bridget
line: School of Computing and Informatics Technology, Makerere University
line: Reporting period: 7 to 13 October 2026
---

[[TOC]]

[[TABLES]]

# Abstract

**Introduction.** Week 6 aimed to make the agent's state explicit, to give it one justified use of persistent memory, and to describe one capability as an MCP-style interface. **Methods.** A state model was written for the session, the checklist item and the review ticket. One memory use case, case history, was implemented: each finished check is remembered, so a resubmission can be compared with it. A data handling note recorded what is stored, why, who can access it, and how it is retained and deleted. A controlled comparison tested whether memory could change a result. The completeness check was specified as an MCP-style tool. **Results.** The memory package passed 93 automated tests, within a suite of 432. On a resubmission the officer was told which missing document had arrived. A deliberately false memory changed no status in a live run, and instead produced a request for a check by hand. The state model and the interface specification both described more than was built. **Conclusion.** Memory was added as an informant and not as a decider. The remaining work is to bring the implementation up to the state model.

# 1. Introduction and Objectives

ProcureCheck checks a tender submission against a procurement checklist. It reports which required documents are present, missing or in need of human review. It never scores, ranks or recommends an award.

Until Week 6 the application kept nothing between runs. Each check started from nothing, and its state lived only inside the running program. Week 6 asked what the system should know, for how long, and who may see it.

The objectives for Week 6 were:

1. To model workflow and session state explicitly.
2. To implement one justified persistent-memory use case.
3. To document what is stored, why, who can access it, retention and deletion.
4. To demonstrate that memory improves a legitimate task without silently controlling critical decisions.
5. To implement one external integration, or document one project capability as an MCP-style interface.

Table 1 gives the five tasks, who was assigned each, and who prepared the deliverable.

<!-- Table: Week 6 tasks, assignment and deliverable -->
| Objective | Assigned to | Deliverable | Prepared by |
| --- | --- | --- | --- |
| 1. State model | Makmot Johnson | Workflow and session state model | Makmot Johnson |
| 2. Memory use case | Jonathan Katongole | The memory package, its tests and a design document | Jonathan Katongole |
| 3. Data handling | Isaac Mwesigwa | Memory data handling note | Jonathan Katongole |
| 4. Demonstration | Isaac Mwesigwa and Bataringaya Bridget | Memory demonstration, script and results | Jonathan Katongole |
| 5. MCP-style interface | Bataringaya Bridget | MCP-style interface specification | Bataringaya Bridget |

# 2. Background

An agent that keeps nothing must be told everything again at each run. Memory lets it carry facts forward. Packer et al. (2023) describe a memory that the model itself reads and writes, so that a conversation can outlast the context window.

Memory that feeds the model is also a way in for an attacker. Text placed in a store can be read back later as if it were trusted, and steer the system long after it was written (Greshake et al., 2023). The safer pattern keeps memory out of the model's input and out of the decision path.

Stored data about people and their bids is also regulated. Uganda's Data Protection and Privacy Act, 2019 requires that personal data be collected for a stated purpose, kept no longer than necessary and kept secure.

The Model Context Protocol is an open standard for offering tools and data to a model through one interface (Anthropic, 2024). A capability described in its style states its inputs, outputs, permissions and boundary, whether or not a server is built.

# 3. Methodology and Procedure

## 3.1 The State Model

State was modelled at three levels: the session, the checklist item and the review ticket (Johnson, 2026). A session was given twelve states, from CREATED to CLOSED, with PAUSED and FAILED for a dependency that goes down. Each allowed move was listed with its trigger, who may make it and its guard condition. Any move not listed was refused.

A checklist item was given nine states. The agent could take an item as far as PRESENT, MISSING, AMBIGUOUS or UNRESOLVED. Only the officer could confirm it. UNRESOLVED was kept apart from MISSING, so that a tool failure could never be read as a finding.

The model also set limits: three search calls for each item, a pause after three service errors in a row, and thirty minutes in which to resume. It stated where each kind of state lives, and left persistent memory to the memory task.

## 3.2 The Memory Use Case

One use case was chosen: case history (Katongole, 2026a). Each workflow run that reached a report stored a record of the submission's result. When the bidder resubmitted, the next run recalled that record and reported what had changed.

Two alternatives were considered and set aside. An approved preference would have saved keystrokes and helped no decision. Reusing a prior result would have let memory decide a status without a fresh check.

Memory was placed outside the workflow loop. The earlier case was recalled before the loop and compared only after it had stopped. It was never passed to the planner and never placed in a prompt. A store that could not be read cost the run its comparison and nothing else.

## 3.3 The Data Handling Note

The note recorded every stored field with its purpose (Katongole, 2026b). A record held the submission identifier, the document name and type, a fingerprint of the text, each item's status, the percentage, who ran the check and when. It held no document text, no quotation and none of the model's reasons.

Access was set by role and checked in code. Only a procurement officer could read, write or delete. Records were deleted automatically after 180 days. An officer could delete one submission's records sooner, after typing its identifier to confirm.

The note also listed everything else the application writes to disk, so that the answer to "what is kept" was complete.

## 3.4 The Demonstration

The demonstration tested three claims separately (Katongole, 2026c). For the first, a submission was checked, then its resubmission, and the officer's work was compared with and without memory.

For the second, one submission was checked three times against the real model. Run A had memory off. Run B held a truthful earlier case. Run C held a false earlier case that said every item had been present. Everything the runs decided was then compared.

For the third, each place where memory shows itself to the officer was listed.

## 3.5 The MCP-Style Interface

The completeness check was specified as one MCP-style tool, check_procurement_document_completeness (Bataringaya, 2026). The specification gave its inputs, its outputs, four status values, the permitted roles and the security boundary. It listed what the tool may not do: change a document, approve or reject a bidder, or award a contract.

The document stated that it was a specification and not a running server. It also noted that a caller's identity should come from the security context, not from a field the caller supplies.

## 3.6 Problems Encountered

A code review of the memory package found four weaknesses, all fixed before release. Text with a stray half-character could not be fingerprinted. An item with irregular spacing did not match its own earlier record. A store interrupted while being created could not be reopened. A deleted record stayed readable in the file's free space.

The model server failed once while loading the model. The run stopped safely and nothing was remembered.

The development machine lost its Python installation during the week. The environment was rebuilt on Python 3.12, and the full test suite passed on it.

Two tasks had not been started by 13 October. They were completed that day by another member, as Table 1 shows.

# 4. Results

## 4.1 Memory Tests and Live Runs

The memory package passed 93 automated tests, run against a scripted model. The full suite of 432 tests passed. Line coverage of the memory package was 97%.

Two live runs showed the use case working. The first checked a submission that lacked the anti-bribery declaration and reported it Incomplete at 66.7%. The second checked the resubmission and reported it Complete at 100.0%. Its case history told the officer that the declaration was now present and that two items were present both times.

## 4.2 The Controlled Comparison

Table 2 gives what each of the three runs decided.

<!-- Table: What each run of the controlled comparison decided -->
| Decided | Run A, memory off | Run B, truthful memory | Run C, false memory |
| --- | --- | --- | --- |
| Tax clearance certificate | Present | Present | Present |
| Anti-bribery declaration | Missing | Missing | Missing |
| Conflict of interest declaration | Present | Present | Present |
| Percentage present | 66.7 | 66.7 | 66.7 |
| Planning decisions | Check, then report | Check, then report | Check, then report |
| Stop reason | report_ready | report_ready | report_ready |
| Hand-off | Locate the declaration; sign off | The same | The same |
| Seconds | 996.6 | 672.0 | 678.8 |

The three runs decided the same thing in every respect. The false memory in run C changed no status. It told the officer that an item recorded as present was now missing, and asked for a check by hand.

## 4.3 What the Data Handling Note Found

The note confirmed eleven of its statements against automated tests. It also recorded three weaknesses. Trace files and check reports hold quotations from the submission, and they are not deleted automatically. Access is by role and not by submission. The store is not encrypted.

## 4.4 The State Model Beside the Implementation

Table 3 sets the state model beside what the application does.

<!-- Table: The state model beside the implementation -->
| Element | State model | Implementation | Agreement |
| --- | --- | --- | --- |
| Session lifecycle | Twelve named states with guarded moves | One immutable state object and eight stop reasons | Differs |
| Item outcomes | Present, Missing, Ambiguous, Unresolved | Present, Missing, Unclear | Partly |
| A failure is never a finding | Unresolved is kept apart from Missing | A tool failure stops the run; nothing is recorded as checked | Agrees |
| Officer confirms each item | Confirmed Present or Confirmed Missing | Sign-off is on the whole report, at publication | Differs |
| Export only after sign-off | No path to export without it | Publication needs an officer's sign-off | Agrees |
| Bounded loop | Three searches for each item | Seven iterations; one re-check round | Agrees in intent |
| Outage | Pause, then resume within thirty minutes | One retry, then stop; the run is repeated by hand | Differs |
| One session, one submission | Every call scoped to its session | One submission for each run | Agrees |
| Every change logged | Append-only audit log | A trace for each run | Partly |
| Working state is short-lived | Cleared when the session closes | Held in the program's memory only | Agrees |

The safety rules agreed. The model was richer in three places: named session states, confirmation of each item by the officer, and a pause that can be resumed.

## 4.5 The Interface Beside the Implementation

Table 4 sets the MCP-style specification beside the tool that exists.

<!-- Table: The MCP-style interface beside the implemented tool -->
| Element | Specification | Implemented tool | Agreement |
| --- | --- | --- | --- |
| Document input | A document identifier | The extracted text of the document | Differs |
| Requirements input | A list of required sections | A list of required items | Agrees |
| Caller | A user identifier in the request | Identity taken from an API key | Differs, as the specification advised |
| Findings | Found, missing and uncertain sections | Present, Missing and Unclear for each item, with a reason | Agrees |
| Overall status | Complete, Incomplete, Needs Human Review | Complete, Incomplete, Needs Review | Agrees |
| Errors | Unsupported file, access denied, invalid input | Unsupported document, unauthorized, invalid arguments | Agrees in meaning |
| Not allowed | Changing documents, approving, awarding | The same, enforced by the executor | Agrees |
| MCP server | Not claimed | Not built | Agrees |

The specification and the tool agreed on what the capability does and where its authority ends. They differed in how a document and a caller are named.

# 5. Discussion

Memory was added without giving it authority. The design kept the recalled case outside the loop, and the controlled comparison showed the effect. A false record could not make a missing document present. The worst a wrong memory could do was ask the officer to look.

The same comparison exposed a second use for memory. When the text was identical and the answer differed, memory said so. A single run cannot show that the model's reading is unstable. Two runs set side by side can.

Writing down what is stored proved as useful as building the store. The note found that the traces and reports, which nobody had thought of as memory, hold more of a bid than the memory does. They are kept until someone deletes them.

The state model and the implementation were again produced in parallel. They agree on every rule that protects a bidder. The model describes a session that an officer walks through, confirming each item. The implementation runs a check to a report in one pass. The officer's confirmation of each item is the largest gap.

The interface specification was honest about its limits. It describes how a tool should be offered to a model, and it claims no server. No external integration was built this week.

# 6. Conclusion

In Week 6 the agent's state was modelled, one use of persistent memory was built and tested, its data handling was documented, and one capability was specified as an MCP-style interface. All five objectives were met.

The main lesson was that memory is safe when it informs and unsafe when it decides. Keeping it out of the planner, out of the prompt and out of every status made a poisoned record harmless.

# 7. Recommendations

- The officer's confirmation of each item should be implemented, with the Confirmed Present and Confirmed Missing states of the state model.
- A paused session that can be resumed should replace the present stop on a lasting outage.
- Trace files and check reports should be given a retention period, or have their quotations removed.
- The store should be encrypted before real bids are checked, and registration under the Data Protection and Privacy Act confirmed.
- The MCP-style specification should be aligned with the implemented tool, then built as a server if an external client is needed.
- Each member's deliverables should be merged from personal branches into the shared branch, so the repository holds the whole team's work.

# References

Anthropic. (2024). *Model Context Protocol: Specification*. https://modelcontextprotocol.io/specification

Bataringaya, B. (2026). *MCP-style interface for the Public Procurement Document Completeness Agent* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Greshake, K., Abdelnabi, S., Mishra, S., Endres, C., Holz, T., and Fritz, M. (2023). Not what you've signed up for: Compromising real-world LLM-integrated applications with indirect prompt injection. In *Proceedings of the 16th ACM Workshop on Artificial Intelligence and Security* (pp. 79-90). ACM. https://doi.org/10.1145/3605764.3623985

Johnson, M. (2026). *Workflow and session state model* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Katongole, J. (2026a). *Persistent memory implementation* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Katongole, J. (2026b). *Memory data handling note* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Katongole, J. (2026c). *Memory demonstration* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Packer, C., Wooders, S., Lin, K., Fang, V., Patil, S. G., Stoica, I., and Gonzalez, J. E. (2023). *MemGPT: Towards LLMs as operating systems*. arXiv. https://arxiv.org/abs/2310.08560

The Data Protection and Privacy Act, 2019 (Uganda).
