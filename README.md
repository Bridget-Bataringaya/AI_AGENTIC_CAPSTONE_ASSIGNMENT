# Public Procurement Document-Completeness Agent

**Release v1.0.0** (23 October 2026). BSE4104 AI-Native & Agentic Engineering Capstone. Group H (Evening), Makerere University.

Checks a sample tender submission against a published procurement checklist, locates
required clauses with page and chunk citations, and produces an auditable missing-item
report. Every item it claims to have found carries a page number and a verbatim quotation.

Authors: Mwesigwa Isaac (23/U/12539/PS), Bataringaya Bridget (23/U/07471/EVE),
Jonathan Katongole (23/U/27072/EVE), Makmot Johnson Kabira (23/U/26794/EVE).

## How it decides

Every item goes through the model twice.

The first pass reads the submission and proposes an answer. The second pass is
shown the requirement and the quotation the first pass returned, and nothing
else, and is asked one question: is this the required document, or a different
one? A quotation the second pass rejects is reported as Not Found with the
reason attached, not as a match.

The second pass exists because of a measured failure. Searching a document for
a requirement always offers a nearest match, and a model asked to search and to
judge in one breath judges in favour of what it has just found: the baseline
returned the bidder's conflict of interest declaration for the required
anti-bribery declaration, and its certificate of registration for the required
certificate of non-blacklisting. Both quotations were real, so grounding passed
them; both came back at confidence 0.95, so the review threshold passed them
too. Nothing deterministic tells one declaration from another, so the judgement
stays with the model and only the question changes. Withhold the document and
the task stops being a search.

Three deterministic guards still run on top of both passes: the quotation must
really appear in the submission, the page number must exist, and a match below
the confidence threshold is routed to a human rather than reported as found.

## What it will not do

The safety boundary is enforced in code, not only in the prompt. The system refuses to
score, grade or rate a submission; to rank or compare bidders; to comment on the legal
validity of a clause; or to recommend awarding, rejecting or disqualifying a bid. These
determinations belong to the Evaluation Committee. A completeness report cannot reach
the procurement record without a `procurement_officer` signing off
(`publish_completeness_report` is held by the executor until that happens). See
`docs/requirements/` for the AI Boundary Matrix and User Stories AC6 to AC9.

## Layout

| Path | Contents |
| --- | --- |
| `src/procurecheck/` | Application code |
| `docs/requirements/` | Charter, user stories, boundary matrix, use case |
| `docs/architecture/` | Architecture and context diagram |
| `docs/evaluation/` | Prompt evaluation tables |
| `docs/weekly-reports/` | Weekly progress reports |
| `prompts/` | Prompt specification and version history |
| `knowledge/checklists/` | The bundled standard checklist, used when none is named |
| `knowledge/samples/` | Synthetic checklist and submission for testing |
| `knowledge/corpus/` | The controlled corpus: 30 PPDA documents and 5 synthetic bids, with provenance |
| `knowledge/index/` | The retrieval index, built locally and not committed |
| `data/memory/` | The case history store, written locally and not committed |
| `data/logs/` | The run logs, written locally and not committed |
| `evidence/` | Screenshots, traces, demo recordings. `evidence/traces/` holds captured live and scripted runs |
| `tests/` | Test suite |
| `scripts/verify_release.sh` | One-command v1.0.0 verification (pytest + scripted checks, no model) |

## Setup

Requires Python 3.11 or later. A live check also needs [Ollama](https://ollama.com).
The release verification in the next section does not.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
ollama pull llama3.1:8b
ollama pull nomic-embed-text
ollama serve
```

`nomic-embed-text` (274 MB) is only needed for corpus search. Without it, search
falls back to keywords and says so.

Copy `.env.example` to `.env` and adjust if needed. Every setting has a working default,
so the agent runs with no configuration at all. The application reads
`PROCURECHECK_BASE_URL` (default `http://localhost:11434`, the same endpoint Ollama
documents as `OLLAMA_HOST`) and writes case history to
`data/memory/case-history.sqlite3`.

## Reproducible Release Verification (`v1.0.0`)

Three ways to confirm this tag. Option A and Option C need no GPU and no Ollama.

### Option A — One-Command Local Verification (No Ollama/GPU, <30s)

```bash
git clone --branch v1.0.0 https://github.com/Bridget-Bataringaya/AI_AGENTIC_CAPSTONE_ASSIGNMENT.git
cd AI_AGENTIC_CAPSTONE_ASSIGNMENT
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .
bash scripts/verify_release.sh
```

The script prints the Python and package versions (procurecheck 1.0.0), runs the
full pytest suite, then the scripted memory demonstration
(`python tests/evaluation/run_memory_demonstration.py --scripted`). That demonstration
re-runs one submission three times (memory off, truthful memory, false memory) and
fails if memory changes a decision. The approval gate
(`tests/test_approval.py`) and the Unclear re-check branch (`tests/test_workflow.py`)
are in the pytest suite. `python run.py verify --quick` is the last step: five
deterministic checks, no model.

### Option B — Live Model Run (Meta Llama 3.1 8B via Ollama)

```bash
ollama pull llama3.1:8b
ollama serve
python run.py health
python run.py check --submission knowledge/samples/synthetic-submission.pdf
python tests/evaluation/run_memory_demonstration.py
python run.py workflow --submission knowledge/samples/synthetic-submission.pdf --publish
```

`health` confirms the backend. `check` runs a live tender completeness audit against
the synthetic sample. The memory demonstration (without `--scripted`) repeats the
three-arm comparison against the real model. `workflow --publish` exercises the
interactive approval gate: a `procurement_officer` must type APPROVE at the terminal
before `publish_completeness_report` runs. Piped input is never treated as sign-off.

A live check on CPU-only hardware takes several minutes per item. Measured workflow
runs of three items have taken about 500 to 680 seconds.

### Option C — Docker

```bash
docker build -t procurecheck:v1.0.0 .
docker run --rm procurecheck:v1.0.0
```

The image installs the package and runs `scripts/verify_release.sh` as its default
command. No Ollama server is started inside the container.

## Running a check

Confirm the model backend is reachable:

```bash
python run.py health
```

Run a completeness check against the synthetic sample:

```bash
python run.py verify --quick
```

That is the fastest way to tell the system is working: five checks, no model
needed, instant. Drop `--quick` to add real model calls against a document whose
contents are known: one item that is in it, one that is not, and one that is not
there but has a close relative on the same page. The third is the case the
evidence check exists to catch, so a run where that check has quietly stopped
working fails here rather than in a report someone signs. It takes several
minutes and proves the whole pipeline end to end.

```bash
python run.py check --submission knowledge/samples/synthetic-submission.pdf
```

The second pass roughly doubles the number of model calls for items the first
pass claims to have found, though each one is short because it carries the
quotation rather than the document. To time the single-pass baseline, or to
trade accuracy for speed on a long checklist:

```bash
python run.py check --submission knowledge/samples/synthetic-submission.pdf --no-evidence-check
```

A check writes a PDF to `evidence/reports/<submission>-completeness-report.pdf`.
The PDF is the report of record for a procurement officer. While the project is
in development, a Word copy with identical content is written beside it, so the
team can review and correct the wording. Set `PROCURECHECK_WORD_COPY=off`, or pass
`--no-word-copy`, to produce the PDF alone.

Export the findings as data instead:

```bash
python run.py check --submission knowledge/samples/synthetic-submission.pdf --format csv --out report.csv
```

### Reading a report

A status on its own does not say what happened, so every item in the report
states five things:

- **What had to be present.** The document the submission needed to contain, and
  what the system needed to see before it could report it Found.
- **What the system did.** Each stage it ran: the pages the model was given, what
  the model claimed, whether the quotation exists in the submission, and what the
  evidence check decided.
- **Evidence.** The page and quotation relied on, or the rejected quotation and
  its page, or a statement that nothing was returned.
- **Result.** The status and what it does and does not establish.
- **Next step.** What the procurement officer does about it.

Not Found is not proof of absence. It means no text in the submission was
accepted as that document, and the report says whether that is because the model
found nothing or because the passage it offered turned out to be a different
document. The CSV and JSON exports carry the same `what_happened` and `next_step`
text.

Every report, the PDF and the Word copy alike, follows the team's Document
Format Standard: Times New Roman 12 point, 1.5 line spacing, justified text,
numbered headings, each main section on a new page, captions above tables, and
no page number on the title page.

## Running the API

```bash
python run.py api --reload
```

Interactive documentation is then at `http://localhost:8000/docs`.

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Confirm the backend and model are reachable |
| `POST /checklist/parse` | Extract required items so the user can edit them |
| `POST /check` | Run a completeness check for one submission |
| `GET /tools` | Each tool's purpose, input and output schema, and permission |
| `POST /tools/{name}` | Call one tool directly. Needs an `X-API-Key` header |
| `POST /agent` | Let the model choose and call the tools on one submission. Needs an `X-API-Key` header |
| `POST /workflow` | Run the multi-step workflow on one submission and return its trace. Needs an `X-API-Key` header |

## Tool calling

The agent has four tools. Two are defined in the team's Tool / Function Specification:
`check_document_completeness` and `generate_completeness_report`. The other two are
used only by the application and never offered to the model: `create_review_ticket`
opens a draft ticket for an item the check could not decide, and
`publish_completeness_report` adds a report to the (simulated) procurement record.
The model proposes
calls; the application runs them. Every call, from the model, the API or a test,
goes through one executor (`src/procurecheck/tools/registry.py`) that checks, in
order, that the tool exists, that the caller may use it, that the arguments match
the schema, and that the answer matches the schema. Each failure ends in the
specification's error envelope with a named code, never a crash.

```bash
python run.py tools
python run.py agent --submission knowledge/samples/synthetic-submission.pdf
python run.py agent --submission knowledge/samples/synthetic-submission.pdf --role bidder
```

The model never sees the document or the checklist. The application binds them to
the tools, and anything the model writes into those fields is discarded, so text
inside a submission cannot redirect a check. Every run writes a trace to
`evidence/traces/tools/`.

Roles decide which tool may run: a `procurement_officer` may check and report, an
`evaluation_committee` member may only report, a `bidder` or `guest` may do neither.
Over the API the caller is identified by `X-API-Key`, with keys read from
`PROCURECHECK_API_KEYS` as `key:role:user` entries, comma separated. With no keys set,
every tool route refuses.

The design is in `docs/architecture/Tool Calling Implementation.docx`. The failure
cases (missing parameters, unauthorized requests, unavailable services, unexpected
responses) are run and tabulated by `python tests/evaluation/run_tool_failure_tests.py`,
which writes `docs/evaluation/tool-failure-tests.docx`.

### Human approval

Publishing a report is the one higher-impact action: the team's AI Boundary Matrix
says a report may not reach the procurement record without an officer's sign-off.
The executor therefore holds `publish_completeness_report` until a person with
sign-off rights approves it, after the permission and argument checks and before
the tool runs. No approver, a decline, no answer, or a yes from someone without
sign-off rights all refuse it, and nothing is recorded. Over the API no person is
present during a request, so a publish call ends as `APPROVAL_REQUIRED` (HTTP 428).
The design is in `docs/architecture/Human Approval Gate.docx`.

## The workflow

`workflow` runs the whole task on one submission by direct orchestration: the
application, not the model, decides each next step. Each iteration senses the
state, plans the next action, acts through the same executor, and observes the
result. It checks every item, re-checks items that came back Unclear, opens a
review ticket for any that stay Unclear, generates the report and, with
`--publish`, asks the officer at the terminal to sign off before publishing.
It retries once after a model outage, drops a failed optional step and carries
on, and stops within its iteration limit. Every run ends in a hand-off to a
procurement officer and writes a trace to `evidence/traces/workflow/`. It exits with 0 when the report is
ready or published, 1 when refused or failed, 2 when the model server stayed down,
and 4 when publishing was asked for but not approved. A sign-off is accepted only
when typed at an interactive terminal; an answer piped in by a script declines.

```bash
python run.py workflow --submission knowledge/samples/synthetic-submission.pdf
python run.py workflow --submission knowledge/samples/synthetic-submission.pdf --publish
python run.py --version
```

The design is in `docs/architecture/Workflow Implementation.docx`.

Six recorded runs against the real model, including an outage the run recovered from and one it
stopped safely on, are set out in `docs/evaluation/workflow-execution-traces.docx`. The recovery
case is reproduced by `python tests/evaluation/run_outage_recovery.py`, which keeps the model
server unreachable for the first 15 seconds of a run.

## Case history (persistent memory)

A check often ends with items missing, the bidder is asked for them, and the bid
comes back. Every `workflow` run that reaches a report therefore remembers the
submission's result, and the next run of the same submission ends with what
changed: which items are now present, which are still missing, and whether
anything that was present has gone.

```bash
python run.py workflow --submission knowledge/samples/synthetic-submission.txt --submission-id SYN-WORKS-2026-014
python run.py workflow --submission knowledge/samples/synthetic-resubmission.txt --submission-id SYN-WORKS-2026-014
python run.py memory list
python run.py memory show --submission-id SYN-WORKS-2026-014
python run.py memory forget --submission-id SYN-WORKS-2026-014
python run.py memory purge
```

What it keeps is each item's status, the percentage, a fingerprint of the text,
who ran the check and when. It keeps no document text, no quotation and none of
the model's reasons. `--submission-id` ties a resubmission under another
filename to its case; without it the filename is used.

Memory informs the officer and decides nothing. The earlier check is recalled
before the loop and compared only after the loop has stopped, so it reaches no
planning decision, no prompt and no status: every item is checked afresh. When
the text is identical and the answer still differs, the comparison says so and
asks for a check by hand.

Only a procurement officer may read, write or delete history. Records are
deleted after 180 days (`PROCURECHECK_MEMORY_RETENTION_DAYS`), `forget` deletes
one submission's records after the operator types its id, and
`PROCURECHECK_MEMORY=off` or `--no-memory` keeps nothing. A store that cannot be
read costs the run its comparison and nothing else. The design is in
`docs/architecture/Persistent Memory Implementation.docx`.

What is stored, why, who can access it, and how it is retained and deleted is set out
in `docs/architecture/Memory Data Handling Note.docx`. A live comparison of three runs
(memory off, a truthful earlier case, and a false one) is in
`docs/evaluation/memory-demonstration.docx`, and is repeated with
`python tests/evaluation/run_memory_demonstration.py` (`--scripted` for an instant check).

## Run logs

Every `check`, `workflow`, `agent` and `search` run writes one JSON Lines file to
`data/logs/`: one event to a line, in the order things happened. A log records each
model call (prompt version and fingerprint, sizes, tokens, time, any error), whether
each answer matched its schema, the verdict on each checklist item and how it was
reached, each search with its scores, each tool call with its outcome, each planning
decision, and how the run ended.

```bash
python run.py logs list
python run.py logs show latest
python run.py logs summary
python run.py logs summary --json
```

`list` gives one line for each run. `show` prints one run, event by event, and takes
the start of a run id. `summary` adds runs together: outcomes, median and slowest
model call, tokens, failed calls by kind, tool error codes and the slowest calls.

A log holds no text from a submission: no document text, no quotation, no prompt text
and no model answer. A prompt is recorded as its version, a fingerprint and a length.
Logging never changes a run: an event that cannot be recorded is dropped, and a log
that cannot be written is skipped. Only a procurement officer may read the logs. They
are deleted after 90 days (`PROCURECHECK_LOG_RETENTION_DAYS`), and
`PROCURECHECK_LOGS=off` writes none. The design, and what the first logs showed about
where a check's time goes, is in `docs/architecture/Observability Implementation.docx`.

## Searching the corpus

The team's controlled corpus lives in `knowledge/corpus/`: 30 public PPDA documents
(standard bidding documents, user guides, guidelines and the 2023 procurement
regulations) and 5 synthetic tender submissions. `CORPUS_MANIFEST.csv` lists them and
`Public_Procurement_Corpus_Provenance_Register.pdf` records where each came from.
Some file names are long, so on Windows run `git config core.longpaths true` in the
repository if a checkout reports "Filename too long".

Build the index once, then search it:

```bash
python run.py index
python run.py search "what form of bid security is required for open bidding"
```

Each result names its document, page, section heading and chunk id, and says whether
keyword search, meaning search or both found it. Every search writes its full trace
to `evidence/traces/retrieval/`. Add `--doc DOC-030` to search one document,
`--mode bm25` or `--mode dense` to use one search alone, and `--json` for the trace.

How it works, one module per stage in `src/procurecheck/retrieval/`:

| Stage | Module | What it does |
| --- | --- | --- |
| Ingestion | `corpus.py` | Reads the manifest and resolves each document to readable text |
| Segmentation | `segment.py` | Splits a document into blocks in reading order, each carrying its heading and page |
| Chunking | `chunking.py` | Packs blocks into passages of about 220 words that never cross a heading |
| Keyword index | `lexical.py` | BM25 over each passage with its document title and heading prepended |
| Meaning index | `embeddings.py` | `nomic-embed-text` vectors from the local Ollama server |
| Retrieval | `retriever.py` | Runs both searches and fuses the rankings by reciprocal rank |

Eight documents cannot be read as filed. Five are legacy Word 97-2003 files, converted
to `.docx`; three are scanned PDFs with no text layer, read by OCR. The derived text is
in `knowledge/corpus/derived/` and `DERIVATIONS.csv` records how each file was made. A
passage from OCR text is labelled as such wherever it is shown, because OCR errors are
not corrected.

A rebuild re-embeds only passages whose text changed. Embedding runs at about one
passage per second on a CPU-only machine, so the first build of the full corpus takes
roughly an hour and later rebuilds take minutes.

Measure retrieval quality with `python run.py evaluate-retrieval`, which runs the
labelled queries in `tests/evaluation/retrieval_cases.py` through keyword, meaning and
hybrid search and writes `docs/evaluation/retrieval-evaluation.md`.

## Tests

```bash
python run.py test
```

The suite runs without a model server: the engine tests use a stubbed client, so the
deterministic behaviour (confidence threshold, snippet grounding, page validity, safety
refusals) is verified independently of model output.

## Evaluation

The team's ten test cases, TC01 to TC10 from
`docs/evaluation/test-cases/Public Procurement Agent - 10 Test Cases.docx`, run
through the application with their own checklists, submissions and requests:

```bash
python run.py evaluate --suite team
```

Each case in `docs/evaluation/team-test-case-evaluation.pdf` (and `.docx`, `.md`,
`.csv`) sets the expected behaviour beside the actual behaviour in full, with an
observation stating the difference. Do not check the test-case document itself
with `check`: it is not a tender submission, so almost every item comes back Not
Found and the result measures nothing.

The built-in prompt evaluation is `python run.py evaluate`. To regenerate the
reports of a past run from its saved trace, without any model calls, add
`--rebuild` (and `--suite team` or `--name STEM` to choose the run). See
`docs/evaluation/how-to-run-the-evaluation.md`.

## Synthetic test data

`knowledge/samples/` holds a ten-item checklist and a seven-page synthetic submission.
The submission is fictional and contains no real bidder, entity or confidential
information, in line with the Project Charter's data-access constraint. Seven items are
present and worded differently from the checklist, so the run tests semantic matching
rather than keyword matching. Three are omitted deliberately:

- `CHK-05` Anti-bribery and anti-corruption declaration
- `CHK-07` Beneficial ownership disclosure form
- `CHK-10` Certificate of non-blacklisting or non-debarment

Regenerate the submission with `python knowledge/samples/generate_submission.py`.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `PROCURECHECK_MODEL` | `llama3.1:8b` | Model name |
| `PROCURECHECK_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `PROCURECHECK_TEMPERATURE` | `0.0` | Fixed by the Model Selection Note |
| `PROCURECHECK_TOP_P` | `0.9` | Fixed by the Model Selection Note |
| `PROCURECHECK_MAX_OUTPUT_TOKENS` | `2048` | Fixed by the Model Selection Note |
| `PROCURECHECK_CONTEXT_TOKENS` | `16384` | Context window requested from Ollama |
| `PROCURECHECK_HUMAN_REVIEW_THRESHOLD` | `0.85` | Below this, route to human review |
| `PROCURECHECK_STRATEGY` | `per_item` | `per_item` or `batch` |
| `PROCURECHECK_PROMPT_VERSION` | `v2.0` | First-pass prompt iteration, `v2.0` or `v1.0` |
| `PROCURECHECK_ADJUDICATE` | `on` | The second pass. `off` reproduces the single-pass baseline |
| `PROCURECHECK_ADJUDICATOR_PROMPT_VERSION` | `adjudicator-v1.0` | Second-pass prompt |
| `PROCURECHECK_ADJUDICATION_CONFLICT_SCORE` | `0.60` | A rejection still scoring the passage this highly goes to a human instead |
| `PROCURECHECK_WORD_COPY` | `on` | Write a Word copy beside each check PDF. For development; `off` for the PDF alone |
| `PROCURECHECK_EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model for corpus search |
| `PROCURECHECK_INDEX_DIR` | `knowledge/index` | Where the retrieval index is written and read |
| `PROCURECHECK_RETRIEVAL_MIN_COSINE` | `0.65` | Below this best similarity, a search reports that the corpus holds no evidence |
| `PROCURECHECK_MEMORY` | `on` | Remember each finished workflow check so the next one can show what changed. `off` keeps nothing |
| `PROCURECHECK_MEMORY_DIR` | `data/memory` | Where the case history store is kept |
| `PROCURECHECK_MEMORY_RETENTION_DAYS` | `180` | Records older than this are deleted |
| `PROCURECHECK_LOGS` | `on` | Write a run log for every check, workflow, agent run and search. `off` writes none |
| `PROCURECHECK_LOG_DIR` | `data/logs` | Where the run logs are kept |
| `PROCURECHECK_LOG_RETENTION_DAYS` | `90` | Logs older than this are deleted |
| `PROCURECHECK_API_KEYS` | unset | `key:role:user` entries for the tool routes. Unset means every tool route refuses |

### A note on the context window

Llama 3.1 8B supports 128,000 tokens, but Ollama defaults `num_ctx` to 4,096 and
silently discards anything beyond it. Left unset, a long tender pack would be truncated
and documents that are present would be reported as missing. The window is therefore
always requested explicitly.

The default is 16,384 rather than 128,000 because the KV cache for this model costs
roughly 128 KB per token, so a full 128,000-token window needs about 16 GB of memory on
top of the weights. 16,384 tokens costs about 2 GB and holds roughly 45 pages. Raise
`PROCURECHECK_CONTEXT_TOKENS` on a machine with more memory. Input above the configured
budget is refused with a clear error rather than silently truncated.

## Known limitations at v1.0.0

These match the Week 6 and Week 7 reports and the architecture notes.

- **CPU inference latency.** A median model call on the development laptop took 168.2 seconds. A live workflow check of three items has taken about 680 seconds. The Week 7 latency target (95th percentile of 10 seconds) cannot be met on that hardware.
- **Unencrypted local stores.** Case history is a local SQLite file with no encryption. Trace files and reports retain verbatim quotations from the submission and are not deleted when a case is forgotten. Both remain pending legal review under the Data Protection and Privacy Act 2019 before real bids are checked.
- **Role-level access control.** Any procurement officer can read any case. There is no per-submission access control.
- **Unclear re-check.** The re-check of Unclear items and the review-ticket step are covered by scripted tests (`tests/test_workflow.py`). Live traces against Llama 3.1 8B did not produce an Unclear item, so those branches have not been captured on the real model.
- **Completeness percentage.** The report still states a percentage of items present. Week 1 ruled out scores; this conflict is recorded as an open point in the Week 7 report (scenario TC22).

## Contributing

See `guide.pdf` for the team workflow. In short: work on a task branch, put the ClickUp
task ID in the branch name or commit message, place files in the folder shown in the
table above, and open a pull request to `main` for another member to review.
