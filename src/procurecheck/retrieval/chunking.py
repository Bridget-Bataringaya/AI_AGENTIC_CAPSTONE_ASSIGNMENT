"""Chunking: pack a document's blocks into retrievable passages.

Three rules, each answering a failure recorded in the team's Retrieval and
Grounding Failure Analysis (Isaac Mwesigwa, Week 3):

1. A chunk never crosses a heading. A clause title and its operative text stay
   in one passage instead of the title ending one chunk and the covenant
   starting the next (Failure Case 1, chunk boundary fragmentation).
2. Every chunk is indexed with its document title and heading path prepended
   (`index_text`), so a passage that opens mid-clause with "The undersigned
   further covenants..." still carries the words that say what it is about.
   The stored `text` stays verbatim so a quotation can be checked against it.
3. Chunks know their neighbours (`prev_id`, `next_id`), so a caller can widen
   a hit to the surrounding passages when one chunk is not enough.

Sizes are in words, not model tokens, because the index must not depend on
which model later reads it. 220 words is roughly 300 tokens: small enough that
one passage is about one thing, large enough to hold a whole ITB sub-clause.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Iterator, List, Optional, Sequence

from .corpus import CorpusDocument
from .segment import Block

TARGET_WORDS: Final[int] = 220
MAX_WORDS: Final[int] = 320
# When a chunk closes because it is full rather than at a heading, its last
# block is repeated at the start of the next if it is this short, so a sentence
# that introduces a list is not separated from the list.
OVERLAP_MAX_WORDS: Final[int] = 60
MIN_CHUNK_WORDS: Final[int] = 8

_SENTENCE_END: Final[re.Pattern] = re.compile(r"(?<=[.;:])\s+(?=[A-Z(\[])")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    ordinal: int
    text: str
    section_heading: Optional[str]
    page_start: Optional[int]
    page_end: Optional[int]
    extraction: str
    prev_id: Optional[str] = None
    next_id: Optional[str] = None

    @property
    def index_text(self) -> str:
        """What BM25 and the embedding model see: title, heading, then text."""
        header = " > ".join(p for p in (self.doc_title, self.section_heading) if p)
        return f"{header}\n{self.text}"

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def location(self) -> str:
        """Human-readable citation, e.g. 'DOC-009, p. 12, Section 1 > Bid Security'."""
        parts = [self.doc_id]
        if self.page_start is not None:
            same = self.page_end in (None, self.page_start)
            parts.append(f"p. {self.page_start}" if same else f"pp. {self.page_start}-{self.page_end}")
        if self.section_heading:
            parts.append(self.section_heading)
        return ", ".join(parts)


def _split_oversized(block: Block) -> Iterator[Block]:
    """Split a block longer than MAX_WORDS at sentence ends, packing to TARGET_WORDS."""
    if len(block.text.split()) <= MAX_WORDS:
        yield block
        return
    buffer: List[str] = []
    count = 0
    for sentence in _SENTENCE_END.split(block.text):
        words = sentence.split()
        # A single "sentence" longer than the limit (a table dump, OCR soup) is
        # cut by words; there is no better boundary to find.
        while len(words) > MAX_WORDS:
            if buffer:
                yield Block(" ".join(buffer), block.page, block.heading)
                buffer, count = [], 0
            yield Block(" ".join(words[:TARGET_WORDS]), block.page, block.heading)
            words = words[TARGET_WORDS:]
        if count + len(words) > TARGET_WORDS and buffer:
            yield Block(" ".join(buffer), block.page, block.heading)
            buffer, count = [], 0
        buffer.append(" ".join(words))
        count += len(words)
    if buffer:
        yield Block(" ".join(buffer), block.page, block.heading)


def _group(blocks: Sequence[Block]) -> Iterator[List[Block]]:
    current: List[Block] = []
    count = 0
    for block in (piece for b in blocks for piece in _split_oversized(b)):
        words = len(block.text.split())
        heading_changed = bool(current) and block.heading != current[-1].heading
        full = bool(current) and count + words > TARGET_WORDS
        if heading_changed or full:
            yield current
            carry = current[-1]
            carried = (
                full
                and not heading_changed
                and len(carry.text.split()) <= OVERLAP_MAX_WORDS
                and len(current) > 1
            )
            current, count = ([carry], len(carry.text.split())) if carried else ([], 0)
        current.append(block)
        count += words
    if current:
        yield current


def chunk_document(document: CorpusDocument, blocks: Sequence[Block]) -> List[Chunk]:
    """Chunks for one document, linked to their neighbours, ids stable per build.

    Ids are ordinal within the document (DOC-009-C0042), so rebuilding the index
    from the same files and the same parameters reproduces the same ids, which
    is what lets an evaluation or a trace refer to a chunk by name.
    """
    drafts: List[List[Block]] = [
        group for group in _group(blocks)
        if sum(len(b.text.split()) for b in group) >= MIN_CHUNK_WORDS
    ]
    ids = [f"{document.doc_id}-C{index:04d}" for index in range(1, len(drafts) + 1)]
    chunks: List[Chunk] = []
    for index, group in enumerate(drafts):
        pages = [b.page for b in group if b.page is not None]
        chunks.append(
            Chunk(
                chunk_id=ids[index],
                doc_id=document.doc_id,
                doc_title=document.title,
                ordinal=index + 1,
                text="\n".join(b.text for b in group),
                section_heading=group[-1].heading,
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
                extraction=document.extraction,
                prev_id=ids[index - 1] if index > 0 else None,
                next_id=ids[index + 1] if index + 1 < len(ids) else None,
            )
        )
    return chunks
