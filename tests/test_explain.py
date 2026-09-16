"""Tests for the explanation behind every verdict.

The reviewer's question on the first real report was what exactly happened,
as opposed to what had to happen. These tests drive real verdicts through the
engine with a stubbed model and assert that each route through the pipeline
is told apart in words. Two Not Found items reached by different routes must
never read the same.
"""

from __future__ import annotations

from procurecheck.explain import (
    ROUTE_CHECK_FAILED,
    ROUTE_DISPUTED,
    ROUTE_FOUND,
    ROUTE_LOW_CONFIDENCE,
    ROUTE_NOTHING_OFFERED,
    ROUTE_REJECTED,
    ROUTE_UNANSWERED,
    ROUTE_UNGROUNDED,
    compare,
    explain,
)
from procurecheck.llm import StructuredOutputError
from procurecheck.models import ClauseVerification, ItemStatus

from test_engine import ITEMS, SUBMISSION, accepting_adjudication, engine_for, make, run


def test_nothing_offered_says_the_model_searched_and_returned_nothing() -> None:
    result = run(make(is_present=False, page_number=None, extracted_snippet=None, confidence_score=0.0))
    story = explain(result, threshold=0.85)

    assert story.route == ROUTE_NOTHING_OFFERED
    assert "all 2 pages" in story.happened
    assert "no page and no quotation" in story.happened
    assert "0.00" in story.happened
    assert story.evidence.startswith("None.")
    assert "not proof that the document is absent" in story.meaning
    assert "Search the submission by hand" in story.next_step


def test_a_rejected_quotation_is_named_and_kept_for_the_reviewer() -> None:
    result = run(
        make(),
        adjudication=accepting_adjudication(
            required_document="tax clearance certificate",
            quoted_document="certificate of registration",
            same_document=False,
            both_required_separately=True,
            match_confidence=0.0,
        ),
    )
    story = explain(result)

    assert result.status is ItemStatus.NOT_FOUND
    assert story.route == ROUTE_REJECTED
    assert "certificate of registration" in story.happened
    assert "rejected the quotation" in story.happened
    assert "TCC/2026/00417" in story.evidence, "the rejected passage is where to look first"
    assert "page 2" in story.next_step


def test_two_not_found_routes_never_read_the_same() -> None:
    searched = explain(run(make(is_present=False, page_number=None, extracted_snippet=None, confidence_score=0.0)))
    rejected = explain(
        run(make(), adjudication=accepting_adjudication(same_document=False, match_confidence=0.0))
    )

    assert searched.happened != rejected.happened
    assert searched.evidence != rejected.evidence


def test_found_states_the_page_the_check_and_the_threshold() -> None:
    story = explain(run(make()), threshold=0.85)

    assert story.route == ROUTE_FOUND
    assert "page 2" in story.happened
    assert "same document" in story.happened
    assert "at or above the 0.85 review threshold" in story.happened
    assert story.evidence.startswith("Page 2:")


def test_low_confidence_says_why_a_person_must_decide() -> None:
    story = explain(run(make(), adjudication=accepting_adjudication(match_confidence=0.55)), threshold=0.85)

    assert story.route == ROUTE_LOW_CONFIDENCE
    assert "below the 0.85 review threshold" in story.happened


def test_a_quotation_missing_from_the_document_is_explained() -> None:
    result = run(make(extracted_snippet="A Bid Security of UGX 24,000,000.00 is attached."))
    story = explain(result)

    assert story.route == ROUTE_UNGROUNDED
    assert "does not appear anywhere in the submission" in story.happened


def test_a_disputed_and_a_failed_evidence_check_are_told_apart() -> None:
    disputed = explain(run(make(), adjudication=accepting_adjudication(same_document=False, match_confidence=0.8)))
    failed = explain(run(make(), adjudication_error=StructuredOutputError("no valid JSON")))

    assert disputed.route == ROUTE_DISPUTED
    assert "contradicted itself" in disputed.happened
    assert failed.route == ROUTE_CHECK_FAILED
    assert "did not return a usable answer" in failed.happened


def test_no_usable_answer_is_never_described_as_a_search() -> None:
    class Broken:
        def complete_structured(self, *args):
            raise StructuredOutputError("garbage")

    engine, _ = engine_for(make())
    engine._client = Broken()
    result = engine.analyse(ITEMS, SUBMISSION).report.verified_items[0]
    story = explain(result)

    assert story.route == ROUTE_UNANSWERED
    assert "did not return a usable answer" in story.happened


def test_a_plain_verdict_from_an_old_trace_is_still_explained() -> None:
    old = ClauseVerification(
        checklist_item_id="CHK-05",
        clause_title="Anti-bribery declaration",
        is_present=False,
        confidence_score=0.0,
        requires_human_review=False,
    )
    story = explain(old, pages_read=7)

    assert story.route == ROUTE_NOTHING_OFFERED
    assert "all 7 pages" in story.happened


def test_the_engine_records_every_stage_it_ran() -> None:
    result = run(make(), adjudication=accepting_adjudication(same_document=False, match_confidence=0.0))

    assert result.pages_read == 2
    assert result.first_pass_present is True
    assert result.first_pass_page == 2
    assert "TCC/2026/00417" in result.first_pass_snippet
    assert result.quotation_grounded is True
    assert result.evidence_check == "rejected"


def test_compare_names_the_cost_of_each_mismatch() -> None:
    found = run(make())
    missing = run(make(is_present=False, page_number=None, extracted_snippet=None, confidence_score=0.0))

    assert "matched the expectation" in compare(ItemStatus.FOUND, found)
    assert "most serious error" in compare(ItemStatus.NOT_FOUND, found)
    assert "was missed" in compare(ItemStatus.FOUND, missing)


def test_no_explanation_contains_an_em_or_en_dash() -> None:
    routes = [
        run(make()),
        run(make(is_present=False, page_number=None, extracted_snippet=None, confidence_score=0.0)),
        run(make(), adjudication=accepting_adjudication(same_document=False, match_confidence=0.0)),
    ]
    for result in routes:
        story = explain(result, threshold=0.85, evidence_check=True)
        for text in (story.required, story.happened, story.evidence, story.meaning, story.next_step):
            assert "\u2014" not in text and "\u2013" not in text
