"""The `index` and `search` commands.

    python run.py index                      build knowledge/index/ from the corpus
    python run.py search "bid security"      top passages, with sources and a trace

A search writes its full trace to evidence/traces/retrieval/, named by time and
query, so any result shown in a report can be traced back to what was ranked.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Final

from ..checklists import REPO_ROOT
from ..config import Settings
from .corpus import CORPUS_DIR, CorpusError, load_corpus
from .embeddings import EmbeddingUnavailableError, OllamaEmbedder
from .index import CorpusIndex, IndexNotFoundError
from .retriever import (
    DEFAULT_TOP_K,
    MODE_HYBRID,
    MODES,
    Retriever,
    SearchResult,
    min_cosine_from_env,
)

DEFAULT_EMBEDDING_MODEL: Final[str] = "nomic-embed-text"
TRACE_DIR: Final[Path] = REPO_ROOT / "evidence" / "traces" / "retrieval"
PREVIEW_CHARS: Final[int] = 320

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_BACKEND_ERROR = 2


def index_dir() -> Path:
    """A relative PROCURECHECK_INDEX_DIR is taken from the repository root, not
    from wherever the command happened to be run."""
    raw = os.getenv("PROCURECHECK_INDEX_DIR", "").strip()
    if not raw:
        return REPO_ROOT / "knowledge" / "index"
    path = Path(raw)
    return path if path.is_absolute() else REPO_ROOT / path


def embedding_model() -> str:
    return os.getenv("PROCURECHECK_EMBEDDING_MODEL", "").strip() or DEFAULT_EMBEDDING_MODEL


def add_parsers(subparsers: argparse._SubParsersAction) -> None:
    build = subparsers.add_parser("index", help="Build the retrieval index over the corpus")
    build.add_argument("--doc", dest="doc_ids", action="append", help="Index only this document id (repeatable)")
    build.add_argument("--no-embeddings", action="store_true", help="Keyword index only; no model needed")
    build.add_argument("--corpus", type=Path, default=CORPUS_DIR)

    search = subparsers.add_parser("search", help="Search the corpus and show sources")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    search.add_argument("--mode", choices=MODES, default=MODE_HYBRID)
    search.add_argument("--doc", dest="doc_ids", action="append", help="Search only this document id (repeatable)")
    search.add_argument("--json", action="store_true", help="Print the trace as JSON")
    search.add_argument("--no-trace", action="store_true", help="Do not write a trace file")


def run_index(args: argparse.Namespace, settings: Settings) -> int:
    started = time.monotonic()
    try:
        documents = load_corpus(args.corpus, args.doc_ids)
    except CorpusError as exc:
        print(f"Corpus error: {exc}", file=sys.stderr)
        return EXIT_USER_ERROR

    def progress(message: str) -> None:
        print(f"[{time.monotonic() - started:6.0f}s] {message}", file=sys.stderr)

    embedder = None if args.no_embeddings else OllamaEmbedder(settings.base_url, embedding_model())
    cache = {}
    if embedder is not None:
        try:
            cache = CorpusIndex.load(index_dir()).embedding_cache(embedder.model)
        except (IndexNotFoundError, OSError, ValueError, KeyError, TypeError):
            cache = {}  # No usable previous index: embed everything.
    try:
        index = CorpusIndex.build(documents, embedder, progress, cache)
    except EmbeddingUnavailableError as exc:
        print(f"Embedding backend error: {exc}", file=sys.stderr)
        return EXIT_BACKEND_ERROR
    finally:
        if embedder is not None:
            embedder.close()

    destination = index_dir()
    index.save(destination)
    print(
        f"Indexed {index.meta['documents']} documents into {index.meta['chunks']} chunks "
        f"({'with' if index.has_vectors else 'without'} embeddings) in "
        f"{time.monotonic() - started:.0f}s. Saved to {destination}.",
        file=sys.stderr,
    )
    return EXIT_OK


def _trace_path(query: str) -> Path:
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:48] or "query"
    return TRACE_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{slug}.json"


def _print_result(result: SearchResult, stale: bool) -> None:
    print(f'Query: "{result.query}"  mode: {result.mode}')
    for note in result.notes:
        print(f"  note: {note}")
    if result.best_cosine is not None:
        verdict = "sufficient" if result.evidence_sufficient else "NOT sufficient"
        print(
            f"  best similarity {result.best_cosine:.3f} against threshold "
            f"{result.min_cosine:.2f}: evidence {verdict}"
        )
    for hit in result.hits:
        title = hit.chunk.doc_title
        signals = []
        if hit.bm25_rank is not None:
            signals.append(f"keyword #{hit.bm25_rank}")
        if hit.dense_rank is not None:
            signals.append(f"meaning #{hit.dense_rank} ({hit.cosine:.3f})")
        print(f"\n{hit.rank}. [{hit.chunk.chunk_id}] {title}")
        print(f"   {hit.chunk.location}  |  {', '.join(signals)}")
        if hit.chunk.extraction != "native":
            print(f"   text source: {hit.chunk.extraction} (see knowledge/corpus/DERIVATIONS.csv)")
        preview = hit.chunk.text.replace("\n", " ")
        print(f"   {preview[:PREVIEW_CHARS]}{'...' if len(preview) > PREVIEW_CHARS else ''}")
    if stale:
        print("\nWarning: the corpus changed after this index was built. Rebuild with `python run.py index`.")


def run_search(args: argparse.Namespace, settings: Settings) -> int:
    try:
        index = CorpusIndex.load(index_dir())
    except IndexNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_USER_ERROR

    try:
        indexed_ids = list(index.meta.get("per_document", {})) or None
        stale = index.is_stale(load_corpus(doc_ids=indexed_ids))
    except CorpusError:
        stale = True

    model = index.meta.get("embedding_model") or embedding_model()
    with OllamaEmbedder(settings.base_url, str(model)) as embedder:
        retriever = Retriever(index, embedder, min_cosine_from_env())
        try:
            result = retriever.search(args.query, args.top_k, args.mode, args.doc_ids)
        except ValueError as exc:
            print(f"Search error: {exc}", file=sys.stderr)
            return EXIT_USER_ERROR

    trace = {
        "searched_at": datetime.now().isoformat(timespec="seconds"),
        "index_built_at": index.meta.get("built_at"),
        "index_stale": stale,
        "embedding_model": model,
        "document_filter": args.doc_ids,
        **result.to_trace(),
    }
    if not args.no_trace:
        path = _trace_path(args.query)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Trace written to {path}", file=sys.stderr)

    if args.json:
        print(json.dumps(trace, indent=2, ensure_ascii=False))
    else:
        _print_result(result, stale)
    return EXIT_OK
