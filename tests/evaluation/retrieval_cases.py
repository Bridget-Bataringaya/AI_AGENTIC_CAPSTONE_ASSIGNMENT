"""Labelled queries for checking retrieval quality on the controlled corpus.

These test the retriever alone, before any model reads what it returns: does
the passage that answers the question come back, and how high? They are not the
team's RAG test questions (ClickUp 123tcvwe2yf), which test the full answer.

A returned chunk counts as relevant when it comes from one of `documents`
(any document if empty) and its text matches every pattern in `must_match`.
The answer key was written by reading the corpus, and each pattern was
confirmed to exist in it, before any search was run.

Out-of-corpus queries have no relevant chunk. They are there to measure how
similar the nearest unrelated passage looks, which is what sets the
evidence-sufficiency threshold in retriever.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Tuple

ANSWERABLE: Final[str] = "answerable"
OUT_OF_CORPUS: Final[str] = "out-of-corpus"


@dataclass(frozen=True)
class RetrievalCase:
    case_id: str
    query: str
    kind: str
    documents: Tuple[str, ...] = ()
    must_match: Tuple[str, ...] = ()
    why: str = ""


CASES: Final[Tuple[RetrievalCase, ...]] = (
    RetrievalCase(
        "RC-01",
        "What form of bid security is required for open domestic bidding for supplies and works?",
        ANSWERABLE,
        ("DOC-025",),
        (r"bid insurance bond",),
        "One passage in the whole corpus, and it is OCR text from a scanned guideline.",
    ),
    RetrievalCase(
        "RC-02",
        "Which steps can be skipped when an entity uses micro procurement?",
        ANSWERABLE,
        ("DOC-030",),
        (r"micro procurement process shall not require",),
        "Paraphrased: the regulation says 'shall not require', the query says 'skipped'.",
    ),
    RetrievalCase(
        "RC-03",
        "How does the guideline define aggregated requirements?",
        ANSWERABLE,
        ("DOC-027",),
        (r"aggregated requirements.{0,3} means",),
        "A definition inside an OCR'd interpretation clause.",
    ),
    RetrievalCase(
        "RC-04",
        "What does a bidder use to log in to the electronic government procurement system?",
        ANSWERABLE,
        ("DOC-026",),
        (r"user identification",),
        "Vocabulary gap: 'log in' against 'authenticated ... User Identification'.",
    ),
    RetrievalCase(
        "RC-05",
        "Which procurements are set aside for registered groups of women, youth and persons with disabilities?",
        ANSWERABLE,
        ("DOC-017",),
        (r"reserved for (women|registered)",),
        "Only one standard document covers reserved procurement; 'set aside' is not its wording.",
    ),
    RetrievalCase(
        "RC-06",
        "Which documents prove a bidder is eligible, such as a tax clearance certificate and trading licence?",
        ANSWERABLE,
        (),
        (r"tax clearance", r"trading licen[cs]e"),
        "Common to many standard documents: tests that the right clause ranks, not the right file.",
    ),
    RetrievalCase(
        "RC-07",
        "For how long can a provider be suspended after failing a performance securing declaration?",
        ANSWERABLE,
        (),
        (r"period of three years",),
        "The answer is a number inside a form, not a clause heading.",
    ),
    RetrievalCase(
        "RC-08",
        "Which documents were deliberately left out of synthetic submission B?",
        ANSWERABLE,
        ("DOC-032",),
        (r"intentionally omitted",),
        "Synthetic bid; 'deliberately left out' against 'Intentionally Omitted'.",
    ),
    RetrievalCase(
        "RC-09",
        "Who signed the bid form for Nile Office Solutions?",
        ANSWERABLE,
        ("DOC-031",),
        (r"sarah namusoke",),
        "A proper name: keyword search should carry it.",
    ),
    RetrievalCase(
        "RC-10",
        "How must a power of attorney signed outside Uganda be authenticated?",
        ANSWERABLE,
        (),
        (r"notari[sz]ed",),
        "The answer word ('notarised') is not in the query.",
    ),
    RetrievalCase(
        "RC-11",
        "What planning records must a procuring and disposing entity keep on file?",
        ANSWERABLE,
        ("DOC-028",),
        (r"consolidated procurement plan",),
        "A short list in a four-page guideline, easily outranked by long standard documents.",
    ),
    RetrievalCase(
        "RC-12",
        "What is the standard notice format announcing the best evaluated bidder for consultancy services?",
        ANSWERABLE,
        ("DOC-029",),
        (r"notice of best evaluated bidder", r"consultancy"),
        "The phrase appears in 24 documents; only the notice-format guideline holds the format.",
    ),
    RetrievalCase(
        "RC-13",
        "Can the entity ask bidders to extend how long their bids remain valid?",
        ANSWERABLE,
        (),
        (r"extend the period of validity",),
        "Paraphrase of the bid validity clause.",
    ),
    RetrievalCase(
        "RC-14",
        "When are bidders treated as having a conflict of interest, for example sharing controlling shareholders?",
        ANSWERABLE,
        (),
        (r"controlling shareholders in common",),
        "A sub-item in a list; tests that list items stay attached to their clause.",
    ),
    RetrievalCase(
        "RC-15",
        "When does a bid securing declaration stop being valid?",
        ANSWERABLE,
        (),
        (r"cease to be valid",),
        "'Stop being valid' against 'cease to be valid'.",
    ),
    RetrievalCase("OC-01", "What is the VAT rate on imported cars in Kenya?", OUT_OF_CORPUS),
    RetrievalCase("OC-02", "Who won the 2022 FIFA World Cup final?", OUT_OF_CORPUS),
    RetrievalCase("OC-03", "What is the recommended dose of paracetamol for a child?", OUT_OF_CORPUS),
    RetrievalCase("OC-04", "How do I reset a forgotten Gmail password?", OUT_OF_CORPUS),
    RetrievalCase(
        "OC-05",
        "What thresholds does Tanzania's PPRA set for consultancy procurement?",
        OUT_OF_CORPUS,
        why="Near-domain: procurement vocabulary, but no Tanzanian rules are in the corpus.",
    ),
)
