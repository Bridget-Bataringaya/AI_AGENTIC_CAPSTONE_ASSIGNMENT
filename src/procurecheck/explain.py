"""Plain-language explanations of each verdict.

A status on its own does not say what happened. On the first real run a team
reviewer received a report in which 21 of 22 items read "Not Found 0.00" and
nothing else, and asked the right question: what exactly happened, as opposed
to what had to happen? "Not Found" reads the same whether the model searched
every page and found nothing, or offered a passage that the evidence check then
showed to be a different document. The reviewer cannot tell which, and the
next step differs.

So every verdict carries five statements, built here and nowhere else so that
the PDF, the Word copy, the CSV, the JSON and the evaluation tables cannot
drift apart:

- required:  what the submission had to contain for the item to be Found
- happened:  what the system actually did, stage by stage
- evidence:  the page and quotation, or why there is none
- meaning:   what this status does and does not establish
- next_step: what the procurement officer does about it

Sentences are kept short and free of jargon, per the team's Document Format
Standard, because the reader is a procurement officer rather than an engineer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Optional

from .models import ItemStatus

QUOTE_LIMIT: Final[int] = 300

# Which path through the pipeline produced a verdict. Tests and the evaluation
# observations key off these, so they are fixed names rather than prose.
ROUTE_FOUND: Final[str] = "found"
ROUTE_LOW_CONFIDENCE: Final[str] = "low_confidence"
ROUTE_NOTHING_OFFERED: Final[str] = "nothing_offered"
ROUTE_REJECTED: Final[str] = "rejected_by_evidence_check"
ROUTE_DISPUTED: Final[str] = "disputed_by_evidence_check"
ROUTE_CHECK_FAILED: Final[str] = "evidence_check_failed"
ROUTE_UNGROUNDED: Final[str] = "quotation_not_in_submission"
ROUTE_UNANSWERED: Final[str] = "no_usable_answer"
ROUTE_UNSURE_ABSENT: Final[str] = "absent_but_unsure"

STATUS_MEANING: Final[dict] = {
    ItemStatus.FOUND: (
        "Text in the submission was accepted as this document. The quotation "
        "was confirmed to exist in the submission."
    ),
    ItemStatus.NOT_FOUND: (
        "No text in the submission was accepted as this document. This is not "
        "proof that the document is absent. It may be missing, or present under "
        "wording the model did not recognise."
    ),
    ItemStatus.REQUIRES_HUMAN_REVIEW: (
        "The system did not reach a decision. A person must record the item as "
        "Found or Not Found."
    ),
}


@dataclass(frozen=True)
class Explanation:
    route: str
    required: str
    happened: str
    evidence: str
    meaning: str
    next_step: str


def _flatten(text: object) -> str:
    return " ".join(str(text).split())


def _quote(text: Optional[str]) -> str:
    """Quote a passage so the sentence around it still ends in a full stop."""
    cleaned = _flatten(text or "")
    if len(cleaned) > QUOTE_LIMIT:
        cleaned = cleaned[: QUOTE_LIMIT - 3].rstrip() + "..."
    if not cleaned.endswith((".", "?", "!")):
        cleaned += "."
    return f'"{cleaned}"'


def _pages(pages_read: Optional[int]) -> str:
    if pages_read is None:
        return "the submission"
    if pages_read == 1:
        return "the single page of the submission"
    return f"all {pages_read} pages of the submission"


def _on_page(page: Optional[int]) -> str:
    return f" on page {page}" if page else ""


def route_of(clause: object) -> str:
    """Name the path through the pipeline that produced this verdict.

    Read defensively: a report restored from an older trace, or produced with
    the evidence check switched off, carries plain ClauseVerification items
    without the stage-by-stage fields, and still has to be explained.
    """
    status = clause.status
    if not getattr(clause, "model_answered", True):
        return ROUTE_UNANSWERED

    check = getattr(clause, "evidence_check", None)
    adjudication = getattr(clause, "adjudication", None)
    if check is None and adjudication is not None:
        # Older traces recorded the second pass without naming its outcome.
        if adjudication.accepts:
            check = "accepted"
        else:
            check = "disputed" if status is ItemStatus.REQUIRES_HUMAN_REVIEW else "rejected"

    if check == "rejected":
        return ROUTE_REJECTED
    if check == "disputed":
        return ROUTE_DISPUTED
    if check == "failed":
        return ROUTE_CHECK_FAILED
    if (
        getattr(clause, "first_pass_present", None)
        and getattr(clause, "quotation_grounded", None) is False
    ):
        return ROUTE_UNGROUNDED
    if status is ItemStatus.FOUND:
        return ROUTE_FOUND
    if status is ItemStatus.NOT_FOUND:
        return ROUTE_NOTHING_OFFERED
    return ROUTE_LOW_CONFIDENCE if clause.is_present else ROUTE_UNSURE_ABSENT


def _required(description: str, evidence_check: Optional[bool]) -> str:
    tail = (
        " It then had to pass the evidence check, which confirms the quoted "
        "passage is this document and not a related one."
        if evidence_check
        else ""
    )
    return (
        f'The submission had to contain this document: "{_flatten(description)}". '
        "To be reported Found, the model had to quote it from the submission. "
        "The quotation had to appear word for word in the submission text."
        + tail
    )


def _named(adjudication: object) -> str:
    return (
        f'It described the quoted passage as "{_flatten(adjudication.quoted_document)}" '
        f'and the requirement as "{_flatten(adjudication.required_document)}".'
    )


def _claimed(clause: object, pages: str) -> str:
    """The first sentence of every route in which the first pass claimed a match."""
    page = getattr(clause, "first_pass_page", None) or clause.page_number
    snippet = getattr(clause, "first_pass_snippet", None) or clause.extracted_snippet
    text = f"The model was given {pages} and reported the document as present{_on_page(page)}."
    if snippet:
        text += f" It quoted: {_quote(snippet)}"
    return text


def _happened(route: str, clause: object, pages_read: Optional[int], threshold: Optional[float]) -> str:
    pages = _pages(pages_read)
    confidence = clause.confidence_score
    adjudication = getattr(clause, "adjudication", None)

    if route == ROUTE_UNANSWERED:
        return (
            "The model did not return a usable answer for this item, even after a "
            "retry. No decision was made, so the item was passed to a person."
        )

    if route == ROUTE_NOTHING_OFFERED:
        text = (
            f"The model was given {pages} and asked to find this document. It reported that "
            "no passage is this document, and returned no page and no quotation. "
            f"Its match confidence was {confidence:.2f}."
        )
        if confidence == 0.0:
            text += " A value of 0.00 means it saw no likely match."
        return text + " With nothing quoted, there was no evidence for the later checks to verify."

    if route == ROUTE_UNGROUNDED:
        return (
            _claimed(clause, pages)
            + " That quotation does not appear anywhere in the submission text. A "
            "quotation that cannot be traced to the document is not accepted as "
            "evidence, so the item was passed to a person."
        )

    if route in (ROUTE_REJECTED, ROUTE_DISPUTED, ROUTE_CHECK_FAILED):
        text = _claimed(clause, pages) + (
            " The quotation was confirmed to appear in the submission. The evidence "
            "check then compared the quotation with the requirement, without the "
            "rest of the submission."
        )
        if route == ROUTE_CHECK_FAILED:
            return text + (
                " That check did not return a usable answer. The match could not be "
                "verified, so the item was passed to a person."
            )
        if adjudication is not None:
            text += " " + _named(adjudication)
        if route == ROUTE_REJECTED:
            return text + (
                " It judged them to be different documents and rejected the "
                "quotation. The item was therefore reported Not Found."
            )
        score = f" a {adjudication.match_confidence:.2f} match" if adjudication else " a close match"
        return text + (
            f" It judged them to be different documents, yet still rated the passage{score}. "
            "Its answer contradicted itself, so the item was passed to a person "
            "rather than reported Not Found."
        )

    if route == ROUTE_UNSURE_ABSENT:
        return (
            f"The model was given {pages} and reported no matching passage. It also "
            "marked its own answer as uncertain. The item was passed to a person "
            "rather than reported Not Found."
        )

    # Found, or found but not confidently enough.
    page = clause.page_number
    located = (
        f"on page {page}"
        if page
        else "in the submission. The file format has no page boundaries, so no page was given"
    )
    text = (
        f"The model was given {pages} and located the document {located}. "
        "The quotation was confirmed to appear in the submission."
    )
    if adjudication is not None:
        text += (
            " The evidence check then compared the quotation with the requirement. "
            + _named(adjudication)
            + " It judged them to be the same document."
        )
    if route == ROUTE_FOUND:
        if threshold is not None:
            text += f" Final confidence was {confidence:.2f}, at or above the {threshold:.2f} review threshold."
        return text

    if threshold is not None and confidence < threshold:
        return text + (
            f" Final confidence was {confidence:.2f}, below the {threshold:.2f} review "
            "threshold. A match that uncertain is not reported as Found, so the item "
            "was passed to a person."
        )
    return text + (
        f" Final confidence was {confidence:.2f}. The model itself marked the match "
        "as uncertain, so the item was passed to a person."
    )


def _evidence(route: str, clause: object) -> str:
    page = clause.page_number
    if route in (ROUTE_FOUND, ROUTE_LOW_CONFIDENCE, ROUTE_DISPUTED, ROUTE_CHECK_FAILED):
        where = f"Page {page}" if page else "No page number, as the file format has no pages"
        return f"{where}: {_quote(clause.extracted_snippet)}"
    if route == ROUTE_REJECTED:
        rejected_page = getattr(clause, "first_pass_page", None)
        rejected = getattr(clause, "first_pass_snippet", None)
        if rejected:
            where = f"was on page {rejected_page}" if rejected_page else "was"
            return f"None accepted. The rejected quotation {where}: {_quote(rejected)}"
        return "None accepted. The quotation the model offered was rejected by the evidence check."
    if route == ROUTE_UNGROUNDED:
        return "None verified. The quotation offered could not be found in the submission."
    return "None. No page number and no quotation were returned."


def _next_step(route: str, clause: object) -> str:
    page = clause.page_number
    if route == ROUTE_FOUND:
        if page:
            return f"Open page {page} and confirm the quoted passage is the required document."
        return "Find the quoted passage in the submission and confirm it is the required document."
    if route in (ROUTE_LOW_CONFIDENCE, ROUTE_DISPUTED, ROUTE_CHECK_FAILED):
        where = f"Read page {page}" if page else "Find the quoted passage"
        return (
            f"{where} and decide whether it is the required document. "
            "Record the item as Found or Not Found."
        )
    search = (
        "Search the submission by hand for this document. If it is there, record "
        "it as Found with its page number. If it is not, record it as missing."
    )
    if route == ROUTE_REJECTED:
        rejected_page = getattr(clause, "first_pass_page", None)
        if rejected_page:
            return f"Start with page {rejected_page}, where the rejected passage was. " + search
    return search


def explain(
    clause: object,
    description: Optional[str] = None,
    pages_read: Optional[int] = None,
    threshold: Optional[float] = None,
    evidence_check: Optional[bool] = None,
) -> Explanation:
    """Explain one verdict in terms a procurement officer can act on.

    `pages_read` falls back to what the engine recorded on the clause. It is
    passed explicitly when a report is rebuilt from an older trace that did not
    record it.
    """
    pages = pages_read if pages_read is not None else getattr(clause, "pages_read", None)
    route = route_of(clause)
    if evidence_check is None and getattr(clause, "adjudication", None) is not None:
        evidence_check = True
    return Explanation(
        route=route,
        required=_required(description or clause.clause_title, evidence_check),
        happened=_happened(route, clause, pages, threshold),
        evidence=_evidence(route, clause),
        meaning=STATUS_MEANING[clause.status],
        next_step=_next_step(route, clause),
    )


def compare(expected: ItemStatus, clause: object) -> str:
    """State how an actual verdict differs from the expected one, in words.

    Used by the evaluation reports. "Pass" and "Fail" say whether the two
    matched; this says what the difference would have cost a reviewer.
    """
    actual = clause.status
    route = route_of(clause)
    head = f"Expected {expected.value}. The system returned {actual.value}."
    if actual is expected:
        return head + " The outcome matched the expectation."

    if expected is ItemStatus.FOUND and actual is ItemStatus.NOT_FOUND:
        cause = (
            " The evidence check rejected a passage that should have been accepted."
            if route == ROUTE_REJECTED
            else " The model did not recognise the document in the text."
        )
        return head + (
            " A document that was in the submission was missed." + cause
            + " A reviewer relying on the report would have searched for it by hand."
        )
    if expected is ItemStatus.NOT_FOUND and actual is ItemStatus.FOUND:
        page = f" on page {clause.page_number}" if clause.page_number else ""
        return head + (
            f" A missing document was reported present{page}. This is the most "
            "serious error the system can make, because it hides a gap in the bid."
        )
    if actual is ItemStatus.REQUIRES_HUMAN_REVIEW:
        return head + (
            " No wrong answer was given, but a person had to decide an item the "
            "system was expected to settle."
        )
    return head + (
        f" An uncertain match was decided as {actual.value} without a person "
        "reviewing it."
    )
