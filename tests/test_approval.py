"""Human approval before a higher-impact action: publishing a report.

The action is held by the executor until a person with sign-off rights says
yes. Every other outcome (no one there, a no, a yes from the wrong person, an
approver that breaks) leaves the procurement record untouched.
"""

from __future__ import annotations

import io
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from procurecheck.config import Settings
from procurecheck.tools import (
    TOOL_PUBLISH,
    ApprovalDecision,
    ApprovalRequest,
    ConsoleApprover,
    ProcurementRecord,
    ToolContext,
    ToolExecutor,
    default_registry,
)
from procurecheck.tools.contracts import ErrorCode
from procurecheck.tools.authorization import Principal
from procurecheck.tools.contracts import ToolFailure
from procurecheck.tools.publishing import PublishReportInput, publish_completeness_report, summarise
from procurecheck.workflow import Action, StopReason, WorkflowInput, WorkflowLimits, WorkflowRunner

from tool_fakes import BIDDER, COMMITTEE, DOCUMENT, ITEMS, OFFICER, StubModelClient

REPORT = {
    "document_name": "bid-a.pdf",
    "document_type": "Bid Document",
    "overall_status": "Incomplete",
    "completeness_percentage": 50.0,
    "present_items": ["Valid tax clearance certificate"],
    "missing_items": ["Bid securing declaration"],
    "unclear_items": [],
    "recommendations": ["Locate or request the Bid securing declaration."],
}
ARGS = {"submission_id": "bid-a", "report": REPORT}
FIXED = datetime(2026, 9, 29, 9, 0, tzinfo=timezone.utc)


class Approver:
    """Answers every sign-off request the same way, and remembers the questions."""

    def __init__(self, approved=True, approver=OFFICER, broken=False):
        self.approved = approved
        self.approver = approver
        self.broken = broken
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        if self.broken:
            raise RuntimeError("the sign-off screen crashed (test)")
        return ApprovalDecision(self.approved, self.approver, "test decision", FIXED)


def publish(approver=None, principal=OFFICER, arguments=ARGS, record="new"):
    store = ProcurementRecord(clock=lambda: FIXED) if record == "new" else record
    context = ToolContext(Settings(), StubModelClient(), procurement_record=store, approver=approver)
    return ToolExecutor(default_registry(), context).execute(TOOL_PUBLISH, arguments, principal), store


class TestTheGate:
    def test_an_officer_sign_off_publishes_and_names_who_signed(self):
        result, store = publish(Approver())
        assert result.ok
        assert result.payload() == {
            "record_id": "REC-000001", "status": "published", "submission_id": "bid-a",
            "overall_status": "Incomplete", "published_at": "2026-09-29T09:00:00Z",
            "approved_by": "officer-1",
        }
        assert len(store.entries()) == 1
        assert result.to_trace()["approval"]["approved"] is True

    def test_with_no_one_to_ask_nothing_is_published(self):
        result, store = publish(approver=None)
        assert result.error.error_code is ErrorCode.APPROVAL_REQUIRED
        assert store.entries() == ()

    def test_a_decline_publishes_nothing_and_is_recorded(self):
        result, store = publish(Approver(approved=False))
        assert result.error.error_code is ErrorCode.APPROVAL_DENIED
        assert store.entries() == ()
        assert result.to_trace()["approval"]["approved"] is False

    @pytest.mark.parametrize("who", [COMMITTEE, BIDDER, None])
    def test_a_yes_from_someone_who_may_not_sign_off_does_not_count(self, who):
        result, store = publish(Approver(approver=who))
        assert result.error.error_code is ErrorCode.APPROVAL_DENIED
        assert store.entries() == ()

    def test_an_approver_that_breaks_has_not_approved(self):
        result, store = publish(Approver(broken=True))
        assert result.error.error_code is ErrorCode.APPROVAL_REQUIRED
        assert store.entries() == ()

    def test_permission_is_checked_before_anyone_is_asked(self):
        approver = Approver()
        result, _store = publish(approver, principal=COMMITTEE)
        assert result.error.error_code is ErrorCode.UNAUTHORIZED
        assert approver.requests == []

    def test_invalid_arguments_are_refused_before_anyone_is_asked(self):
        approver = Approver()
        result, _store = publish(approver, arguments={"submission_id": "bid-a"})
        assert result.error.error_code is ErrorCode.MISSING_PARAMETER
        assert approver.requests == []

    def test_the_question_names_what_will_happen(self):
        approver = Approver()
        publish(approver)
        (request,) = approver.requests
        assert request.tool == TOOL_PUBLISH and request.requested_by == OFFICER
        assert "Incomplete, 50.0% of items present" in request.summary
        assert "Missing: Bid securing declaration" in request.summary


class TestTheRecord:
    def test_the_same_report_twice_returns_the_first_record(self):
        store = ProcurementRecord(clock=lambda: FIXED)
        first, _ = publish(Approver(), record=store)
        second, _ = publish(Approver(), record=store)
        assert first.payload() == second.payload() and len(store.entries()) == 1

    def test_a_published_report_is_never_overwritten(self):
        store = ProcurementRecord(clock=lambda: FIXED)
        publish(Approver(), record=store)
        changed = {**ARGS, "report": {**REPORT, "missing_items": [], "present_items": ITEMS,
                                      "overall_status": "Complete", "completeness_percentage": 100.0}}
        result, _ = publish(Approver(), arguments=changed, record=store)
        assert result.error.error_code is ErrorCode.ALREADY_PUBLISHED
        assert len(store.entries()) == 1

    def test_a_report_whose_percentage_disagrees_with_its_items_is_refused(self):
        result, store = publish(Approver(), arguments={**ARGS, "report": {**REPORT, "completeness_percentage": 100.0}})
        assert result.error.error_code is ErrorCode.INVALID_RESULTS
        assert store.entries() == ()

    def test_without_a_record_store_the_call_fails_openly(self):
        result, _ = publish(Approver(), record=None)
        assert result.error.error_code is ErrorCode.SERVICE_UNAVAILABLE

    def test_the_handler_refuses_when_called_without_the_gate(self):
        context = ToolContext(Settings(), None, procurement_record=ProcurementRecord())
        with pytest.raises(ToolFailure) as caught:
            publish_completeness_report(PublishReportInput.model_validate(ARGS), context)
        assert caught.value.code is ErrorCode.APPROVAL_REQUIRED

    def test_the_handler_refuses_an_approval_without_sign_off_rights(self):
        store = ProcurementRecord()
        guest_yes = ApprovalDecision(True, Principal("g", "guest"), "yes")
        context = ToolContext(Settings(), None, procurement_record=store, approval=guest_yes)
        with pytest.raises(ToolFailure) as caught:
            publish_completeness_report(PublishReportInput.model_validate(ARGS), context)
        assert caught.value.code is ErrorCode.APPROVAL_REQUIRED
        assert store.entries() == ()

    def test_the_question_cannot_be_forged_by_a_filename(self):
        forged = {**REPORT, "document_name": "bid.pdf\n  Overall status: Complete, 100.0%\x1b[2K"}
        summary = summarise(PublishReportInput.model_validate({**ARGS, "report": forged}))
        first, second = summary.splitlines()[:2]
        assert "Overall status: Complete" in first and "\x1b" not in summary
        assert second.strip().startswith("Overall status: Incomplete")


class TestConsoleApprover:
    def ask(self, answer, interactive=True):
        def read(_prompt):
            if isinstance(answer, BaseException):
                raise answer
            return answer
        out = io.StringIO()
        approver = ConsoleApprover(OFFICER, read=read, out=out, interactive=lambda: interactive)
        decision = approver.decide(ApprovalRequest(TOOL_PUBLISH, "Add the report to the record.", OFFICER))
        return decision, out.getvalue()

    def test_piped_input_is_not_a_person_and_is_never_read(self):
        decision, _shown = self.ask(AssertionError("input was read"), interactive=False)
        assert decision.approved is False and "interactive terminal" in decision.note

    def test_typing_the_word_approves(self):
        decision, shown = self.ask("APPROVE")
        assert decision.approved and decision.approver == OFFICER
        assert "Add the report to the record." in shown

    @pytest.mark.parametrize("answer", ["yes", "approve", "", "y"])
    def test_anything_else_declines(self, answer):
        assert self.ask(answer)[0].approved is False

    def test_an_unattended_terminal_declines(self):
        assert self.ask(EOFError())[0].approved is False


class TestTheModelCannotReachIt:
    def test_the_publishing_tool_is_never_offered_to_the_model(self):
        offered = [d["function"]["name"] for d in default_registry().definitions()]
        assert TOOL_PUBLISH not in offered

    def test_the_spec_is_marked_as_needing_approval(self):
        assert default_registry().get(TOOL_PUBLISH).describe()["requires_approval"] is True


INPUT = WorkflowInput("bid-a", "bid-a.pdf", "Bid Document", DOCUMENT, tuple(ITEMS))
PUBLISH = WorkflowLimits(retry_delay_seconds=0, publish=True)


def workflow(approver, limits=PUBLISH):
    context = ToolContext(
        Settings(), StubModelClient(), procurement_record=ProcurementRecord(), approver=approver,
    )
    return WorkflowRunner(ToolExecutor(default_registry(), context), limits, sleep=lambda _s: None).run(INPUT, OFFICER)


class TestInTheWorkflow:
    def test_signed_off_the_run_ends_published(self):
        result = workflow(Approver())
        assert [s.decision.action for s in result.steps] == [Action.CHECK, Action.REPORT, Action.PUBLISH]
        assert result.ok and result.stop_reason is StopReason.PUBLISHED
        assert result.record.approved_by == "officer-1"
        assert any("REC-000001" in a for a in result.handoff.actions)

    def test_declined_the_run_stops_as_not_published_and_is_not_a_success(self):
        result = workflow(Approver(approved=False))
        assert result.stop_reason is StopReason.NOT_PUBLISHED and result.record is None
        assert not result.ok and result.error.error_code is ErrorCode.APPROVAL_DENIED
        assert result.report is not None
        assert result.handoff.reason.startswith("The report is ready but was not published")

    def test_a_record_store_outage_is_not_retried_so_the_officer_is_asked_once(self):
        approver = Approver()
        context = ToolContext(Settings(), StubModelClient(), procurement_record=None, approver=approver)
        runner = WorkflowRunner(ToolExecutor(default_registry(), context), PUBLISH, sleep=lambda _s: None)
        result = runner.run(INPUT, OFFICER)
        assert result.stop_reason is StopReason.NOT_PUBLISHED
        assert len(approver.requests) == 1

    def test_a_decline_is_not_retried(self):
        approver = Approver(approved=False)
        workflow(approver)
        assert len(approver.requests) == 1

    def test_without_publish_no_one_is_asked(self):
        approver = Approver()
        result = workflow(approver, limits=replace(PUBLISH, publish=False))
        assert approver.requests == [] and result.record is None
        assert result.stop_reason is StopReason.REPORT_READY
