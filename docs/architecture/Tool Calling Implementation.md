---
title: Tool Calling Implementation
subtitle: Tool and Function Calling Through the Application Layer
line: **Public Procurement Document-Completeness Agent (ProcureCheck)**
line: BSE4104 AI-Native and Agentic Engineering Capstone, Group H (Evening)
line: Week 4, ClickUp task 123tcvwfnxb
line: Author: Jonathan Katongole
---

[[TOC]]

[[TABLES]]

# 1. Purpose

This document describes how tool calling was added to ProcureCheck in Week 4. The tools were defined first in the team's tool specification (Bataringaya, 2026). This work implemented those tools and the layer that calls them.

The central design rule was that the model proposes and the application decides. The model may name a tool and supply some arguments. It never runs a tool, never chooses the document, and never bypasses a check.

# 2. The Tools

Two tools were implemented, exactly as specified. Table 1 summarises them.

<!-- Table: The two tools and their contracts -->
| Tool | Purpose | Input | Output | Permission |
| --- | --- | --- | --- | --- |
| check_document_completeness | Checks a document against its checklist | document_text, document_type, required_items | Present, Missing or Unclear per item, with a reason, and the completeness percentage | document:analyse |
| generate_completeness_report | Builds a report from the check results | document_name, document_type, completeness_percentage, completeness_results | Overall status, present, missing and unclear items, recommendations | report:generate |

The check tool reuses the existing matching engine. A check made through a tool therefore passes through the same two model passes and three code guards as any other check. The engine's statuses were mapped to the specification's names. Found became Present, Not Found became Missing, and Requires Human Review became Unclear.

The report tool makes no model call. Counting items and listing next steps is arithmetic, and arithmetic done by a model can be wrong. The tool also recomputes the percentage from the results it receives. A percentage that disagrees with the results is refused as INVALID_RESULTS.

Recommendations concern the document only. They never say to award, reject or disqualify a bid.

# 3. Architecture

## 3.1 The Flow of One Run

A run passed through six stages. Table 2 lists them in order.

<!-- Table: Stages of one tool-calling run -->
| Stage | Component | What happens |
| --- | --- | --- |
| 1 | Safety guard | The user's request is screened. A request to score, rank, judge legality or recommend an award is refused before the model is called. |
| 2 | Model turn | The model receives the request and the tool definitions. It proposes zero or more tool calls. |
| 3 | Call parsing | Each proposed call is read without trusting its shape. A malformed call becomes a structured error. |
| 4 | Argument binding | The document text and checklist are supplied by the application. Any value the model wrote into those fields is discarded and recorded. |
| 5 | Tool executor | The call is checked and run (Section 3.2). The result, or a structured error, is returned to the model. |
| 6 | Final answer | When the model stops calling tools, its answer is screened again. An answer that recommends an award is withheld. |

The loop ends after five model turns at most. A model that keeps calling tools ends the run with STEP_LIMIT_REACHED. A run in which every tool call was refused for permission ends as UNAUTHORIZED, so it cannot be read as a success.

## 3.2 The Tool Executor

Every tool call passes through one method, whichever route it came from: the model, the API or a test. That method applied five checks in a fixed order. Table 3 lists them.

<!-- Table: Checks applied by the tool executor, in order -->
| Order | Check | Error code on failure |
| --- | --- | --- |
| 1 | The tool exists | UNKNOWN_TOOL |
| 2 | The caller holds the tool's permission | UNAUTHORIZED |
| 3 | The arguments match the input schema | MISSING_PARAMETER, INVALID_ARGUMENTS or INVALID_RESULTS |
| 4 | The tool runs | The tool's own code, SERVICE_UNAVAILABLE, or ANALYSIS_FAILED and REPORT_GENERATION_FAILED |
| 5 | The answer matches the output schema | UNEXPECTED_TOOL_RESPONSE |

Authorization runs before argument checks on purpose. A caller who may not use a tool learns nothing about its parameters by probing it.

## 3.3 Why the Model Never Sees the Document

The model is offered each tool's schema with the bound fields removed. For the check tool, it sees only document_type. For the report tool, it sees no arguments at all.

This choice closed a prompt injection route. A submission could contain text telling the model to check a different document, or to pass an empty checklist. Because the model cannot set those fields, such text has nothing to act on.

It also kept the conversation small. The model never copies a whole submission into a tool argument, so an 8B model cannot garble it.

# 4. Authorization

Permissions were granted by role. Table 4 gives the roles, which follow the actors in the Project Charter.

<!-- Table: Roles and the tools each may call -->
| Role | check_document_completeness | generate_completeness_report |
| --- | --- | --- |
| procurement_officer | Yes | Yes |
| evaluation_committee | No | Yes |
| bidder | No | No |
| guest, unknown role or no identity | No | No |

The API identifies the caller by an X-API-Key header. Keys are read from the PROCURECHECK_API_KEYS environment variable as key:role:user entries. No key is stored in code. When no keys are configured, every tool route refuses. The API fails closed rather than open. Keys are compared in constant time. A malformed key setting is reported by its position only, never by its content, and the caller receives only a generic server error.

The command line is a local, trusted entry point. The operator states a role with --role, which defaults to procurement_officer.

# 5. Error Codes

The specification named eight error codes. The orchestration layer added seven more, for failures that happen around a tool rather than inside it. Table 5 lists the additions.

<!-- Table: Error codes added by the orchestration layer -->
| Code | Raised when |
| --- | --- |
| UNKNOWN_TOOL | The model or a caller names a tool that does not exist |
| MISSING_PARAMETER | A required argument is absent; the message names it |
| INVALID_ARGUMENTS | An argument has the wrong type, or an undeclared argument is sent |
| SERVICE_UNAVAILABLE | The model backend cannot be reached or answers with something other than JSON |
| UNEXPECTED_TOOL_RESPONSE | A tool answers with something that does not match its output schema |
| STEP_LIMIT_REACHED | The model is still calling tools after the turn limit |
| REFUSED | The request crosses the safety boundary |

Over HTTP the body is always the specification's error envelope. The status code only tells a client which kind of failure occurred: 401, 403, 404, 422, 502 or 503.

# 6. Using It

The tools and the agent are reached in three ways. Table 6 lists them.

<!-- Table: Entry points -->
| Entry point | Command or route | Use |
| --- | --- | --- |
| List tools | python run.py tools, or GET /tools | Each tool's purpose, schemas and permission |
| Agent | python run.py agent --submission FILE, or POST /agent | The model chooses and calls the tools; a trace is written to evidence/traces/tools/ |
| Direct call | POST /tools/{name} | A caller runs one tool through the same executor, without the model |

Every agent run writes a trace. It records the caller, each proposed call, the arguments after binding, the result or error, the time taken and the final answer.

# 7. Departures From the Specification

Four points differ from, or go beyond, the tool specification.

1. Seven error codes were added, listed in Table 5. The success payloads were not changed.
2. Document-level access was not enforced. The specification asks that a user may access the particular document. Permissions are checked per role only, because the application does not yet record who owns which submission.
3. The report tool's completeness_results argument defaults to an empty list. A call without results therefore returns NO_ANALYSIS_RESULTS, as specified, rather than a generic missing-parameter error.
4. The report tool rejects a percentage that disagrees with its results by more than half a point.

# 8. Verification

The work was verified by 91 automated tests across five test files. They ran without a model server, against a scripted model. Coverage of the tools package was 99%.

A code review of the new package found three defects, all fixed before release. A malformed key setting could echo the key to an anonymous caller. The agent route returned success when every tool call had been refused. An unexpected fault passed its internal message to the caller. Each fix has a regression test.

Four runs were also made against the real model. As a procurement officer, the model called the check tool, which returned the correct result of 66.7% in 1,053 seconds. The model then answered without calling the report tool. As a bidder, the check was refused and the run ended as UNAUTHORIZED. With the backend stopped, the run ended as SERVICE_UNAVAILABLE. A request to pick a winner was refused before any model call.

The failure behaviour is reported separately, case by case, in the tool-calling failure test report (docs/evaluation/tool-failure-tests.docx). That report also lists runs against the real model.

# 9. Open Work

- A human approval step before higher-impact actions is Isaac Mwesigwa's Week 4 task. The executor is the place to add it, as a check between authorization and execution.
- A tool that reads current application data or makes a low-risk simulated change is Makmot Johnson's Week 4 task. A new tool is registered with one ToolSpec and inherits every check above.
- Document-level access control needs a record of which user may see which submission.
- The orchestration prompt, orchestrator-v1.0, has not yet been evaluated across many requests. In the live officer run the model skipped the report tool. A firmer tool order in the prompt, or an application-side report step after a successful check, should be tried.

# References

Bataringaya, B. (2026). *Tool / function specification for the Public Procurement Document Completeness Agent* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Ollama. (2026). *Ollama API documentation: Chat request with tools*. https://github.com/ollama/ollama/blob/main/docs/api.md
