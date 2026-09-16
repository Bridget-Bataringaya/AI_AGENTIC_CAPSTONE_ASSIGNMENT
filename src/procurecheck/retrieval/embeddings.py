"""Meaning-based retrieval: text embeddings from the local Ollama server.

The model is nomic-embed-text (137M parameters, 768 dimensions), pulled into
the same Ollama install that serves Llama 3.1 8B, so no text leaves the machine
and no new service is added. It expects a task prefix: passages are embedded as
"search_document: ..." and questions as "search_query: ...". Leaving the
prefixes off measurably weakens it, so they are applied here and nowhere else.

Vectors are normalised to unit length when produced, which makes cosine
similarity a plain dot product at search time.
"""

from __future__ import annotations

import math
from typing import Callable, Final, List, Optional, Sequence

import httpx

DOCUMENT_PREFIX: Final[str] = "search_document: "
QUERY_PREFIX: Final[str] = "search_query: "
BATCH_SIZE: Final[int] = 32


class EmbeddingUnavailableError(RuntimeError):
    """Raised when the embedding model cannot be reached or is not installed."""


def normalise(vector: Sequence[float]) -> List[float]:
    length = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / length for v in vector]


def dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


class OllamaEmbedder:
    """Calls POST /api/embed. One instance per index build or search session."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 600.0,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.model = model
        self._endpoint = f"{base_url.rstrip('/')}/api/embed"
        self._client = client or httpx.Client(timeout=timeout_seconds)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "OllamaEmbedder":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _embed(self, inputs: List[str]) -> List[List[float]]:
        try:
            response = self._client.post(
                self._endpoint, json={"model": self.model, "input": inputs, "truncate": True}
            )
        except httpx.HTTPError as exc:
            raise EmbeddingUnavailableError(
                f"Cannot reach the embedding backend at {self._endpoint}. Start Ollama "
                f"with `ollama serve`. Underlying error: {exc}"
            ) from exc
        if response.status_code == 404:
            raise EmbeddingUnavailableError(
                f"Embedding model {self.model!r} is not installed. "
                f"Pull it with `ollama pull {self.model}`."
            )
        try:
            response.raise_for_status()
            vectors = response.json()["embeddings"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise EmbeddingUnavailableError(
                f"The embedding backend returned an unusable response: {exc}"
            ) from exc
        if len(vectors) != len(inputs):
            raise EmbeddingUnavailableError(
                f"Asked for {len(inputs)} embeddings, received {len(vectors)}."
            )
        return [normalise(v) for v in vectors]

    def embed_documents(
        self,
        texts: Sequence[str],
        on_batch: Optional[Callable[[int, int], None]] = None,
    ) -> List[List[float]]:
        vectors: List[List[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            batch = [DOCUMENT_PREFIX + t for t in texts[start : start + BATCH_SIZE]]
            vectors.extend(self._embed(batch))
            if on_batch is not None:
                on_batch(len(vectors), len(texts))
        return vectors

    def embed_query(self, text: str) -> List[float]:
        return self._embed([QUERY_PREFIX + text])[0]
