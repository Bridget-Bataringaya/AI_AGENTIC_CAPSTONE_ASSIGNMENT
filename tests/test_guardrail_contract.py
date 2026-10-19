"""Unit tests against existing ProcureCheck guardrail modules."""
import pytest

from procurecheck.safety import screen_request, assert_single_submission, MultipleSubmissionsError
from procurecheck.workflow.limits import WorkflowLimits, APPROVED_TOOLS
from procurecheck.tools.authorization import (
    Principal,
    ROLE_BIDDER,
    ROLE_PROCUREMENT_OFFICER,
    PERMISSION_ANALYSE,
)


def test_award_recommendation_refused():
    assert not screen_request("Which bidder should be awarded the contract?").allowed


def test_completeness_request_allowed():
    assert screen_request("Identify the documents missing from this submission").allowed


def test_multiple_submissions_refused():
    with pytest.raises(MultipleSubmissionsError):
        assert_single_submission(2)


def test_bidder_lacks_analyse_permission():
    assert not Principal("bidder1", ROLE_BIDDER).may(PERMISSION_ANALYSE)


def test_officer_has_analyse_permission():
    assert Principal("officer1", ROLE_PROCUREMENT_OFFICER).may(PERMISSION_ANALYSE)


def test_iteration_limit_rejects_zero():
    with pytest.raises(ValueError):
        WorkflowLimits(max_iterations=0)


def test_workflow_does_not_publish_by_default():
    limits = WorkflowLimits()
    assert limits.publish is False
    assert limits.max_iterations == 7
    assert APPROVED_TOOLS == limits.approved_tools
