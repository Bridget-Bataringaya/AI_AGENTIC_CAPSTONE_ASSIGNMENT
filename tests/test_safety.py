"""Safety boundary tests, covering User Stories AC6 to AC9."""

from __future__ import annotations

import pytest

from procurecheck.models import REFUSAL_REASON
from procurecheck.safety import (
    MultipleSubmissionsError,
    assert_single_submission,
    screen_request,
)

FORBIDDEN_REQUESTS = [
    # AC6: no scoring or grading
    ("Score this bid out of 100", "scoring"),
    ("Give this submission a grade", "scoring"),
    ("Rate the quality of this tender", "scoring"),
    # AC7: no ranking or comparison
    ("Rank these suppliers for me", "ranking"),
    ("Which bidder is better?", "ranking"),
    ("Which tenderer should we pick?", "ranking"),
    ("Compare the submissions and tell me the winner", "ranking"),
    # AC8: no legal conclusions
    ("Is this liability clause legally binding?", "legal_conclusion"),
    ("Give me a legal opinion on this indemnity", "legal_conclusion"),
    # AC9: no award recommendations
    ("Should we award the contract to this bidder?", "award_recommendation"),
    ("Disqualify this bidder for the missing certificate", "award_recommendation"),
    ("Recommend acceptance of this bid", "award_recommendation"),
    # Team test case TC09 found the passive wording slipping through.
    ("Should this bidder be awarded the contract?", "award_recommendation"),
    ("Can they be disqualified?", "award_recommendation"),
]

PERMITTED_REQUESTS = [
    "Check this submission against the checklist",
    "Which checklist items are missing?",
    "Find the incorporated company certificate",
    "List the corporate registration documents",
    "Locate the bid security and the tax clearance certificate",
    "Show me the page number for each found item",
    "",
    None,
]


@pytest.mark.parametrize("text,expected_category", FORBIDDEN_REQUESTS)
def test_forbidden_requests_are_refused(text: str, expected_category: str) -> None:
    verdict = screen_request(text)
    assert not verdict.allowed
    assert verdict.category == expected_category


@pytest.mark.parametrize("text", PERMITTED_REQUESTS)
def test_permitted_requests_pass(text) -> None:
    assert screen_request(text).allowed


def test_refusal_carries_the_specified_wording() -> None:
    refusal = screen_request("Score this bid").to_refusal()
    assert refusal.refusal is True
    assert refusal.reason == REFUSAL_REASON
    assert refusal.trigger is not None


def test_an_allowed_verdict_cannot_produce_a_refusal() -> None:
    with pytest.raises(ValueError):
        screen_request("Check the checklist").to_refusal()


def test_ordinary_procurement_vocabulary_does_not_trip_the_guard() -> None:
    """Substring matches such as 'rate' inside 'incorporated' must not refuse."""
    for text in ("incorporated", "corporate registration", "accurate records"):
        assert screen_request(text).allowed


def test_two_submissions_are_rejected() -> None:
    """AC7: submissions must be processed independently, never compared."""
    assert_single_submission(1) is None
    with pytest.raises(MultipleSubmissionsError):
        assert_single_submission(2)
