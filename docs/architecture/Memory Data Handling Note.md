---
title: Memory Data Handling Note
subtitle: What Is Stored, Why, Who Can Access It, Retention and Deletion
line: **Public Procurement Document-Completeness Agent (ProcureCheck)**
line: BSE4104 AI-Native and Agentic Engineering Capstone, Group H (Evening)
line: Week 6, ClickUp task 123tcvwkyvk
line: Version 0.4.4
---

[[TOC]]

[[TABLES]]

# 1. Purpose

This note records how ProcureCheck handles the data it keeps between runs. The Week 6 task was to document what is stored, why, who can access it, and how it is retained and deleted. Each statement below was checked against the code and, where possible, against an automated test.

The note has two parts. Sections 2 to 6 cover persistent memory, which is the case history added in Week 6. Section 7 covers everything else the application writes to disk, because a reader asking what the system keeps should get the whole answer.

# 2. What Is Stored

Persistent memory holds one record for each workflow run that reached a report. Table 1 lists every field, with the reason it is kept.

<!-- Table: Fields of a case record and the purpose of each -->
| Field | Example | Purpose | Personal data |
| --- | --- | --- | --- |
| Submission identifier | SYN-WORKS-2026-014 | Finds earlier checks of the same submission | Possibly, if it names a person |
| Document name | bid-resubmitted.pdf | Tells the officer which file was checked | Possibly, if it names a person |
| Document type | Bid Document | States what the checklist was applied to | No |
| Document fingerprint | A SHA-256 value | Shows whether the text changed | No |
| Each item and its status | Tax clearance certificate, Present | The earlier result the new one is compared with | No |
| Percentage present | 66.7 | The earlier headline figure | No |
| Overall status | Incomplete | The earlier headline status | No |
| Stop reason | report_ready | How the earlier run ended | No |
| Recorded by | The officer's user name | Shows who ran the check | Yes |
| Recorded at | A time in UTC | Shows when, and starts the retention period | No |
| Version | 0.4.4 | Shows which build produced the result | No |

A second, smaller table logs deletions. Each entry holds a time, a user name, a cause and a count of records removed. It never names the submission that was deleted.

## 2.1 What Is Deliberately Not Stored

Three things are left out on purpose:

- The text of the submission.
- Any quotation taken from the submission.
- The reasons the model wrote for its findings, because those reasons quote the submission.

A bid can carry personal and commercial detail. None of it is needed to say what changed between two checks. The fingerprint is a one-way value: it shows that two texts differ and cannot be turned back into either.

# 3. Why It Is Stored

The data serves one purpose. When a bidder resubmits after being asked for missing documents, the officer needs to know what changed since the last check. The record lets the next run answer that question.

The data is not used for anything else. It is not used to decide a status, to score or rank a bidder, to build a profile of a bidder, or to train a model. Memory is recalled before the workflow loop and compared only after the loop has ended, so it cannot reach a decision.

# 4. Who Can Access It

Access is decided by role and checked in code. Table 2 gives the three permissions.

<!-- Table: Case history permissions by role -->
| Role | Read | Write | Delete | Reason |
| --- | --- | --- | --- | --- |
| Procurement officer | Yes | Yes | Yes | The history is the officer's working material |
| Evaluation committee | No | No | No | The committee works from the published report |
| Bidder | No | No | No | A bidder must not learn the state of any bid through this route |
| Guest or anonymous | No | No | No | No identity, so no access |

The permissions are separate, so a role could later be given read access without the right to delete.

Three limits apply, and each is stated here so it is not mistaken for a control:

- Access is by role, not by submission. Any officer can read any case.
- The store is a file on the machine that runs ProcureCheck. A person with access to that folder can open the file with other software.
- The file is not encrypted. On a shared machine its protection is the folder's access rights.

The model has no access. The recalled record is never placed in a prompt, and the tools the model may call do not include memory.

# 5. Where It Is Stored

The store is one SQLite file, data/memory/case-history.sqlite3, on the machine that runs the check. Nothing is sent to another system. The file is excluded from version control, so it cannot be published by a commit. Its location is set by PROCURECHECK_MEMORY_DIR.

# 6. Retention and Deletion

## 6.1 Retention

A record is kept for 180 days from the time of the check. The period covers one tender from first submission to award, with margin. It is set by PROCURECHECK_MEMORY_RETENTION_DAYS and can be shortened without a code change.

Retention is applied automatically. Records past the period are deleted whenever the store is opened, by any command. An expired record is therefore never shown, even if nobody ran a clean-up. Entries in the deletion log are removed at the same age.

## 6.2 Deletion

Table 3 lists the four ways a record leaves the store.

<!-- Table: Routes by which a case record is deleted -->
| Route | Who | What it removes |
| --- | --- | --- |
| Retention | The system | Every record older than the retention period |
| python run.py memory forget --submission-id ID | A procurement officer | Every record of one submission |
| python run.py memory purge | A procurement officer | Every record past retention, at once |
| PROCURECHECK_MEMORY=off, or --no-memory on one run | The operator | Nothing is written in the first place |

The forget action cannot be undone. It therefore asks the operator to type the submission identifier before it deletes. A deleted record is overwritten in the file, not only unlinked, so it cannot be read back from the file's free space.

A bidder who asks for their history to be removed is served by the forget action. The request is made to the procuring entity, and an officer carries it out.

## 6.3 What Deletion Does Not Reach

Deleting a case record removes it from the store only. It does not remove a trace file or a report that an earlier run wrote, and it does not reach a backup of the folder. Those are covered in Section 7.

# 7. Other Data the Application Keeps

Persistent memory is the only data ProcureCheck reads back in a later run. Other data is written to disk as output or evidence. Table 4 lists all of it.

<!-- Table: Everything the application keeps, and for how long -->
| Data | Contents | Where | Kept for | Read by a later run |
| --- | --- | --- | --- | --- |
| Case history | Table 1 | data/memory/ | 180 days, then deleted automatically | Yes |
| Workflow state | The run's progress | The program's memory | The length of one run | No |
| Review tickets | Draft notes on unclear items | The program's memory | The length of one session | No |
| Procurement record | Published reports, simulated | The program's memory | The length of one session | No |
| Trace files | Each step, tool call, result and time | evidence/traces/ | Until deleted by hand | No |
| Check reports | The findings, as PDF and Word | evidence/reports/ | Until deleted by hand | No |
| Retrieval index | Passages from public PPDA documents | knowledge/index/ | Until rebuilt | Yes, by search only |

Two rows need care. A trace file holds the first 200 characters of the submission and the quotation behind each finding. A check report holds the same quotations. Neither is deleted automatically, and neither is removed when a case is forgotten. With real bids, both folders would hold bid content for as long as the operator leaves them there.

# 8. Data Protection Considerations

This section is not legal advice. Table 5 sets the handling described above beside the principles of the Data Protection and Privacy Act, 2019 of Uganda. It is written so that a qualified reviewer can see what was intended.

<!-- Table: Data protection principles and the matching control -->
| Principle | Control in ProcureCheck |
| --- | --- |
| Collect for a stated purpose | One purpose, stated in Section 3 and announced at the start of every command-line run |
| Keep what is relevant and not excessive | Statuses only; no document text, quotation or model reason |
| Keep it no longer than necessary | Deleted automatically after 180 days |
| Keep it secure | Role checks in code; a local file; excluded from version control |
| Be open about it | Each command-line run states that case history is on and how to turn it off |
| Let the person concerned act | An officer can show and delete the history of a submission on request |

The project used synthetic submissions only, so no real personal data was processed. Before real bids are checked, three matters need a decision by the procuring entity, with legal review:

- Whether the entity must register with the Personal Data Protection Office as a data collector or controller.
- Whether 180 days is the right period under the entity's own records rules.
- Whether the store and the trace files must be encrypted.

# 9. Verification

Table 6 lists each statement in this note that a test confirms. The tests are in tests/test_memory.py and were run against version 0.4.4.

<!-- Table: Statements in this note and the test that confirms each -->
| Statement | Test |
| --- | --- |
| No document text is written to the store | test_no_document_text_and_no_reason_is_written_to_the_store |
| The model is never shown the earlier case | test_the_model_is_never_shown_the_earlier_case |
| Only an officer may read or delete | test_only_an_officer_may_read_or_delete_history |
| A bidder's run leaves no record | test_a_bidder_is_refused_and_leaves_no_trace_in_memory |
| A record past retention is never recalled | test_a_case_past_retention_is_never_recalled |
| Forget removes every record of one submission | test_forget_deletes_every_case_of_one_submission_and_its_items |
| A forgotten record is gone from the file itself | test_a_forgotten_case_is_gone_from_the_file_itself |
| The deletion log does not name the submission | test_the_deletion_log_does_not_name_the_submission |
| Forget asks for the identifier to be typed | test_forget_asks_for_the_submission_id_to_be_typed |
| Memory off writes nothing | test_no_memory_recalls_nothing_and_writes_nothing |
| The identifier cannot inject a query | test_a_submission_id_cannot_inject_sql |

# 10. Open Work

- Trace files and check reports should be given a retention period, or have their quotations removed, before real bids are checked.
- The forget action should also remove the trace files and reports of the same submission, or list them for the operator.
- Access should be checked per submission once the application records who owns one.
- The store should be encrypted at rest.
- The API should gain routes to show and delete history, so the command line is not the only way.
- The retention period should be confirmed against the procuring entity's records rules.

# References

Katongole, J. (2026). *Persistent memory implementation* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Johnson, M. (2026). *Workflow and session state model* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

The Data Protection and Privacy Act, 2019 (Uganda).
