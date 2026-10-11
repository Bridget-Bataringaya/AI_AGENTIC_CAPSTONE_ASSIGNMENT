"""Keyword retrieval: Okapi BM25 over chunk index text.

Kept alongside meaning-based search because procurement requirements turn on
exact terms. "Debarred", "bid securing declaration" and "Form B-3" must match
as words; an embedding alone scores a tax clearance affidavit close to a
non-debarment affidavit because both are sworn legal boilerplate (Failure Case
2 in the team's failure analysis).

No stemming library: a three-rule plural fold (securities -> security,
guarantees -> guarantee, bids -> bid) covers what the corpus needs and keeps
every match explainable.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Final, List, Sequence, Tuple

K1: Final[float] = 1.5
B: Final[float] = 0.75

_TOKEN: Final[re.Pattern] = re.compile(r"[a-z0-9]+")
STOPWORDS: Final[frozenset] = frozenset(
    """a about above after all also an and any are as at be been before being by
    can could did do does each either for from had has have he her his how if in
    into is it its may might more most must no not of on or other our shall she
    should so such than that the their them then there these they this those to
    under upon was we were what when where which while who whom will with within
    would you your""".split()
)


def _fold(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if token.endswith("sses"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def tokenize(text: str) -> List[str]:
    return [_fold(t) for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS]


@dataclass
class BM25Index:
    """Inverted index. Postings map a term to (chunk position, term frequency)."""

    doc_lengths: List[int] = field(default_factory=list)
    postings: Dict[str, List[Tuple[int, int]]] = field(default_factory=dict)

    @classmethod
    def build(cls, texts: Sequence[str]) -> "BM25Index":
        index = cls()
        for position, text in enumerate(texts):
            counts = Counter(tokenize(text))
            index.doc_lengths.append(sum(counts.values()))
            for term, frequency in counts.items():
                index.postings.setdefault(term, []).append((position, frequency))
        return index

    @property
    def size(self) -> int:
        return len(self.doc_lengths)

    def score(self, query: str) -> Dict[int, float]:
        """BM25 score for every chunk sharing at least one query term."""
        if not self.doc_lengths:
            return {}
        average = sum(self.doc_lengths) / len(self.doc_lengths) or 1.0
        scores: Dict[int, float] = {}
        for term in set(tokenize(query)):
            postings = self.postings.get(term)
            if not postings:
                continue
            idf = math.log(1 + (self.size - len(postings) + 0.5) / (len(postings) + 0.5))
            for position, frequency in postings:
                norm = K1 * (1 - B + B * self.doc_lengths[position] / average)
                scores[position] = scores.get(position, 0.0) + idf * frequency * (K1 + 1) / (
                    frequency + norm
                )
        return scores

    def to_json(self) -> dict:
        return {"doc_lengths": self.doc_lengths, "postings": self.postings}

    @classmethod
    def from_json(cls, data: dict) -> "BM25Index":
        return cls(
            doc_lengths=list(data["doc_lengths"]),
            postings={t: [tuple(p) for p in ps] for t, ps in data["postings"].items()},
        )
