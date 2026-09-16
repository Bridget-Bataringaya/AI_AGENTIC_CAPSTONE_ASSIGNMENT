# Public Procurement Document-Completeness Agent

BSE4104 AI-Native & Agentic Engineering Capstone. Group-H (Evening), Makerere University.

Checks a tender submission against a published procurement checklist and reports which
required items are present, missing, or need human review, with a page number and a
verbatim quotation as evidence for every item it claims to have found.

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
determinations belong to the Evaluation Committee. See `docs/requirements/` for the
AI Boundary Matrix and User Stories AC6 to AC9.

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
| `evidence/` | Screenshots, traces, demo recordings |
| `tests/` | Test suite |

## Setup

Requires Python 3.10 or later and [Ollama](https://ollama.com).

```bash
pip install -r requirements.txt
ollama pull llama3.1:8b
ollama serve
```

Copy `.env.example` to `.env` and adjust if needed. Every setting has a working default,
so the agent runs with no configuration at all.

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

## Contributing

See `guide.pdf` for the team workflow. In short: work on a task branch, put the ClickUp
task ID in the branch name or commit message, place files in the folder shown in the
table above, and open a pull request to `main` for another member to review.
