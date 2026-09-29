"""The multi-step workflow: the planner's rules and the loop that runs them."""

from __future__ import annotations

from dataclasses import replace

import pytest

from procurecheck.config import Settings
from procurecheck.llm import ModelUnavailableError
from procurecheck.tools import (
    TOOL_CHECK,
    TOOL_PUBLISH,
    TOOL_REPORT,
    TOOL_TICKET,
    ReviewQueue,
    ToolContext,
    ToolExecutor,
    default_registry,
)
from procurecheck.tools.contracts import (
    CheckCompletenessOutput,
    ErrorCode,
    ItemPresence,
    ItemResult,
    ToolError,
)
from procurecheck.tools.tickets import REASON_MAX_CHARS
from procurecheck.workflow import (
    Action,
    StopReason,
    WorkflowInput,
    WorkflowLimits,
    WorkflowRunner,
    WorkflowState,
    decide,
)

from tool_fakes import (
    BIDDER,
    COMMITTEE,
    DOCUMENT,
    ITEMS,
    OFFICER,
    OutageClient,
    StubModelClient,
    UnclearClient,
)

INPUT = WorkflowInput("bid-a", "bid-a.pdf", "Bid Document", DOCUMENT, tuple(ITEMS))
NO_WAIT = WorkflowLimits(retry_delay_seconds=0)
NEW_QUEUE = object()


def run(client=None, principal=OFFICER, limits=NO_WAIT, queue=NEW_QUEUE, workflow_input=INPUT):
    review_queue = ReviewQueue() if queue is NEW_QUEUE else queue
    context = ToolContext(Settings(), client or StubModelClient(), review_queue=review_queue)
    runner = WorkflowRunner(ToolExecutor(default_registry(), context), limits, sleep=lambda _s: None)
    return runner.run(workflow_input, principal)


def actions(result):
    return [step.decision.action for step in result.steps]


class RecheckOutage(UnclearClient):
    """Leaves an item Unclear, then goes down for the re-check."""

    def complete_structured(self, system_prompt, user_message, schema):
        if self.bid_security_checks >= 1:
            raise ModelUnavailableError("Cannot reach the model backend (test).")
        return super().complete_structured(system_prompt, user_message, schema)


class TestHappyPath:
    def test_check_then_report_then_stop_with_a_handoff(self):
        result = run()
        assert result.ok and result.stop_reason is StopReason.REPORT_READY
        assert actions(result) == [Action.CHECK, Action.REPORT]
        body = result.report.report
        assert body.overall_status.value == "Incomplete" and body.completeness_percentage == 50.0
        assert result.handoff.to == "procurement_officer"
        assert "Locate or request: Bid securing declaration" in result.handoff.actions

    def test_the_report_is_a_step_of_the_plan_not_a_choice(self):
        # The Week 4 live run ended without a report because the model chose
        # not to call the report tool. Here it cannot be skipped.
        assert actions(run())[-1] is Action.REPORT

    def test_every_iteration_records_sense_plan_act_and_observe(self):
        trace = run().to_trace()
        first = trace["steps"][0]
        assert set(first) == {"iteration", "sense", "plan", "act", "observe"}
        assert first["sense"]["checked"] is False
        assert first["plan"]["action"] == "check" and first["observe"] == ["success"]
        assert trace["orchestration"] == "direct" and trace["stop_reason"] == "report_ready"
        assert trace["limits"]["approved_tools"] == sorted([TOOL_CHECK, TOOL_REPORT, TOOL_TICKET, TOOL_PUBLISH])

    def test_the_trace_abbreviates_the_document(self):
        long_input = replace(INPUT, document_text=DOCUMENT + " filler" * 100)
        arguments = run(workflow_input=long_input).to_trace()["steps"][0]["act"][0]["arguments"]
        assert arguments["document_text"].endswith("characters)")


class TestReplanOnUnclear:
    def test_an_item_settled_by_the_recheck_needs_no_ticket(self):
        result = run(UnclearClient(unclear_answers=1))
        assert actions(result) == [Action.CHECK, Action.RECHECK, Action.REPORT]
        assert result.tickets == ()
        assert result.report.report.unclear_items == []

    def test_an_item_still_unclear_after_the_recheck_gets_a_ticket(self):
        result = run(UnclearClient(unclear_answers=2))
        assert actions(result) == [Action.CHECK, Action.RECHECK, Action.OPEN_TICKETS, Action.REPORT]
        (ticket,) = result.tickets
        assert ticket.item_id == "REQ-02" and ticket.resolved is False
        assert result.report.report.overall_status.value == "Needs Review"
        assert f"Resolve review ticket {ticket.ticket_id} (REQ-02)" in result.handoff.actions

    def test_the_recheck_asks_only_about_the_unclear_items(self):
        recheck = run(UnclearClient(unclear_answers=2)).steps[1].results[0]
        assert recheck.arguments["required_items"] == ["Bid securing declaration"]

    def test_the_recheck_keeps_the_items_it_was_not_asked_about(self):
        result = run(UnclearClient(unclear_answers=1))
        statuses = {r.item: r.status.value for r in result.check.results}
        assert statuses == {
            "Valid tax clearance certificate": "Present",
            "Bid securing declaration": "Missing",
        }
        assert result.check.completeness_percentage == 50.0

    def test_with_rechecks_switched_off_unclear_items_go_straight_to_tickets(self):
        result = run(UnclearClient(unclear_answers=1), limits=replace(NO_WAIT, max_recheck_rounds=0))
        assert actions(result) == [Action.CHECK, Action.OPEN_TICKETS, Action.REPORT]

    def test_when_tickets_cannot_be_opened_the_run_carries_on_and_says_so(self):
        result = run(UnclearClient(unclear_answers=2), queue=None)
        assert result.ok and result.tickets == ()
        assert any("open_review_tickets failed" in note for note in result.notes)
        assert (
            "Flag for review by hand, no ticket could be opened: Bid securing declaration"
            in result.handoff.actions
        )


class TestRecovery:
    def test_an_outage_is_retried_and_the_run_recovers(self):
        result = run(OutageClient(outages=1))
        assert result.ok
        assert actions(result) == [Action.CHECK, Action.CHECK, Action.REPORT]
        assert result.steps[0].results[0].error.error_code is ErrorCode.SERVICE_UNAVAILABLE
        assert result.steps[1].decision.retry is True

    def test_the_retry_waits_first(self):
        waits = []
        context = ToolContext(Settings(), OutageClient(outages=1), review_queue=ReviewQueue())
        runner = WorkflowRunner(
            ToolExecutor(default_registry(), context),
            WorkflowLimits(retry_delay_seconds=2.5),
            sleep=waits.append,
        )
        runner.run(INPUT, OFFICER)
        assert waits == [2.5]

    def test_a_lasting_outage_stops_after_the_retry_budget(self):
        result = run(StubModelClient(unavailable=True))
        assert result.stop_reason is StopReason.SERVICE_UNAVAILABLE
        assert actions(result) == [Action.CHECK, Action.CHECK]
        assert result.error.error_code is ErrorCode.SERVICE_UNAVAILABLE
        assert result.report is None

    def test_a_failed_recheck_is_dropped_and_the_first_results_are_kept(self):
        result = run(RecheckOutage(unclear_answers=5))
        assert result.ok
        assert actions(result) == [
            Action.CHECK, Action.RECHECK, Action.RECHECK, Action.OPEN_TICKETS, Action.REPORT,
        ]
        assert any("recheck_unclear failed" in note for note in result.notes)
        assert len(result.tickets) == 1


class TestStops:
    def test_a_bidder_is_refused_at_the_first_step_and_nothing_is_retried(self):
        result = run(principal=BIDDER)
        assert result.stop_reason is StopReason.UNAUTHORIZED and len(result.steps) == 1
        assert result.error.error_code is ErrorCode.UNAUTHORIZED

    def test_a_committee_member_may_not_start_a_check(self):
        assert run(principal=COMMITTEE).stop_reason is StopReason.UNAUTHORIZED

    def test_an_anonymous_caller_is_refused(self):
        assert run(principal=None).stop_reason is StopReason.UNAUTHORIZED

    def test_the_iteration_limit_stops_the_run(self):
        result = run(limits=replace(NO_WAIT, max_iterations=1))
        assert result.stop_reason is StopReason.ITERATION_LIMIT
        assert result.error.error_code is ErrorCode.STEP_LIMIT_REACHED
        assert result.check is not None and result.report is None

    def test_a_tool_outside_the_approved_list_is_never_called(self):
        client = StubModelClient()
        result = run(client, limits=replace(NO_WAIT, approved_tools=frozenset({TOOL_REPORT})))
        assert result.stop_reason is StopReason.TOOL_NOT_APPROVED
        assert result.steps == () and client.calls == 0

    def test_an_empty_document_ends_the_run_as_a_tool_failure(self):
        result = run(workflow_input=replace(INPUT, document_text="   "))
        assert result.stop_reason is StopReason.TOOL_FAILED
        assert result.error.error_code is ErrorCode.EMPTY_DOCUMENT
        assert len(result.steps) == 1


class TestInput:
    def test_blank_and_repeated_checklist_lines_are_dropped(self):
        messy = replace(INPUT, required_items=(" Bid securing declaration ", "", "bid securing declaration", ITEMS[0]))
        assert messy.required_items == ("Bid securing declaration", ITEMS[0])
        assert messy.item_id("BID SECURING DECLARATION") == "REQ-01"

    def test_a_repeated_line_no_longer_breaks_the_report(self):
        result = run(workflow_input=replace(INPUT, required_items=(*ITEMS, ITEMS[1])))
        assert result.ok and len(result.check.results) == 2

    def test_a_fault_inside_the_loop_ends_as_a_tool_failure_with_a_handoff(self, monkeypatch):
        import procurecheck.workflow.runner as runner_module

        def broken(*_args):
            raise RuntimeError("bug (test)")

        monkeypatch.setattr(runner_module, "observe", broken)
        result = run()
        assert result.stop_reason is StopReason.TOOL_FAILED
        assert result.handoff.to == "procurement_officer"
        assert "bug (test)" not in result.to_trace()["stop_detail"]


class TestPlanner:
    def test_the_first_decision_is_to_check_every_item(self):
        decision = decide(WorkflowState(input=INPUT), NO_WAIT)
        assert decision.action is Action.CHECK
        (call,) = decision.calls
        assert call.tool == TOOL_CHECK and call.arguments["required_items"] == ITEMS

    def test_decide_is_pure(self):
        state = WorkflowState(input=INPUT)
        assert decide(state, NO_WAIT) == decide(state, NO_WAIT)

    def test_a_non_retryable_failure_of_the_report_stops(self):
        state = WorkflowState(
            input=INPUT, last_action=Action.REPORT,
            last_error=ToolError(error_code=ErrorCode.INVALID_RESULTS, message="bad"),
        )
        decision = decide(state, NO_WAIT)
        assert decision.action is Action.STOP and decision.stop_reason is StopReason.TOOL_FAILED

    def test_ticket_reasons_are_cut_to_the_tool_limit(self):
        check = CheckCompletenessOutput(document_type="Bid", completeness_percentage=0.0, results=[
            ItemResult(item=ITEMS[0], status=ItemPresence.MISSING, reason="none"),
            ItemResult(item=ITEMS[1], status=ItemPresence.UNCLEAR, reason="x" * 5000),
        ])
        decision = decide(WorkflowState(input=INPUT, check=check, recheck_rounds=1), NO_WAIT)
        assert decision.action is Action.OPEN_TICKETS
        (call,) = decision.calls
        assert call.tool == TOOL_TICKET and call.arguments["item_id"] == "REQ-02"
        assert len(call.arguments["reason"]) == REASON_MAX_CHARS


@pytest.mark.parametrize("field,value", [
    ("max_iterations", 0),
    ("max_service_retries", -1),
    ("max_recheck_rounds", -1),
    ("retry_delay_seconds", -1.0),
])
def test_limits_reject_impossible_values(field, value):
    with pytest.raises(ValueError):
        WorkflowLimits(**{field: value})
