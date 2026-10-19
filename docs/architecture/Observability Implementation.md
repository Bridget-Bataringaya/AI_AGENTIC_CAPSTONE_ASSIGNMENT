---
title: Observability Implementation
subtitle: Run Logs for Model, Prompt, Retrieval, Tool, Latency, Error and Outcome Evidence
line: **Public Procurement Document-Completeness Agent (ProcureCheck)**
line: BSE4104 AI-Native and Agentic Engineering Capstone, Group H (Evening)
line: Week 7, ClickUp task 123tcvwp3fm
line: Version 0.5.0
---

[[TOC]]

[[TABLES]]

# 1. Purpose

This document describes the logging added to ProcureCheck in Week 7. The task was to add logs and traces that capture useful model, prompt, retrieval, tool, latency or error, and outcome evidence.

A run log was added. Every check, workflow run, agent run and search now writes one file that records what the run did, what each step cost and how it ended. A new command reads the logs back, one run at a time or summed across runs.

# 2. What Existed and What Was Missing

Earlier weeks had already produced traces. A workflow trace recorded each planning decision and tool call. A search trace recorded the passages returned. Table 1 sets the six kinds of evidence the task names beside what existed.

<!-- Table: Evidence before Week 7 and the gap in each -->
| Evidence | Before Week 7 | Gap |
| --- | --- | --- |
| Model | The model name, once in each trace | No record of a single model call |
| Prompt | A pipeline label, once in each trace | No link between a call and the prompt that made it |
| Retrieval | A trace for each search command | Not joined to other runs; no latency |
| Tool | Each call, its result and its time | In workflow and agent traces only; a plain check had none |
| Latency and error | The time of each tool call | No model latency, no tokens, no cause of a model error |
| Outcome | The stop reason of a workflow | No common outcome across commands; no way to sum runs |

The largest gap was the model call. A check of three items took about eleven minutes, and the trace showed one tool call of eleven minutes. It could not say which item was slow, how many tokens were read, or what failed when the server was down.

# 3. The Run Log

## 3.1 One File for Each Run

Each run writes one JSON Lines file: one event to a line, in the order things happened. A run can be read alone, and many runs can be added together. Every event carries the run's identifier, a sequence number and a time in UTC.

## 3.2 The Events

Table 2 lists the eight events.

<!-- Table: Events of the run log -->
| Event | When it is written | What it records |
| --- | --- | --- |
| run_started | Once, first | The command, version, model, prompt versions, settings, caller's role, and the submission by name, fingerprint and size |
| decision | Each planning decision of the workflow | The iteration, the action, the written reason, whether it is a retry, and any stop reason |
| model_call | Each request to the model | The purpose, the item, the prompt version and fingerprint, sizes, tokens, timings, and any error |
| model_output | Each answer checked against its schema | The schema, the attempt number and whether the answer was valid |
| item_outcome | Each checklist item decided | The status, the confidence, whether the quotation was found in the submission, and the result of the evidence check |
| retrieval | Each corpus search | The query, the mode, each hit by chunk and score, the best similarity, whether evidence was sufficient, and the time |
| tool_call | Each tool call | The tool, the caller's role, the outcome, the error code, the time and any approval |
| run_finished | Once, last | The outcome, the time taken and the totals for the run |

## 3.3 The Six Kinds of Evidence

Table 3 maps the words of the task to the fields that carry them.

<!-- Table: The evidence named in the task and where it is recorded -->
| Evidence | Fields |
| --- | --- |
| Model | The model name on every call; temperature, top-p, output limit and context size; the reason generation stopped |
| Prompt | The prompt version; a fingerprint and length of the system prompt; the length of everything sent; the purpose of the call |
| Retrieval | The query, the mode asked for and used, each hit's chunk, location and scores, the similarity threshold, and whether evidence was sufficient |
| Tool | The tool name, the caller's role, success or the error code, and the approval decision |
| Latency | The time of every model call, tool call and search; time spent loading, reading the prompt and generating; tokens in and out |
| Error | The kind of error and the HTTP status of a failed model call; the error code of a failed tool call; an answer that did not match its schema |
| Outcome | The status of each item and how it was reached; the stop reason or result of the run; whether the run succeeded; the totals |

A prompt is recorded by version and fingerprint, not by its text. Every prompt version is kept in the source code, so the pair identifies the exact prompt that ran. If a prompt is edited without a new version number, its fingerprint changes and the log shows it.

## 3.4 What Is Left Out

The log holds no text from a submission. It leaves out the document text, every quotation, the prompt text and the model's answer. Sizes and counts say how much was sent without saying what.

This follows from the Week 6 data handling note, which found that trace files hold quotations from a bid and are never deleted automatically. The run log was designed not to repeat that. A test writes a log and searches it for the submission's text and for the prompt's text.

Three kinds of free text are kept, and none is bid content: the wording of a checklist item, a search query and a planning reason.

# 4. How It Was Built

## 4.1 Recording Without Changing the Code Around It

A run is recorded by wrapping it in one block. Inside the block, any part of the application can add an event without being handed a logger. Outside a block, adding an event does nothing. The model client, the engine, the tool executor, the planner loop and the retriever each gained a few lines, and no function signature changed.

The engine labels its calls. A label names the purpose of a call, the prompt version and the item. Every event written inside the label carries those fields, which is how a model call is tied to the item it was made for.

## 4.2 Recording Must Not Change a Run

Logging was held to the same rule as memory: its failure must cost only the log. Table 4 gives each failure and its effect.

<!-- Table: Logging failures and their effect on a run -->
| Failure | Effect on the run |
| --- | --- |
| An event cannot be recorded | The event is dropped; the run continues |
| The log folder cannot be written | The log is skipped and a warning is written; the run's result is unchanged |
| The run raises an error | The log is still written, with the kind of error, and the error is raised as before |
| The run reports no outcome | The log is written with the outcome unfinished |

A test ran the same workflow with and without recording. The check, the report, each decision and the hand-off were identical.

## 4.3 Where Logs Live, for How Long, and Who May Read Them

Logs are written to data/logs/, which is excluded from version control. They are kept for 90 days. Older files are deleted whenever a run writes its log. Logging is switched off with PROCURECHECK_LOGS=off.

A log names the submissions checked and who checked them. Reading the logs is therefore a permission, held by a procurement officer only. A bidder, a guest and a committee member are refused.

# 5. Using It

A run prints where its log was written. Three actions read the logs:

    python run.py logs list
    python run.py logs show latest
    python run.py logs summary

The list action gives one line for each run. The show action prints one run, event by event, and accepts the start of a run identifier. The summary action adds runs together: how they ended, the median and slowest model call, tokens, the number of failed calls and their kinds, tool error codes, item outcomes and the slowest calls. With --json it prints the same figures for a script to read.

Table 5 lists the settings.

<!-- Table: Run log settings -->
| Setting | Default | Effect |
| --- | --- | --- |
| PROCURECHECK_LOGS | on | off writes no log |
| PROCURECHECK_LOG_DIR | data/logs | The folder that holds the logs |
| PROCURECHECK_LOG_RETENTION_DAYS | 90 | The age at which a log is deleted |

A workflow or agent trace now carries the identifier and file name of its run log, so the two can be read together.

# 6. Verification

## 6.1 Automated Tests

The run log was verified by 63 automated tests. Model calls were tested against a stand-in server that answers as Ollama does, so real requests and real error responses were recorded. Table 6 lists what the tests cover. The full suite of 495 tests passed. Line coverage of the observability package was 97%.

<!-- Table: What the run log tests cover -->
| Area | Tests | Cases |
| --- | --- | --- |
| The recorder | 17 | Header and totals; labels; one outcome only; an unfinished run; a run that raises; logs switched off; an unwritable folder; an event that cannot be recorded; text that cannot be encoded; a fault while closing the log; control characters removed; retention that deletes only its own files |
| Model calls | 13 | Prompt, sizes, tokens and timings; the evidence check under its own prompt; no document, prompt or answer text in the log; item outcomes; an HTTP error; an unreachable server; an answer that is not JSON; a schema failure and its retry; four oddly shaped answers; a tool-calling turn |
| Tool calls | 4 | A successful call; a refused caller with no model call; an anonymous caller and an unknown tool; a tool name the model made up is not logged |
| Workflow decisions | 3 | Every decision with its reason, including the stop; a retry marked as a retry; recording changes nothing the run decides |
| Retrieval | 4 | Scores and sources without passages; no evidence; a fallback to keywords; a rejected query |
| Commands | 19 | A workflow run writes a log named in its trace; a refused run; logs switched off; list, show and summary; summary as JSON; show by the start of an identifier; nothing logged; every action refused to a bidder, a guest and a committee member; a damaged line |
| Summary and API | 3 | Percentiles; runs added together; the API route logs its run and returns the identifier |

A code review of the change found no critical or serious fault. It confirmed that no bid text, quotation, prompt text or model answer reaches an event, with one exception that was then closed. It found seven weaknesses, all fixed before release:

- Text that could not be encoded, such as a damaged file name, made the log fail to write and could hide the run's own error.
- An oddly shaped answer from the model server could make a successful call fail while it was being recorded.
- A tool name invented by the model was logged as written, so a crafted document could have placed its own text in the log.
- The median was computed with the wrong rounding and was overstated for an even number of calls.
- Retention would have deleted any old file with the log's extension in the log folder, not only run logs.
- Control characters in a file name or a query were kept, and would have been replayed at the terminal.
- A summary of the last zero runs reported that nothing was logged.

## 6.2 Runs Against the Real Model

Four runs were logged against the real model, Meta Llama 3.1 8B through Ollama on a CPU-only laptop, on 13 October 2026. Table 7 gives them. The logs are in evidence/traces/observability/.

<!-- Table: Live runs recorded by the run log -->
| Run | Outcome | Seconds | Model calls | Failed | Tool calls | Failed |
| --- | --- | --- | --- | --- | --- | --- |
| A search of the corpus | results | 5.0 | 0 | 0 | 0 | 0 |
| A workflow check of three items | report_ready | 680.6 | 5 | 0 | 2 | 0 |
| The same, with the server unreachable at the start | report_ready | 793.7 | 6 | 1 | 3 | 1 |
| The same, run as a bidder | unauthorized | 0.0 | 0 | 0 | 1 | 1 |

The summary action added the four runs together. It reported eleven model calls, one failed as ConnectError. The median model call took 168.2 seconds and the slowest 241.3. The model read 17,736 tokens and wrote 898. The tool errors were one UNAUTHORIZED and one SERVICE_UNAVAILABLE. Four items were Found and two Not Found, and every quotation was found in the submission.

The third run shows what the log adds. Its trace recorded a failed check and a successful retry. Its log recorded why: the first model call failed after 2.1 seconds with a connection error and no HTTP status, so the server was unreachable and had not answered with an error of its own. The retry then made five calls, and the log gives the time and tokens of each.

The live runs were made on the development build, before the version was raised to 0.5.0. Their logs carry version 0.4.3 or 0.4.5.

## 6.3 What the Logs Showed About Speed

The logs answered a question the traces could not: where the eleven minutes go. Table 8 gives the five model calls of the second run.

<!-- Table: Model calls of one workflow check, from its run log -->
| Call | Prompt tokens | Output tokens | Reading the prompt (s) | Generating (s) | Total (s) |
| --- | --- | --- | --- | --- | --- |
| Verify item 1 | 2,367 | 132 | 107.4 | 90.5 | 200.9 |
| Check the evidence for item 1 | 881 | 51 | 18.5 | 27.5 | 46.4 |
| Verify item 2 | 2,372 | 78 | 109.8 | 56.9 | 168.2 |
| Verify item 3 | 2,364 | 135 | 108.8 | 105.7 | 215.4 |
| Check the evidence for item 3 | 884 | 53 | 18.7 | 27.4 | 48.5 |

Three findings follow. First, the model spent about 108 seconds reading the prompt on each verification call, and the prompt was almost the same each time. Close to half of the run was spent re-reading the same submission. Second, an item that was missing was the quickest to decide, because the model wrote the least. Third, the evidence check added about 47 seconds for each item found, a fifth of that item's time.

The first finding points to a possible saving, which was not tested. Two things may stop the server reusing what it has already read. The checklist item is placed before the submission text, so two requests differ before the submission begins. The evidence check also runs between two verifications, under a different prompt. Both should be tried and measured with the run log.

# 7. Use for the Week 7 Evaluation

The team's evaluation criteria include task completion, groundedness, tool selection, instruction following, latency and safety violations. Table 9 shows which log fields can feed each. The scoring itself belongs to the evaluation tasks.

<!-- Table: Evaluation criteria and the log fields that can feed them -->
| Criterion | Log fields |
| --- | --- |
| Task completion | The outcome of run_finished; the stop reason; item outcomes present for every item |
| Groundedness | quotation_grounded and evidence_check on each item_outcome; evidence_sufficient on each retrieval |
| Tool selection | The sequence of tool_call events; tools offered and calls proposed on each tool-calling model call |
| Instruction following | Valid and invalid model_output events; retries; decisions against the planning rules |
| Latency | latency_ms on model calls and searches; duration_ms on tool calls; seconds on the run |
| Safety violations | UNAUTHORIZED, REFUSED and approval outcomes on tool_call events; a refused outcome on a run |

# 8. Open Work

- Two changes should be tried and measured with the run log: placing the submission before the checklist item, and running the evidence checks after all the verifications.
- The API's check and agent routes are not yet recorded. Only the workflow route is.
- The terminal still prints a long error trace when the model server is down. The log now holds the cause, so the terminal message can be shortened.
- Logs are files on one machine. A deployment with several officers would need them collected in one place.
- The guardrail work on another member's branch changes the API. It should be merged before the API routes are instrumented further.
- A refusal by the safety screen is recorded only as the run's outcome. It should be given an event of its own.

# References

Katongole, J. (2026). *Workflow implementation* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Katongole, J. (2026). *Memory data handling note* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Ollama. (2026). *Ollama API documentation: Generate a chat completion*. https://github.com/ollama/ollama/blob/main/docs/api.md
