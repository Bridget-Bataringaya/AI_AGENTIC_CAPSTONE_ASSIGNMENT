"""Retrieval over the controlled corpus: ingest, chunk, index, search.

Pipeline, one module per stage:

    corpus.py      manifest -> documents, with derived text for unreadable files
    segment.py     document -> ordered blocks carrying their heading and page
    chunking.py    blocks -> passages that never cross a heading
    lexical.py     BM25 keyword index
    embeddings.py  nomic-embed-text vectors through the local Ollama server
    index.py       build, save and load the combined index
    retriever.py   hybrid search fused by reciprocal rank, with a trace
    commands.py    the `index` and `search` commands
"""

from .chunking import Chunk
from .corpus import CorpusDocument, CorpusError, load_corpus
from .index import CorpusIndex, IndexNotFoundError
from .retriever import Hit, Retriever, SearchResult

__all__ = [
    "Chunk",
    "CorpusDocument",
    "CorpusError",
    "CorpusIndex",
    "Hit",
    "IndexNotFoundError",
    "Retriever",
    "SearchResult",
    "load_corpus",
]
