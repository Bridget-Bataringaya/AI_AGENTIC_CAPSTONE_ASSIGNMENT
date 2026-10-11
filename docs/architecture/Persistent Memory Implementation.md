---
title: Persistent Memory Implementation
subtitle: Case History of a Submission, Kept Between Runs
line: **Public Procurement Document-Completeness Agent (ProcureCheck)**
line: BSE4104 AI-Native and Agentic Engineering Capstone, Group H (Evening)
line: Week 6, ClickUp task 123tcvwkyv5
line: Version 0.4.0
---

[[TOC]]

[[TABLES]]

# 1. Purpose

This document describes the persistent memory added to ProcureCheck in Week 6. The task was to implement one justified persistent-memory use case. The use case chosen was case history: the result of each finished check of a submission is kept, so a later check of the same submission can be set beside it.

Until this week the application kept nothing between runs. The review queue and the procurement record lasted for one session only. Case history is the first thing that survives a restart.

# 2. The Use Case

## 2.1 The Task It Serves

A completeness check often ends with items missing. The procurement officer asks the bidder for them, and the bidder submits again. The officer then checks the new file and needs two answers. Which requested items arrived? Did anything that was present go missing?

Without memory the officer had to find the earlier report and read the two side by side. With case history the second run ends with that comparison already made.

## 2.2 Why This Use Case Was Chosen

The course brief offered three examples: an approved preference, case history, or a prior task result. Table 1 gives the reasoning for each.

<!-- Table: Candidate memory use cases and the decision on each -->
| Candidate | What it would remember | Decision | Reason |
| --- | --- | --- | --- |
| Approved preference | An officer's choices, such as a default checklist | Not chosen | It saves a few keystrokes and helps no decision the officer makes |
| Prior task result, reused | The earlier statuses, returned again when the same file is checked | Rejected | Memory would then decide an item's status without a fresh check |
| Case history, compared | The earlier statuses, shown beside the new ones | Chosen | It answers a real question and decides nothing |

Reusing a prior result was the tempting option, because a check takes several minutes on the development machine. It was rejected for that reason: a remembered status would stand in for a reading of the document. A stale or altered record could then mark a missing document as present.

# 3. What Is Stored

One record is written for each run that reaches a report. Table 2 lists every field and why it is kept.

<!-- Table: Fields of one case record and the reason for each -->
| Field | Example | Why it is kept |
| --- | --- | --- |
| Submission identifier | SYN-WORKS-2026-014 | Finds the earlier checks of the same submission |
| Document name | synthetic-submission.txt | Tells the officer which file was checked |
| Document type | Bid Document | The kind of document the checklist was applied to |
| Document fingerprint | A SHA-256 value | Shows whether the text changed, without keeping the text |
| Each item and its status | Tax clearance certificate, Present | The earlier result the new one is set beside |
| Percentage present | 66.7 | The earlier headline figure |
| Overall status | Incomplete | The earlier headline status |
| Stop reason | report_ready | How the earlier run ended |
| Recorded by | The officer's user name | Who ran the check |
| Recorded at | A time in UTC | When; retention is counted from here |
| Version | 0.4.0 | Which build produced the result |

Three things are deliberately not stored: the document text, any quotation from it, and the model's written reasons. A bid can carry personal and commercial detail. None of it is needed to say what changed, so none of it is kept. A test reads the stored file byte by byte and confirms the submission's text is absent.

The store is a single SQLite file, data/memory/case-history.sqlite3. SQLite ships with Python, so nothing was added to the dependencies. The file is excluded from version control.

# 4. How It Works

## 4.1 Place Around the Loop

Memory sits outside the workflow loop. Table 3 gives the order of events in one run.

<!-- Table: Where memory acts in one workflow run -->
| Order | Step | What happens |
| --- | --- | --- |
| 1 | Recall | The latest earlier case for the submission identifier is read and set aside |
| 2 | The loop | Sense, plan, act and observe run exactly as in Week 5, with no knowledge of step 1 |
| 3 | Compare | After the loop has stopped, the settled statuses are compared with the earlier case |
| 4 | Remember | If the run reached a report, the new case is appended |
| 5 | Report to the officer | The comparison is printed under the hand-off and written to the trace |

The recalled case is not passed to the planner, and it is not part of the workflow state. It cannot enter a prompt, because the only model call is inside the check tool, which receives the submission and the checklist alone.

## 4.2 The Comparison

Each checklist item is matched to the earlier case by its wording, ignoring letter case and outer spaces. Table 4 lists what the comparison can say about an item.

<!-- Table: What the comparison reports for one item -->
| Earlier status | Status now | Reported as |
| --- | --- | --- |
| Missing or Unclear | Present | Now present |
| Present | Missing or Unclear | No longer present; confirm by hand |
| Missing | Missing | Still missing |
| Unclear | Unclear | Still unclear |
| Missing | Unclear, or the reverse | Status changed |
| Present | Present | Counted as present both times |
| Not on the earlier checklist | Any | New on the checklist |
| Any | Not on this checklist | On the earlier checklist only |

The comparison also states whether the document text is identical to the one checked before. When the text is identical and an item's status still differs, the model has answered one question two ways. That is reported on its own line, with a request to check those items by hand. It is a second use of the same memory: it exposes an unstable reading that a single run would hide.

Every comparison ends with the same sentence. It says the comparison is advisory, that every item was checked afresh, and that the earlier result changed no status.

## 4.3 Matching a Resubmission

A resubmitted file rarely carries the same name. The workflow command therefore accepts --submission-id, which names the case a file belongs to. It defaults to the file name without its extension. The API route takes the same value as a form field.

# 5. Controls

## 5.1 Memory Decides Nothing

The design rule was that memory may inform a person and may not decide for one. It was enforced in four ways:

- The recalled case is held outside the workflow state, so the planner cannot read it.
- The comparison is computed after the loop has stopped, from statuses already settled.
- The hand-off, the report and the stop reason are built before the comparison exists.
- The trace records used_by_planner as false, beside the comparison itself.

Tests confirm it. A store was seeded with an earlier case in which every item was present. The new run still reported the bid securing declaration missing. Its decisions, its sensed state, its report and its hand-off were identical to those of a run with no memory.

## 5.2 Who Can Access It

Access is checked in code, by the same role table as the tools. Three permissions were added, so that reading, writing and deleting can be granted separately. Table 5 gives them by role.

<!-- Table: Case history permissions by role -->
| Role | Read history | Write history | Delete history |
| --- | --- | --- | --- |
| Procurement officer | Yes | Yes | Yes |
| Evaluation committee | No | No | No |
| Bidder | No | No | No |
| Guest or anonymous | No | No | No |

The committee was not given read access. The history is the officer's working material. The committee works from the published report. A bidder must never see it, since it could reveal the state of another bid.

## 5.3 Retention and Deletion

A record is kept for 180 days by default. Records past that age are deleted whenever the store is opened, by any command. An expired record is therefore never recalled, even if nobody ran a clean-up.

An officer can delete sooner. The forget action removes every record of one submission. It cannot be undone, so the operator must type the submission identifier to confirm. The purge action removes whatever is past retention at that moment.

A deleted record is overwritten in the file, not only unlinked. SQLite would otherwise leave it readable in the file's free space. A test deletes a case and then searches the file's bytes for its identifier.

Each deletion is logged with a time, a user, a cause and a count. The log does not name the submission, because a deletion log that listed what was deleted would defeat the deletion. Log entries are themselves removed at the same retention age.

The 180 days are the implementation's default. The team's own decision on what is stored, who can access it, retention and deletion is a separate Week 6 task (123tcvwkyvk). The period is one configuration value, so adopting the team's figure needs no code change.

## 5.4 Failing Safe

Memory is an aid, so its failure must cost only the aid. Table 6 gives each failure and its effect.

<!-- Table: Memory failures and their effect on a run -->
| Failure | Effect on the check | What the officer is told |
| --- | --- | --- |
| The store cannot be opened or read | None | The check was not compared with an earlier one |
| The store cannot be written | None | The check was not remembered |
| A record holds a status the application never writes | None; the record is not trusted | The check was not compared with an earlier one |
| The store was written by a newer version | None | The check was not compared with an earlier one |
| The run reached no report | Not applicable | Nothing was remembered |
| The caller's role may not read history | None | No earlier check was recalled |
| Any other fault inside memory | None | The check was not compared or not remembered |

Text is cleaned of control characters before it is stored, because it is printed at a terminal later. Every query is parameterised.

# 6. Using It

Case history is on by default and needs no set-up. The second of these two commands ends with the comparison:

    python run.py workflow --submission bid.pdf --submission-id TENDER-014
    python run.py workflow --submission bid-resubmitted.pdf --submission-id TENDER-014

The memory command shows and deletes what is remembered:

    python run.py memory list
    python run.py memory show --submission-id TENDER-014
    python run.py memory forget --submission-id TENDER-014
    python run.py memory purge

Table 7 lists the settings. A single run can also be made without memory by adding --no-memory.

<!-- Table: Case history settings -->
| Setting | Default | Effect |
| --- | --- | --- |
| PROCURECHECK_MEMORY | on | off recalls nothing and stores nothing |
| PROCURECHECK_MEMORY_DIR | data/memory | The folder that holds the store |
| PROCURECHECK_MEMORY_RETENTION_DAYS | 180 | The age at which a record is deleted |

# 7. Verification

## 7.1 Automated Tests

Memory was verified by 91 automated tests, run against a scripted model so each case is repeatable. Table 8 lists what they cover. The full suite of 430 tests passed. Line coverage of the memory package was 97%.

<!-- Table: What the memory tests cover -->
| Area | Tests | Cases |
| --- | --- | --- |
| The store | 27 | Write and read back; newest first; one submission never sees another; retention at its boundary; forget and purge; the deletion log names no submission; a forgotten case is absent from the file's bytes; an injection attempt in the identifier; control characters; a damaged file; an altered status or time; a half-created store; a newer schema |
| The comparison | 17 | Every pair of statuses; a changed checklist; a changed document; the same text with a different answer; a different version; an item with irregular spacing; the advisory line |
| Memory around the workflow | 14 | First run remembers; second run compares; an earlier all-present case changes no status, decision, report or hand-off; the model is never shown the earlier case; no document text is stored; a bidder leaves no record; a broken store, or any fault in it, costs only the comparison |
| The workflow command | 6 | Two runs end in a comparison; a submission identifier ties a renamed file to its case; --no-memory and the environment switch write nothing |
| The memory command | 24 | List, show, forget and purge; the typed confirmation; a script needs --yes; every action refused to a bidder, a guest and a committee member; a damaged store exits with 2 |
| The API route | 3 | The second request carries the comparison; a blank identifier is refused; memory off returns no memory block |

A code review of the change confirmed that the recalled case reaches no decision, prompt or status. It found no critical fault. It found four weaknesses, all fixed before release:

- Text containing a stray half-character from a PDF could not be fingerprinted, which would have failed a finished run.
- An item with a double space or a line break did not match its own earlier record.
- A store interrupted while first being created could not be opened again.
- A deleted record stayed readable in the file's free space.

## 7.2 Run Against the Real Model

The use case was run end to end against the real model, Meta Llama 3.1 8B through Ollama on a CPU-only laptop. Both runs used the same three checklist items as the Week 4 and Week 5 live runs, and the same submission identifier, SYN-WORKS-2026-014.

The first run checked the synthetic submission, which omits the anti-bribery declaration. The second checked a resubmission: the same text with that declaration added as a new section, under a different file name. Table 9 gives the two runs.

<!-- Table: Live runs of one submission, before and after resubmission -->
| Run | File | Check result | Seconds | What memory did |
| --- | --- | --- | --- | --- |
| 1 | synthetic-submission.txt | Incomplete, 66.7%: 2 present, 1 missing | 507.6 | Recalled nothing; remembered the check as case 1 |
| 2 | synthetic-resubmission.txt | Complete, 100.0%: 3 present | 672.5 | Recalled case 1; reported the change; remembered the check as case 2 |

The second run ended with these lines under its hand-off:

- Earlier check: 2026-10-06 20:22 UTC by pc, Incomplete, 66.7% of items present (ProcureCheck 0.4.0).
- The document text has changed since then.
- Now present, was Missing: Anti-bribery and anti-corruption declaration signed by the bidder
- Present both times: 2 item(s).
- This comparison is advisory. Every item was checked afresh, and the earlier result changed no status.
- This check was remembered as case 2 and is kept for 180 days.

The officer was therefore told, without opening the earlier report, that the one requested document had arrived and nothing else had changed. The second run's planning steps were the same two as the first: check, then report. Its trace records used_by_planner as false.

The memory command was then run. The list action showed one submission with two checks. The show action printed both cases with their items and fingerprints. The list action run as an evaluation committee member was refused and exited with 1.

One unplanned event tested the failure rule. On the first attempt at run 1 the model server answered with an error to the check and to its retry. The run stopped as service_unavailable and handed the case to the officer. Its trace records that nothing was remembered, and the list action then showed an empty store. The run was repeated once the server answered, and that repeat is run 1 above.

The traces and logs are in evidence/traces/memory/. The failed attempt is kept as evidence/traces/workflow/live-03-backend-error-stopped-safely.

# 8. Open Work

- The team's statement of what is stored, who can access it, retention and deletion (123tcvwkyvk) should be compared with this implementation. Its figures should be adopted as configuration.
- The team's demonstration that memory improves a task without controlling a decision (123tcvwkyvu) can use the two live traces and the tests of Section 5.1.
- The workflow and session state model (123tcvwkyum) is a separate task. Memory was kept outside the workflow state on purpose, and that boundary should be kept.
- The store is not encrypted. It relies on the access rights of its folder. Encryption at rest should be added before real bids are checked.
- Permissions are per role, not per submission. Any officer can read any case. Ownership of a submission is not yet recorded anywhere in the application.
- The API recalls and remembers, but it has no route to list or delete history. Those actions are on the command line only.
- Storing real case data may bring the operator under the Data Protection and Privacy Act, 2019, including its registration duty. That should be confirmed with the Personal Data Protection Office before any live use.

# References

Katongole, J. (2026). *Workflow implementation* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Katongole, J. (2026). *Human approval gate* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

The Data Protection and Privacy Act, 2019 (Uganda).
