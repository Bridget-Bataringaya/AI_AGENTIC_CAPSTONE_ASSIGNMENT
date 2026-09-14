# Public Procurement Document-Completeness Agent

BSE4104 AI-Native & Agentic Engineering Capstone. Group-H (Evening), Makerere University.

Checks a tender submission against a published procurement checklist and reports which
required items are present, missing, or need human review, with a page number and a
verbatim quotation as evidence for every item it claims to have found.

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
python run.py check --checklist knowledge/samples/checklist.csv --submission knowledge/samples/synthetic-submission.pdf
```

Export the report instead of printing it:

```bash
python run.py check --checklist knowledge/samples/checklist.csv --submission knowledge/samples/synthetic-submission.pdf --format csv --out report.csv
```

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
| `PROCURECHECK_PROMPT_VERSION` | `v2.0` | Prompt iteration to run, `v2.0` or `v1.0` |

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
