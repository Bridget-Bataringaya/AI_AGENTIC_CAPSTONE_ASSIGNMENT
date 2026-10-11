---
title: Week 4 Progress Report
subtitle: Tools, Tool Calling and Human Approval
line: **Public Procurement Document-Completeness Agent (ProcureCheck)**
line: BSE4104 AI-Native and Agentic Engineering Capstone
line: Group H (Evening)
line: Jonathan Katongole, Makmot Johnson, Isaac Mwesigwa, Bataringaya Bridget
line: School of Computing and Informatics Technology, Makerere University
line: Reporting period: 23 to 29 September 2026
---

[[TOC]]

[[TABLES]]

# Abstract

**Introduction.** Week 4 aimed to let the completeness agent act through tools rather than through free text alone. **Methods.** Two tools were specified with their inputs, outputs, permissions and failure behaviour. They were implemented behind a single executor that checks every call. A model-driven loop let the language model propose calls while the application ran them. A third tool with a low-risk side effect, a draft review ticket, was specified and implemented. A human sign-off step was added before the one higher-impact action, publishing a report to the procurement record. Failure behaviour was tested with 34 scripted cases and four runs against the real model. **Results.** All 34 failure cases met their expected behaviour. The executor refused unauthorised callers, reported unavailable services and discarded malformed tool answers. The approval gate published nothing without an officer's sign-off. In the live run the model called the check tool correctly but did not call the report tool. **Conclusion.** Checks enforced in code held in every case. Choices left to the 8B model did not always hold, which pointed Week 5 towards orchestration led by the application.

# 1. Introduction and Objectives

ProcureCheck checks a tender submission against a procurement checklist. It reports which required documents are present, missing or in need of human review. It never scores, ranks or recommends an award.

Up to Week 3 the system was a single pipeline: the application called the model in a fixed order. Week 4 introduced tools, named functions with declared inputs and outputs that the model may ask to use. A tool call is a request for an action. Whether the action runs, and with what data, remained a decision for the application.

The objectives for Week 4 were:

1. To define at least two tools with their purpose, input schema, output schema, authorization and failure behaviour.
2. To implement tool calling through the application and orchestration layer.
3. To provide at least one tool that retrieves current application data or performs a low-risk simulated side effect.
4. To add human approval before any higher-impact action.
5. To test missing parameters, unauthorized requests, unavailable services and unexpected tool responses.

The work was shared as follows. Bataringaya Bridget wrote the tool specification that defined the first two tools. Makmot Johnson specified the review ticket tool. Jonathan Katongole implemented the tools, the tool-calling layer, the review ticket tool and the human approval gate. He also ran the failure tests.

# 2. Background

Function calling lets a language model return a structured request to run a named function instead of text (Schick et al., 2023). The application supplies the function definitions, runs the function and returns its result to the model. Ollama exposes this for Llama 3.1 through a tools field on its chat endpoint (Ollama, 2026).

Tool use widens what can go wrong. Text in a document can try to steer the model into calling a tool with different arguments, a risk known as indirect prompt injection (Greshake et al., 2023). The model may also call the wrong tool, omit arguments or stop early. The usual answer is to keep authority in the application: validate every call, restrict what the model can set, and ask a person before consequential actions.

# 3. Methodology and Procedure

## 3.1 Tool Specification

The tool specification defined two tools (Bataringaya, 2026). check_document_completeness takes the document text, its type and the checklist, and returns Present, Missing or Unclear for each item with a reason and a percentage. generate_completeness_report turns those results into a report with an overall status and recommendations. The specification gave each tool's schemas, its permission and eight error codes.

A third tool, create_review_ticket, was specified to meet the side-effect objective (Johnson, 2026). It writes a draft review ticket for an item the check could not decide, so the item stays visible to the officer. It decides nothing and the agent cannot close a ticket.

## 3.2 The Executor

Every tool call, from the model, the API or a test, passed through one executor. It applied its checks in a fixed order, listed in Table 1.

<!-- Table: Checks applied by the tool executor, in order -->
| Order | Check | Error code on failure |
| --- | --- | --- |
| 1 | The tool exists | UNKNOWN_TOOL |
| 2 | The caller holds the tool's permission | UNAUTHORIZED |
| 3 | The arguments match the input schema | MISSING_PARAMETER or INVALID_ARGUMENTS |
| 4 | A person approves, if the tool is higher-impact | APPROVAL_REQUIRED or APPROVAL_DENIED |
| 5 | The tool runs | The tool's own code, or SERVICE_UNAVAILABLE |
| 6 | The answer matches the output schema | UNEXPECTED_TOOL_RESPONSE |

Permissions were granted by role, following the actors in the Project Charter. A procurement officer could use every tool. An evaluation committee member could only read reports. A bidder and a guest could use none. API callers were identified by keys held in an environment variable, never in code.

## 3.3 Tool Calling

In the model-driven loop the model received the request and the tool definitions, and proposed calls. The application ran each call through the executor and returned the result, for at most five turns.

The model was never shown the document text or the checklist as arguments. The application supplied them from the session and discarded anything the model wrote into those fields. Text inside a submission therefore had nothing to steer. The review ticket and publishing tools were not offered to the model at all.

## 3.4 Human Approval

The team's AI Boundary Matrix placed report sign-off under Human Approval Required. A completeness report may not enter the official procurement record without explicit sign-off from an authorised officer. Adding a report to the record was therefore identified as the higher-impact action.

A publishing tool was added for that action, writing to a simulated, append-only record. The executor held any call to it until a person with sign-off rights approved. The officer was shown the document, its overall status and its missing and unclear items, and typed APPROVE to sign off. No approver, a decline, no answer, or a yes from someone without sign-off rights all refused the action (Katongole, 2026b).

## 3.5 Failure Tests

Thirty-four failure cases were written, each stating its expected behaviour before it ran. They ran against a scripted model, so every case was repeatable. Four further runs used the real model, Meta Llama 3.1 8B through Ollama on a CPU-only laptop (Katongole, 2026a).

## 3.6 Problems Encountered

Five problems arose, all found by code review and all fixed before release.

A malformed key setting caused the API to echo the key in an error message to an unauthenticated caller. The message was changed to give the entry's position only.

The agent route reported success when every tool call had been refused. A run whose calls were all refused was changed to end as UNAUTHORIZED.

An unexpected fault passed its internal message to the caller. The caller was given the fault's type only, and the details went to the server log.

The publishing tool, if called directly rather than through the executor, accepted an approval from someone without sign-off rights. It was changed to check those rights itself.

An approval piped into the sign-off prompt by a script counted as a person's. The prompt was changed to accept an answer only at an interactive terminal.

# 4. Results

All 34 failure cases met their expected behaviour. Table 2 gives the count by category.

<!-- Table: Failure cases met by category -->
| Category | Cases | Met |
| --- | --- | --- |
| Missing or unusable parameters | TF-01 to TF-09 | 9 of 9 |
| Unauthorized requests | TF-10 to TF-16 | 7 of 7 |
| Unavailable services | TF-17 to TF-21 | 5 of 5 |
| Unexpected tool and model responses | TF-22 to TF-34 | 13 of 13 |

Table 3 lists the runs against the real model.

<!-- Table: Runs against the real model -->
| Run | Role | Outcome | Seconds |
| --- | --- | --- | --- |
| Officer asks for a check and report | Procurement officer | Check ran, 66.7% present; no report | 1,052.9 |
| Bidder asks for a check | Bidder | Refused as UNAUTHORIZED | 68.7 |
| Model server stopped | Procurement officer | SERVICE_UNAVAILABLE | 2.1 |
| Request to pick a winning bidder | Procurement officer | Refused before any model call | 0.0 |

The check in the officer run was correct. Two of the three checklist items were found and the anti-bribery declaration was reported missing. The model then answered without calling the report tool, although the request asked for a report. It also gave the tool's status, success, as though it were the document's status.

The approval gate passed all 36 of its automated tests, 31 for the gate itself and five end to end. No test left a report on the record without an officer's sign-off. The review ticket tool passed 10 tests, including one showing that the model could not call it even by naming it.

# 5. Discussion

Everything enforced in code held. Unauthorised roles were refused, bad arguments were caught before any tool ran, and malformed answers were discarded rather than passed on. The checks lived in one executor, so no route could skip them.

What was left to the model held less well. The 8B model skipped the report step and confused two meanings of the word status. Neither broke a safety rule and no finding was invented. Both show that the order of steps in a routine task should not depend on the model's choice.

Binding the document and checklist in the application proved worthwhile beyond security. The model never had to copy a long submission into an argument, which an 8B model could easily garble.

The approval gate made the Boundary Matrix's sign-off rule enforceable rather than advisory. Its weak point is the API. With no person present during a request, a publish call through the API can only be refused. An approval queue that an officer answers later is needed there.

Two limits remained. Permissions were checked per role, not per document, because the system did not yet record who may see which submission. The record the publishing tool wrote to was simulated.

# 6. Conclusion

In Week 4 the agent gained three tools behind one checked executor, a fourth tool behind human sign-off, and a tested account of how each call can fail. All five objectives were met.

The main lesson was that tool calling moved authority, not just capability. The system was safe where the application decided and less reliable where the model decided. That finding set the direction for Week 5.

# 7. Recommendations

- The order of routine steps, such as checking before reporting, should be set by the application rather than by the model.
- The API should gain an approval queue so an officer can sign off a report after the request that produced it.
- Access should be checked per submission as well as per role once ownership is recorded.
- A second officer's sign-off should be considered for publication, separating the person who ran the check from the person who approves it.
- The orchestration prompt should be evaluated across many requests before the model-driven loop is relied on.

# References

Bataringaya, B. (2026). *Tool / function specification for the Public Procurement Document Completeness Agent* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Greshake, K., Abdelnabi, S., Mishra, S., Endres, C., Holz, T., and Fritz, M. (2023). Not what you've signed up for: Compromising real-world LLM-integrated applications with indirect prompt injection. In *Proceedings of the 16th ACM Workshop on Artificial Intelligence and Security* (pp. 79-90). ACM. https://doi.org/10.1145/3605764.3623985

Johnson, M. (2026). *Third tool specification: create_review_ticket* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Katongole, J. (2026a). *Tool-calling failure tests* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Katongole, J. (2026b). *Human approval gate* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Ollama. (2026). *Ollama API documentation: Chat request with tools*. https://github.com/ollama/ollama/blob/main/docs/api.md

Schick, T., Dwivedi-Yu, J., Dessì, R., Raileanu, R., Lomeli, M., Zettlemoyer, L., Cancedda, N., and Scialom, T. (2023). Toolformer: Language models can teach themselves to use tools. In *Advances in Neural Information Processing Systems 36*. https://arxiv.org/abs/2302.04761
