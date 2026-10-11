"""Indexing: build the corpus index once, save it, load it for every search.

On disk (knowledge/index/, not committed because it is rebuilt from the corpus):

    meta.json      what was indexed, with which parameters, and when
    chunks.jsonl   one chunk per line, verbatim text plus provenance
    bm25.json      the keyword index
    vectors.f32    unit-length embeddings, float32, in chunk order

meta.json records a fingerprint of every source file. A search against an
index whose fingerprint no longer matches the corpus is told so, because an
index that silently lags the corpus reports documents missing that exist.
"""

from __future__ import annotations

import hashlib
import json
from array import array
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Final, List, Optional, Sequence

from . import chunking
from .chunking import Chunk, chunk_document
from .corpus import CorpusDocument
from .embeddings import OllamaEmbedder
from .lexical import BM25Index
from .segment import segment

META_FILE: Final[str] = "meta.json"
CHUNKS_FILE: Final[str] = "chunks.jsonl"
BM25_FILE: Final[str] = "bm25.json"
VECTORS_FILE: Final[str] = "vectors.f32"
INDEX_FORMAT_VERSION: Final[int] = 1

ProgressFn = Callable[[str], None]


class IndexNotFoundError(FileNotFoundError):
    """Raised when a search is attempted before `procurecheck index` has run."""


def _hash_path(path: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path.rglob("*")) if path.is_dir() else [path]
    for file in files:
        if file.is_file():
            digest.update(file.name.encode("utf-8"))
            digest.update(file.read_bytes())
    return digest.hexdigest()


def fingerprint(documents: Sequence[CorpusDocument]) -> Dict[str, str]:
    return {d.doc_id: _hash_path(d.text_source) for d in documents}


def text_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class CorpusIndex:
    chunks: List[Chunk]
    bm25: BM25Index
    vectors: Optional[List[List[float]]]
    meta: Dict[str, object] = field(default_factory=dict)
    _positions: Dict[str, int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._positions = {c.chunk_id: i for i, c in enumerate(self.chunks)}

    @property
    def has_vectors(self) -> bool:
        return bool(self.vectors) and len(self.vectors) == len(self.chunks)

    def chunk(self, chunk_id: str) -> Chunk:
        return self.chunks[self._positions[chunk_id]]

    def is_stale(self, documents: Sequence[CorpusDocument]) -> bool:
        return self.meta.get("fingerprint") != fingerprint(documents)

    def embedding_cache(self, model: str) -> Dict[str, List[float]]:
        """Vectors keyed by the exact text embedded, reusable by a rebuild.

        Embedding is the slow step (about one chunk per second on the CPU-only
        development machine), and most of a rebuild re-embeds text that has not
        changed. A vector is reused only for identical text and the same model.
        """
        if not self.has_vectors or self.meta.get("embedding_model") != model:
            return {}
        return {text_key(c.index_text): v for c, v in zip(self.chunks, self.vectors or [])}

    # Build ---------------------------------------------------------------

    @classmethod
    def build(
        cls,
        documents: Sequence[CorpusDocument],
        embedder: Optional[OllamaEmbedder],
        progress: ProgressFn = lambda _msg: None,
        cache: Optional[Dict[str, List[float]]] = None,
    ) -> "CorpusIndex":
        chunks: List[Chunk] = []
        per_document: Dict[str, Dict[str, object]] = {}
        for document in documents:
            blocks = segment(document)
            document_chunks = chunk_document(document, blocks)
            chunks.extend(document_chunks)
            per_document[document.doc_id] = {
                "title": document.title,
                "extraction": document.extraction,
                "blocks": len(blocks),
                "chunks": len(document_chunks),
                "chunks_with_page": sum(1 for c in document_chunks if c.page_start is not None),
            }
            progress(f"{document.doc_id} {len(document_chunks)} chunks ({document.extraction})")

        texts = [c.index_text for c in chunks]
        bm25 = BM25Index.build(texts)
        vectors = None
        reused = 0
        if embedder is not None:
            known = dict(cache or {})
            missing = [t for t in dict.fromkeys(texts) if text_key(t) not in known]
            reused = len(texts) - sum(1 for t in texts if text_key(t) not in known)
            progress(f"reusing {reused} cached embeddings, embedding {len(missing)} new texts")
            fresh = embedder.embed_documents(
                missing, on_batch=lambda done, total: progress(f"embedded {done}/{total}")
            )
            known.update({text_key(t): v for t, v in zip(missing, fresh)})
            vectors = [known[text_key(t)] for t in texts]

        meta: Dict[str, object] = {
            "format_version": INDEX_FORMAT_VERSION,
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "documents": len(documents),
            "chunks": len(chunks),
            "embedding_model": embedder.model if embedder else None,
            "embedding_dimensions": len(vectors[0]) if vectors else 0,
            "embeddings_reused": reused,
            "chunking": {
                "target_words": chunking.TARGET_WORDS,
                "max_words": chunking.MAX_WORDS,
                "overlap_max_words": chunking.OVERLAP_MAX_WORDS,
                "min_chunk_words": chunking.MIN_CHUNK_WORDS,
            },
            "per_document": per_document,
            "fingerprint": fingerprint(documents),
        }
        return cls(chunks=chunks, bm25=bm25, vectors=vectors, meta=meta)

    # Persist -------------------------------------------------------------

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / META_FILE).write_text(json.dumps(self.meta, indent=2), encoding="utf-8")
        with (directory / CHUNKS_FILE).open("w", encoding="utf-8") as handle:
            for chunk in self.chunks:
                handle.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")
        (directory / BM25_FILE).write_text(json.dumps(self.bm25.to_json()), encoding="utf-8")
        vectors_path = directory / VECTORS_FILE
        if self.has_vectors:
            flat = array("f")
            for vector in self.vectors or []:
                flat.extend(vector)
            with vectors_path.open("wb") as handle:
                flat.tofile(handle)
        elif vectors_path.exists():
            vectors_path.unlink()

    @classmethod
    def load(cls, directory: Path) -> "CorpusIndex":
        meta_path = directory / META_FILE
        if not meta_path.is_file():
            raise IndexNotFoundError(
                f"No index at {directory}. Build it first with `python run.py index`."
            )
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        with (directory / CHUNKS_FILE).open(encoding="utf-8") as handle:
            chunks = [Chunk(**json.loads(line)) for line in handle if line.strip()]
        bm25 = BM25Index.from_json(json.loads((directory / BM25_FILE).read_text(encoding="utf-8")))

        vectors = None
        dimensions = int(meta.get("embedding_dimensions") or 0)
        vectors_path = directory / VECTORS_FILE
        if dimensions and vectors_path.is_file():
            flat = array("f")
            with vectors_path.open("rb") as handle:
                flat.frombytes(handle.read())
            vectors = [
                flat[i : i + dimensions].tolist() for i in range(0, len(flat), dimensions)
            ]
        return cls(chunks=chunks, bm25=bm25, vectors=vectors, meta=meta)
