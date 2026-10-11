"""Engine tests using a stubbed model, so they run without a GPU or a server.

These cover the deterministic corrections the engine applies on top of whatever
the model returns: the confidence threshold, snippet grounding, page-number
validity and the safety refusal path.

They also cover the second model pass, the evidence check, which is not a
deterministic correction: it is the model being asked a second, narrower
question. The stub answers each pass separately so that a test cannot pass while
the second one is never really made.
"""

from __future__ import annotations

from typing import List

import pytest

from procurecheck.config import Settings
from procurecheck.engine import MatchingEngine
from procurecheck.ingestion.submission import ParsedPage, ParsedSubmission
from procurecheck.models import (
    ChecklistItem,
    ClauseVerification,
    EvidenceAdjudication,
    ItemStatus,
)

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


def accepting_adjudication(**kwargs) -> EvidenceAdjudication:
    """An evidence check that confirms the first pass. The common case."""
    defaults = dict(
        required_document="tax clearance certificate",
        quoted_document="tax clearance certificate",
        same_document=True,
        both_required_separately=False,
        match_confidence=0.95,
    )
    defaults.update(kwargs)
    return EvidenceAdjudication(**defaults)


class StubClient:
    """Answers each pass with a scripted result instead of calling a model.

    Schema-aware, because the pipeline now makes two different calls. Handing
    the same object back for both would let a test pass while the second pass
    was never really exercised.
    """

    def __init__(
        self,
        verification: ClauseVerification,
        adjudication: EvidenceAdjudication | None = None,
        adjudication_error: Exception | None = None,
    ) -> None:
        self._verification = verification
        self._adjudication = adjudication or accepting_adjudication()
        self._adjudication_error = adjudication_error
        self.calls = 0
        self.adjudication_calls = 0
        self.adjudication_messages: List[str] = []

    def complete_structured(self, system_prompt, user_message, schema):
        if schema is EvidenceAdjudication:
            self.adjudication_calls += 1
            self.adjudication_messages.append(user_message)
            if self._adjudication_error is not None:
                raise self._adjudication_error
            return self._adjudication
        self.calls += 1
        return self._verification


def engine_for(
    verification: ClauseVerification,
    adjudication: EvidenceAdjudication | None = None,
    adjudication_error: Exception | None = None,
    **overrides,
) -> tuple[MatchingEngine, StubClient]:
    settings = Settings(**{**Settings().__dict__, **overrides})
    client = StubClient(verification, adjudication, adjudication_error)
    return MatchingEngine(client, settings), client


def run(verification: ClauseVerification, **overrides) -> ClauseVerification:
    engine, _ = engine_for(verification, **overrides)
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


# ---------------------------------------------------------------------------
# The evidence check: the second model pass.
#
# These cover the failure the baseline measured. The first pass quotes real
# text from the submission that belongs to a different document, so grounding
# passes it and its 0.95 confidence clears the review threshold. Only a second
# reading of the quotation catches it.
# ---------------------------------------------------------------------------


def test_the_evidence_check_sees_the_quotation_and_not_the_submission() -> None:
    """Withholding the document is the whole point. Assert it, do not assume it."""
    engine, client = engine_for(make())
    engine.analyse(ITEMS, SUBMISSION)

    assert client.adjudication_calls == 1
    message = client.adjudication_messages[0]
    assert "A Tax Clearance Certificate reference TCC/2026/00417" in message
    assert "Tender reference SYN/2026/001" not in message, (
        "the second pass was handed the submission, which restores the very "
        "pressure it exists to remove"
    )


def test_a_confidently_rejected_quotation_becomes_not_found() -> None:
    """EV-05 and EV-07: real text, wrong document."""
    result = run(
        make(),
        adjudication=accepting_adjudication(
            required_document="anti-bribery declaration",
            quoted_document="conflict of interest declaration",
            same_document=False,
            both_required_separately=True,
            match_confidence=0.0,
        ),
    )
    assert result.status is ItemStatus.NOT_FOUND
    assert result.is_present is False
    assert result.extracted_snippet is None
    assert result.page_number is None
    assert "conflict of interest declaration" in result.adjudication_note


def test_two_separate_filings_are_rejected_even_when_named_the_same() -> None:
    """Either signal alone is enough to refuse the evidence."""
    result = run(
        make(),
        adjudication=accepting_adjudication(
            same_document=True, both_required_separately=True, match_confidence=0.1
        ),
    )
    assert result.status is ItemStatus.NOT_FOUND


def test_a_rejection_that_still_scores_the_passage_highly_goes_to_a_human() -> None:
    """A second pass arguing with itself must not delete a filed document."""
    result = run(
        make(),
        adjudication=accepting_adjudication(same_document=False, match_confidence=0.8),
    )
    assert result.status is ItemStatus.REQUIRES_HUMAN_REVIEW
    assert result.extracted_snippet is not None, (
        "the reviewer needs the disputed quotation to settle it"
    )
    assert "disagree" in result.adjudication_note


def test_a_document_filed_under_another_name_survives_the_check() -> None:
    """The check must not punish house style. EV-01 to EV-04 depend on this."""
    result = run(
        make(),
        adjudication=accepting_adjudication(
            required_document="bid security",
            quoted_document="bid guarantee",
            same_document=True,
            both_required_separately=False,
            match_confidence=0.95,
        ),
    )
    assert result.status is ItemStatus.FOUND
    assert result.extracted_snippet is not None


def test_an_unsure_acceptance_drops_below_the_review_threshold() -> None:
    """The first pass returns 0.95 for everything, so on its own the threshold
    never fires. Taking the weaker of the two judgements is what gives it
    something to act on."""
    result = run(make(), adjudication=accepting_adjudication(match_confidence=0.55))
    assert result.status is ItemStatus.REQUIRES_HUMAN_REVIEW
    assert result.confidence_score == pytest.approx(0.55)


def test_an_absent_item_is_not_sent_to_the_evidence_check() -> None:
    """Nothing was claimed, so there is no evidence to doubt and no call to make."""
    engine, client = engine_for(
        make(is_present=False, page_number=None, extracted_snippet=None,
             confidence_score=0.0)
    )
    outcome = engine.analyse(ITEMS, SUBMISSION)
    assert outcome.report is not None
    assert outcome.report.verified_items[0].status is ItemStatus.NOT_FOUND
    assert client.adjudication_calls == 0


def test_a_failed_evidence_check_is_never_reported_as_a_verified_match() -> None:
    from procurecheck.llm import StructuredOutputError

    result = run(make(), adjudication_error=StructuredOutputError("no valid JSON"))
    assert result.status is ItemStatus.REQUIRES_HUMAN_REVIEW
    assert "could not be completed" in result.adjudication_note


def test_the_baseline_single_pass_remains_reproducible() -> None:
    """PROCURECHECK_ADJUDICATE=off must restore the measured v2.0 behaviour."""
    engine, client = engine_for(
        make(),
        adjudication=accepting_adjudication(same_document=False, match_confidence=0.0),
        adjudicate=False,
    )
    outcome = engine.analyse(ITEMS, SUBMISSION)
    assert outcome.report is not None
    assert outcome.report.verified_items[0].status is ItemStatus.FOUND
    assert client.adjudication_calls == 0
