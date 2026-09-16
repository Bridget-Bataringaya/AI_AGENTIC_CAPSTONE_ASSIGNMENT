"""Measure retrieval quality: keyword, meaning and hybrid search side by side.

    python run.py evaluate-retrieval

Needs a built index (`python run.py index`) and Ollama running with the
embedding model. Writes docs/evaluation/retrieval-evaluation.md and .csv, and
the full ranked lists to evidence/traces/retrieval-evaluation-raw.json.

For each answerable query it records where the first relevant passage ranked.
For each out-of-corpus query it records how similar the nearest passage looked,
because that is the number the evidence-sufficiency threshold has to beat.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from procurecheck.config import Settings  # noqa: E402
from procurecheck.retrieval.chunking import Chunk  # noqa: E402
from procurecheck.retrieval.commands import index_dir  # noqa: E402
from procurecheck.retrieval.embeddings import OllamaEmbedder  # noqa: E402
from procurecheck.retrieval.index import CorpusIndex  # noqa: E402
from procurecheck.retrieval.retriever import (  # noqa: E402
    MODE_BM25,
    MODE_DENSE,
    MODE_HYBRID,
    Retriever,
    SearchResult,
    min_cosine_from_env,
)

from retrieval_cases import ANSWERABLE, CASES, OUT_OF_CORPUS, RetrievalCase  # noqa: E402

EVALUATION_DIR = REPO_ROOT / "docs" / "evaluation"
TRACES_DIR = REPO_ROOT / "evidence" / "traces"
DEPTH = 10
MODES = (MODE_BM25, MODE_DENSE, MODE_HYBRID)
MODE_NAMES = {MODE_BM25: "Keyword (BM25)", MODE_DENSE: "Meaning (embeddings)", MODE_HYBRID: "Hybrid (RRF)"}


def is_relevant(case: RetrievalCase, chunk: Chunk) -> bool:
    if case.documents and chunk.doc_id not in case.documents:
        return False
    return all(re.search(pattern, chunk.text, re.IGNORECASE) for pattern in case.must_match)


def first_relevant_rank(case: RetrievalCase, result: SearchResult) -> Optional[int]:
    for hit in result.hits:
        if is_relevant(case, hit.chunk):
            return hit.rank
    return None


def _summary(ranks: Sequence[Optional[int]]) -> Dict[str, float]:
    return {
        "hit@1": sum(1 for r in ranks if r == 1) / len(ranks),
        "hit@5": sum(1 for r in ranks if r is not None and r <= 5) / len(ranks),
        "hit@10": sum(1 for r in ranks if r is not None) / len(ranks),
        "mrr@10": mean(1 / r if r else 0.0 for r in ranks),
    }


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _rank_cell(rank: Optional[int]) -> str:
    return str(rank) if rank else f"not in top {DEPTH}"


def main() -> int:
    settings = Settings.from_env()
    index = CorpusIndex.load(index_dir())
    if not index.has_vectors:
        print("The index has no embeddings. Rebuild with `python run.py index`.", file=sys.stderr)
        return 1
    threshold = min_cosine_from_env()
    answerable = [c for c in CASES if c.kind == ANSWERABLE]
    unanswerable = [c for c in CASES if c.kind == OUT_OF_CORPUS]

    rows: List[Dict[str, object]] = []
    raw: List[Dict[str, object]] = []
    with OllamaEmbedder(settings.base_url, str(index.meta["embedding_model"])) as embedder:
        retriever = Retriever(index, embedder, threshold)
        for case in CASES:
            row: Dict[str, object] = {"case": case.case_id, "kind": case.kind, "query": case.query}
            for mode in MODES:
                result = retriever.search(case.query, top_k=DEPTH, mode=mode)
                rank = first_relevant_rank(case, result) if case.kind == ANSWERABLE else None
                row[f"{mode}_rank"] = rank
                if mode == MODE_HYBRID:
                    row["best_cosine"] = result.best_cosine
                    row["top_hit"] = result.hits[0].chunk.location if result.hits else ""
                    row["flagged_sufficient"] = result.evidence_sufficient
                raw.append({"case": case.case_id, "relevant_rank": rank, **result.to_trace()})
            rows.append(row)
            print(f"{case.case_id} " + " ".join(f"{m}={_rank_cell(row[f'{m}_rank'])}" for m in MODES), file=sys.stderr)

    summaries = {m: _summary([r[f"{m}_rank"] for r in rows if r["kind"] == ANSWERABLE]) for m in MODES}
    answerable_cos = [float(r["best_cosine"]) for r in rows if r["kind"] == ANSWERABLE]
    ooc_cos = [float(r["best_cosine"]) for r in rows if r["kind"] == OUT_OF_CORPUS]
    meta = index.meta
    stamp = datetime.now().isoformat(timespec="minutes")

    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    with (EVALUATION_DIR / "retrieval-evaluation.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (TRACES_DIR / "retrieval-evaluation-raw.json").write_text(
        json.dumps({"run_at": stamp, "index": {k: meta[k] for k in ("built_at", "chunks", "embedding_model")}, "results": raw}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        "# Retrieval Evaluation",
        "",
        f"Run {stamp} over the index built {meta['built_at']}: {meta['documents']} documents, "
        f"{meta['chunks']} chunks, embeddings from `{meta['embedding_model']}`. "
        f"{len(answerable)} answerable queries and {len(unanswerable)} out-of-corpus queries from "
        "`tests/evaluation/retrieval_cases.py`. Reproduce with `python run.py evaluate-retrieval`.",
        "",
        "## 1. Ranking quality",
        "",
        "Table 1 gives, for each search mode, the share of answerable queries whose answering "
        f"passage ranked first, in the top 5 and in the top {DEPTH}, and the mean reciprocal rank.",
        "",
        "Table 1: Ranking quality by search mode",
        "",
        "| Mode | Hit at 1 | Hit at 5 | Hit at 10 | Mean reciprocal rank |",
        "| --- | --- | --- | --- | --- |",
    ]
    for mode in MODES:
        s = summaries[mode]
        lines.append(f"| {MODE_NAMES[mode]} | {_pct(s['hit@1'])} | {_pct(s['hit@5'])} | {_pct(s['hit@10'])} | {s['mrr@10']:.2f} |")
    lines += [
        "",
        "## 2. Rank of the answering passage per query",
        "",
        "Table 2 lists every answerable query with the rank at which each mode first returned a "
        "passage from the answer key.",
        "",
        "Table 2: First relevant rank per query",
        "",
        "| Case | Query | Keyword | Meaning | Hybrid | Hybrid top result |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        if row["kind"] != ANSWERABLE:
            continue
        lines.append(
            f"| {row['case']} | {row['query']} | {_rank_cell(row['bm25_rank'])} | "
            f"{_rank_cell(row['dense_rank'])} | {_rank_cell(row['hybrid_rank'])} | {row['top_hit']} |"
        )
    lines += [
        "",
        "## 3. Evidence sufficiency",
        "",
        "Table 3 shows the best cosine similarity each query reached against any passage, and "
        f"whether the configured threshold of {threshold:.2f} called the evidence sufficient.",
        "",
        "Table 3: Best similarity and sufficiency call",
        "",
        "| Case | Kind | Best cosine | Called sufficient |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(f"| {row['case']} | {row['kind']} | {float(row['best_cosine']):.3f} | {'yes' if row['flagged_sufficient'] else 'no'} |")
    separable = min(answerable_cos) > max(ooc_cos)
    lines += [
        "",
        f"Answerable queries reached between {min(answerable_cos):.3f} and {max(answerable_cos):.3f}. "
        f"Out-of-corpus queries reached between {min(ooc_cos):.3f} and {max(ooc_cos):.3f}. "
        + (
            f"The two ranges do not overlap, so any threshold between {max(ooc_cos):.3f} and "
            f"{min(answerable_cos):.3f} separates them on this set."
            if separable
            else "The two ranges overlap, so no single threshold separates every case; similarity "
            "alone cannot decide answerability and the model must still be allowed to say the "
            "evidence does not answer the question."
        ),
        "",
    ]
    (EVALUATION_DIR / "retrieval-evaluation.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {EVALUATION_DIR / 'retrieval-evaluation.md'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
