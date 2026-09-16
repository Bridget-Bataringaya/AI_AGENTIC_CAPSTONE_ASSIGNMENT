"""Retrieval: hybrid keyword and meaning search, fused by reciprocal rank.

Each query runs two searches over the same chunks. BM25 ranks by shared terms;
the embedding ranks by cosine similarity. The two score scales cannot be
compared, so they are combined by rank instead (Reciprocal Rank Fusion,
Cormack et al. 2009): a chunk scores 1 / (k + rank) in each list it appears
in, summed. A passage both searches agree on rises; one that only shares
boilerplate words, or only sounds similar, does not.

Every search returns a trace: the query, both ranked lists, the fused result
and the evidence-sufficiency call. That is the record a reviewer uses to see
why a passage was, or was not, put in front of the model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Final, List, Optional, Sequence

from .chunking import Chunk
from .embeddings import EmbeddingUnavailableError, OllamaEmbedder, dot
from .index import CorpusIndex

RRF_K: Final[int] = 60
DEFAULT_TOP_K: Final[int] = 5
CANDIDATE_POOL: Final[int] = 50

# Below this best cosine similarity the corpus is treated as holding no
# evidence for the query, so a caller can answer "not in the corpus" instead
# of passing the nearest unrelated passage to the model. Calibrated on the
# retrieval check in tests/evaluation/retrieval_cases.py; see
# docs/evaluation/retrieval-evaluation.md.
DEFAULT_MIN_COSINE: Final[float] = 0.60

MODE_HYBRID: Final[str] = "hybrid"
MODE_BM25: Final[str] = "bm25"
MODE_DENSE: Final[str] = "dense"
MODES: Final = (MODE_HYBRID, MODE_BM25, MODE_DENSE)


def min_cosine_from_env() -> float:
    raw = os.getenv("PROCURECHECK_RETRIEVAL_MIN_COSINE", "").strip()
    return float(raw) if raw else DEFAULT_MIN_COSINE


@dataclass(frozen=True)
class Hit:
    rank: int
    chunk: Chunk
    fused_score: float
    bm25_rank: Optional[int]
    bm25_score: Optional[float]
    dense_rank: Optional[int]
    cosine: Optional[float]

    def to_trace(self) -> Dict[str, object]:
        return {
            "rank": self.rank,
            "chunk_id": self.chunk.chunk_id,
            "location": self.chunk.location,
            "extraction": self.chunk.extraction,
            "fused_score": round(self.fused_score, 6),
            "bm25_rank": self.bm25_rank,
            "bm25_score": None if self.bm25_score is None else round(self.bm25_score, 4),
            "dense_rank": self.dense_rank,
            "cosine": None if self.cosine is None else round(self.cosine, 4),
            "text": self.chunk.text,
        }


@dataclass(frozen=True)
class SearchResult:
    query: str
    mode: str
    hits: List[Hit]
    best_cosine: Optional[float]
    min_cosine: float
    notes: List[str]

    @property
    def evidence_sufficient(self) -> Optional[bool]:
        """None when there is no cosine to judge by (keyword-only search)."""
        if self.best_cosine is None:
            return None if self.mode == MODE_BM25 else False
        return self.best_cosine >= self.min_cosine

    def to_trace(self) -> Dict[str, object]:
        return {
            "query": self.query,
            "mode": self.mode,
            "best_cosine": None if self.best_cosine is None else round(self.best_cosine, 4),
            "min_cosine": self.min_cosine,
            "evidence_sufficient": self.evidence_sufficient,
            "notes": self.notes,
            "hits": [hit.to_trace() for hit in self.hits],
        }


def _ranks(scores: Dict[int, float], limit: int) -> Dict[int, int]:
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return {position: rank for rank, (position, _score) in enumerate(ordered, start=1)}


class Retriever:
    def __init__(
        self,
        index: CorpusIndex,
        embedder: Optional[OllamaEmbedder] = None,
        min_cosine: float = DEFAULT_MIN_COSINE,
    ) -> None:
        self._index = index
        self._embedder = embedder
        self._min_cosine = min_cosine

    def neighbours(self, chunk: Chunk, width: int = 1) -> List[Chunk]:
        """The chunk with up to `width` passages either side, in document order."""
        before: List[Chunk] = []
        after: List[Chunk] = []
        cursor = chunk
        for _ in range(width):
            if not cursor.prev_id:
                break
            cursor = self._index.chunk(cursor.prev_id)
            before.insert(0, cursor)
        cursor = chunk
        for _ in range(width):
            if not cursor.next_id:
                break
            cursor = self._index.chunk(cursor.next_id)
            after.append(cursor)
        return [*before, chunk, *after]

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        mode: str = MODE_HYBRID,
        doc_ids: Optional[Sequence[str]] = None,
    ) -> SearchResult:
        if not query.strip():
            raise ValueError("query must not be empty")
        if mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}")

        chunks = self._index.chunks
        allowed = {d.upper() for d in doc_ids} if doc_ids else None
        eligible = [
            i for i, c in enumerate(chunks) if allowed is None or c.doc_id.upper() in allowed
        ]
        notes: List[str] = []

        bm25_scores: Dict[int, float] = {}
        if mode in (MODE_HYBRID, MODE_BM25):
            raw = self._index.bm25.score(query)
            bm25_scores = {i: raw[i] for i in eligible if i in raw}

        cosines: Dict[int, float] = {}
        if mode in (MODE_HYBRID, MODE_DENSE):
            if not self._index.has_vectors or self._embedder is None:
                notes.append("No embeddings available; meaning-based search was skipped.")
            else:
                try:
                    query_vector = self._embedder.embed_query(query)
                    vectors = self._index.vectors or []
                    cosines = {i: dot(query_vector, vectors[i]) for i in eligible}
                except EmbeddingUnavailableError as exc:
                    notes.append(f"Meaning-based search failed: {exc}")
            if not cosines:
                if mode == MODE_DENSE:
                    return SearchResult(query, mode, [], None, self._min_cosine, notes)
                mode = MODE_BM25
                notes.append("Fell back to keyword search only.")

        bm25_ranks = _ranks(bm25_scores, CANDIDATE_POOL)
        dense_ranks = _ranks(cosines, CANDIDATE_POOL)
        fused: Dict[int, float] = {}
        for ranks in (bm25_ranks, dense_ranks):
            for position, rank in ranks.items():
                fused[position] = fused.get(position, 0.0) + 1.0 / (RRF_K + rank)

        ordered = sorted(fused.items(), key=lambda item: (-item[1], item[0]))[:top_k]
        hits = [
            Hit(
                rank=rank,
                chunk=chunks[position],
                fused_score=score,
                bm25_rank=bm25_ranks.get(position),
                bm25_score=bm25_scores.get(position),
                dense_rank=dense_ranks.get(position),
                cosine=cosines.get(position),
            )
            for rank, (position, score) in enumerate(ordered, start=1)
        ]
        best = max(cosines.values()) if cosines else None
        return SearchResult(query, mode, hits, best, self._min_cosine, notes)
