"""Engine tests using a stubbed model, so they run without a GPU or a server.

These cover the deterministic corrections the engine applies on top of whatever
the model returns: the confidence threshold, snippet grounding, page-number
validity and the safety refusal path.
"""

from __future__ import annotations

from typing import List

import pytest

from procurecheck.config import Settings
from procurecheck.engine import MatchingEngine
from procurecheck.ingestion.submission import ParsedPage, ParsedSubmission
from procurecheck.models import ChecklistItem, ClauseVerification, ItemStatus

SUBMISSION = ParsedSubmission(
    submission_id="SYN-TEST",
    pages=(
        ParsedPage(number=1, text="Tender reference SYN/2026/001 for civil works."),
        ParsedPage(
            number=2,
            text="A Tax Clearance Certificate reference TCC/2026/00417 is enclosed.",
        ),
    ),
)

ITEMS: List[ChecklistItem] = [
    ChecklistItem(id="CHK-01", description="Valid tax clearance certificate"),
]


class StubClient:
    """Returns a scripted ClauseVerification instead of calling a model."""

    def __init__(self, verification: ClauseVerification) -> None:
        self._verification = verification
        self.calls = 0

    def complete_structured(self, system_prompt, user_message, schema):
        self.calls += 1
        return self._verification


def run(verification: ClauseVerification, **overrides) -> ClauseVerification:
    settings = Settings(**{**Settings().__dict__, **overrides})
    engine = MatchingEngine(StubClient(verification), settings)
    outcome = engine.analyse(ITEMS, SUBMISSION)
    assert outcome.report is not None
    return outcome.report.verified_items[0]


def make(**kwargs) -> ClauseVerification:
    defaults = dict(
        checklist_item_id="CHK-01",
        clause_title="Tax Clearance Certificate",
        is_present=True,
        page_number=2,
        extracted_snippet="A Tax Clearance Certificate reference TCC/2026/00417 is enclosed.",
        confidence_score=0.95,
        requires_human_review=False,
    )
    defaults.update(kwargs)
    return ClauseVerification(**defaults)


def test_a_grounded_confident_match_is_found() -> None:
    result = run(make())
    assert result.status is ItemStatus.FOUND
    assert result.page_number == 2
    assert "TCC/2026/00417" in result.extracted_snippet


def test_low_confidence_is_routed_to_human_review() -> None:
    """AC10: a low-confidence match must not be reported as Found."""
    result = run(make(confidence_score=0.40))
    assert result.status is ItemStatus.REQUIRES_HUMAN_REVIEW


def test_a_fabricated_snippet_is_not_reported_as_found() -> None:
    """The quotation a reviewer would trust must exist in the source document."""
    result = run(make(extracted_snippet="A Bid Security of UGX 24,000,000.00 is attached."))
    assert result.status is ItemStatus.REQUIRES_HUMAN_REVIEW
    assert result.is_present is False


def test_an_invalid_page_number_is_discarded() -> None:
    result = run(make(page_number=99))
    assert result.page_number is None


def test_an_absent_item_is_reported_missing_without_review() -> None:
    result = run(
        make(
            is_present=False,
            page_number=None,
            extracted_snippet=None,
            confidence_score=0.05,
        )
    )
    assert result.status is ItemStatus.NOT_FOUND
    assert result.requires_human_review is False


def test_an_overlong_snippet_is_truncated() -> None:
    long_snippet = SUBMISSION.pages[1].text * 20
    result = run(make(extracted_snippet=long_snippet), snippet_max_chars=50)
    assert len(result.extracted_snippet) <= 53
    assert result.extracted_snippet.endswith("...")


def test_the_model_id_is_never_trusted_over_our_own() -> None:
    result = run(make(checklist_item_id="WRONG-99"))
    assert result.checklist_item_id == "CHK-01"


def test_a_forbidden_instruction_refuses_before_any_model_call() -> None:
    """AC6 to AC9: the guard must gate the engine, not just the report."""
    client = StubClient(make())
    engine = MatchingEngine(client, Settings())
    outcome = engine.analyse(ITEMS, SUBMISSION, instruction="Score this bid out of 100")
    assert outcome.refused
    assert outcome.report is None
    assert client.calls == 0


def test_an_empty_checklist_is_rejected() -> None:
    engine = MatchingEngine(StubClient(make()), Settings())
    with pytest.raises(ValueError):
        engine.analyse([], SUBMISSION)


def test_human_override_produces_a_new_report() -> None:
    """AC10: the user may override a review tag to Found or Missing."""
    settings = Settings()
    engine = MatchingEngine(StubClient(make(confidence_score=0.4)), settings)
    outcome = engine.analyse(ITEMS, SUBMISSION)
    assert outcome.report is not None
    original = outcome.report
    overridden = original.with_overridden_item("CHK-01", ItemStatus.FOUND)

    assert overridden.verified_items[0].status is ItemStatus.FOUND
    assert original.verified_items[0].status is ItemStatus.REQUIRES_HUMAN_REVIEW
    assert overridden.missing_items == []
