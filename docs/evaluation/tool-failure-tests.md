---
title: Tool-Calling Failure Tests
subtitle: Missing Parameters, Unauthorized Requests, Unavailable Services and Unexpected Responses
line: **Public Procurement Document-Completeness Agent (ProcureCheck)**
line: BSE4104 AI-Native and Agentic Engineering Capstone, Group H (Evening)
line: Run 2026-09-23 18:41
---

[[TOC]]

[[TABLES]]

# 1. Scope

The tests cover the tool-calling layer added in Week 4. It runs the two tools in the team's tool specification: check_document_completeness and generate_completeness_report. Every call passes through one executor. The executor checks that the tool exists, that the caller is permitted, that the arguments match the schema, and that the answer matches the schema.

Each case states its expected behaviour before it runs. A case is Met only when every assertion in its test passes. The rule behind every case is the same. A failure must end in a structured error with a named code, never in a crash, an empty result or an invented one.

The cases run without a model server, against a scripted model, so each one is repeatable. Section 4 adds live runs against the real model.

# 2. Summary

34 of 34 cases met their expected behaviour. Table 1 gives the count by category.

<!-- Table: Cases met by failure category -->
| Category | Cases | Met |
| --- | --- | --- |
| Missing or unusable parameters | TF-01 to TF-09 | 9 of 9 |
| Unauthorized requests | TF-10 to TF-16 | 7 of 7 |
| Unavailable services | TF-17 to TF-21 | 5 of 5 |
| Unexpected tool and model responses | TF-22 to TF-34 | 13 of 13 |

# 3. Expected and Actual Behaviour

## 3.1 Missing or unusable parameters

Table 2 lists each case, its expected behaviour and the result.

<!-- Table: Missing or unusable parameters: expected and actual behaviour -->
| Case | Scenario | Expected | Result |
| --- | --- | --- | --- |
| TF-01 | Check tool called without document_type | MISSING_PARAMETER naming document_type | Met. As expected. |
| TF-02 | Check tool called without required_items | MISSING_PARAMETER naming required_items | Met. As expected. |
| TF-03 | Checklist holds only blank entries | MISSING_CHECKLIST; no model call | Met. As expected. |
| TF-04 | Report tool called with no results | NO_ANALYSIS_RESULTS | Met. As expected. |
| TF-05 | Model omits document_type, then retries | MISSING_PARAMETER sent back to the model; retry succeeds | Met. As expected. |
| TF-06 | required_items sent as a string, not a list | INVALID_ARGUMENTS | Met. As expected. |
| TF-07 | Model adds an undeclared parameter | INVALID_ARGUMENTS naming it | Met. As expected. |
| TF-08 | Raw PDF bytes sent as document_text | UNSUPPORTED_DOCUMENT | Met. As expected. |
| TF-09 | Blank document_text | EMPTY_DOCUMENT | Met. As expected. |

## 3.2 Unauthorized requests

Table 3 lists each case, its expected behaviour and the result.

<!-- Table: Unauthorized requests: expected and actual behaviour -->
| Case | Scenario | Expected | Result |
| --- | --- | --- | --- |
| TF-10 | Anonymous caller runs a check | UNAUTHORIZED with the specified message; no model call | Met. As expected. |
| TF-11 | Bidder calls either tool | UNAUTHORIZED with each tool's specified message | Met. As expected. |
| TF-12 | Evaluation committee member calls both tools | Check refused; report allowed | Met. As expected. |
| TF-13 | Bidder calls with empty arguments | UNAUTHORIZED; no parameter names disclosed | Met. As expected. |
| TF-14 | Caller with an unknown role | UNAUTHORIZED | Met. As expected. |
| TF-15 | Bidder drives the agent | Tool call UNAUTHORIZED; run ends UNAUTHORIZED; no findings | Met. As expected. |
| TF-16 | Request to rank bidders | REFUSED before any model call | Met. As expected. |

## 3.3 Unavailable services

Table 4 lists each case, its expected behaviour and the result.

<!-- Table: Unavailable services: expected and actual behaviour -->
| Case | Scenario | Expected | Result |
| --- | --- | --- | --- |
| TF-17 | Model backend fails during a check | SERVICE_UNAVAILABLE | Met. As expected. |
| TF-18 | Orchestrating model is down | SERVICE_UNAVAILABLE; no tool run | Met. As expected. |
| TF-19 | Real client against a closed port | ModelUnavailableError, not a crash | Met. As expected. |
| TF-20 | Backend answers HTTP 500, or HTML instead of JSON | ModelUnavailableError in both cases | Met. As expected (2 variants). |
| TF-21 | Document larger than the context window | ANALYSIS_FAILED; no model call | Met. As expected. |

## 3.4 Unexpected tool and model responses

Table 5 lists each case, its expected behaviour and the result.

<!-- Table: Unexpected tool and model responses: expected and actual behaviour -->
| Case | Scenario | Expected | Result |
| --- | --- | --- | --- |
| TF-22 | Tool returns a percentage of 150 | UNEXPECTED_TOOL_RESPONSE; output discarded | Met. As expected. |
| TF-23 | Tool returns prose instead of its schema | UNEXPECTED_TOOL_RESPONSE | Met. As expected. |
| TF-24 | Tool raises an unhandled KeyError | ANALYSIS_FAILED naming the fault type only; no crash | Met. As expected. |
| TF-25 | Report percentage contradicts its results | INVALID_RESULTS naming both figures | Met. As expected. |
| TF-26 | Report results list an item twice | INVALID_RESULTS | Met. As expected. |
| TF-27 | Report result has status "Probably" | INVALID_RESULTS | Met. As expected. |
| TF-28 | Model calls a tool that does not exist | UNKNOWN_TOOL; run continues | Met. As expected. |
| TF-29 | Model arguments are broken JSON, or a list | INVALID_ARGUMENTS in both cases | Met. As expected (2 variants). |
| TF-30 | Model tool_calls field is malformed | INVALID_ARGUMENTS in both cases | Met. As expected (2 variants). |
| TF-31 | Model never stops calling tools | STEP_LIMIT_REACHED after 3 turns | Met. As expected. |
| TF-32 | Model tries to replace the document and checklist | Model values discarded; uploaded document checked | Met. As expected. |
| TF-33 | Model's final answer recommends an award | Answer withheld; tool results kept | Met. As expected. |
| TF-34 | Model requests a report before any check | NO_ANALYSIS_RESULTS, then check and report succeed | Met. As expected. |

# 4. Live Runs Against the Model

Table 6 lists runs of the agent command against the real model, Meta Llama 3.1 8B through Ollama on a CPU-only laptop. The traces are in evidence/traces/tools/.

<!-- Table: Live agent runs -->
| Run | Role | Tool calls | Outcome | Report | Seconds |
| --- | --- | --- | --- | --- | --- |
| live-01-officer-check-and-report | procurement_officer | check_document_completeness success | success | No report; check gave 66.7% | 1052.9 |
| live-02-bidder-refused | bidder | check_document_completeness UNAUTHORIZED | UNAUTHORIZED | - | 68.7 |
| live-03-model-backend-down | procurement_officer | no tool call | SERVICE_UNAVAILABLE | - | 2.1 |
| live-04-refused-request | procurement_officer | no tool call | REFUSED | - | 0.0 |

## 4.1 Observations

In live-01-officer-check-and-report, the model called the check tool and then answered directly. It did not call the report tool, although the request asked for a report. The check results were correct and were carried in the trace. The model's answer also gave the tool's status, success, as if it were the document's overall status.

Neither behaviour broke a safety rule, and no finding was invented. Both are weaknesses of the orchestration prompt, orchestrator-v1.0, with an 8B model. A later version should either state the tool order more firmly or have the application call the report tool itself after a successful check.

# 5. Reproducing the Results

The scripted cases run with python tests/evaluation/run_tool_failure_tests.py, which also rewrites this document. The live runs use python run.py agent with the options recorded at the top of each trace file.
