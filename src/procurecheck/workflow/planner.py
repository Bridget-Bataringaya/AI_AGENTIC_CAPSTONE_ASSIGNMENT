"""The Plan/Decide step: given what is known, choose the next action.

`decide` is a pure function of the state and the limits. The model never plans
here: it only does the reading inside check_document_completeness. Deciding
what to do next is ordinary control flow, and control flow written in code is
reproducible, testable and cannot be talked out of a step. Last week's live
run showed why this matters: the model, left to choose, skipped the report.

The rules, in order:

1. After a failed step:
   - UNAUTHORIZED ends the run. Retrying cannot grant a permission.
   - SERVICE_UNAVAILABLE repeats the same step, up to max_service_retries.
   - Otherwise the plan changes (re-plan). A failed re-check or failed
     tickets are dropped and the run carries on with what it has; a failed
     check or report ends the run, because there is nothing to carry on with.
2. No check yet: check every item.
3. Items came back Unclear and re-check rounds remain: check those items again
   in a call of their own. Only those items can change; the rest are kept.
4. Items are still Unclear: open a review ticket for each.
5. No report yet: generate it.
6. Otherwise stop: the report is ready for the officer.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Optional, Sequence, Tuple

from ..tools.completeness import TOOL_CHECK, TOOL_REPORT
from ..tools.contracts import ErrorCode, ItemResult, ToolError
from ..tools.tickets import REASON_MAX_CHARS, TOOL_TICKET, SuggestedStatus
from .limits import StopReason, WorkflowLimits
from .state import Action, WorkflowState

TRUNCATION_MARK = "..."


@dataclass(frozen=True)
class PlannedCall:
    tool: str
    arguments: Dict[str, Any]


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    calls: Tuple[PlannedCall, ...] = ()
    stop_reason: Optional[StopReason] = None
    error: Optional[ToolError] = None
    retry: bool = False
    abandon: Optional[Action] = None

    def to_trace(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "retry": self.retry,
            "abandoned": None if self.abandon is None else self.abandon.value,
            "stop_reason": None if self.stop_reason is None else self.stop_reason.value,
        }


def _check_call(state: WorkflowState, items: Sequence[str]) -> PlannedCall:
    return PlannedCall(TOOL_CHECK, {
        "document_text": state.input.document_text,
        "document_type": state.input.document_type,
        "required_items": list(items),
    })


def _ticket_call(state: WorkflowState, result: ItemResult) -> PlannedCall:
    reason = result.reason.strip() or "The check could not decide whether this item is present."
    if len(reason) > REASON_MAX_CHARS:
        reason = reason[: REASON_MAX_CHARS - len(TRUNCATION_MARK)] + TRUNCATION_MARK
    return PlannedCall(TOOL_TICKET, {
        "submission_id": state.input.submission_id,
        "item_id": state.input.item_id(result.item),
        "reason": reason,
        "suggested_status": SuggestedStatus.AMBIGUOUS.value,
    })


def _report_call(state: WorkflowState) -> PlannedCall:
    assert state.check is not None
    return PlannedCall(TOOL_REPORT, {
        "document_name": state.input.document_name,
        "document_type": state.check.document_type,
        "completeness_percentage": state.check.completeness_percentage,
        "completeness_results": [r.model_dump(mode="json") for r in state.check.results],
    })


def _stop(reason: StopReason, why: str, error: Optional[ToolError] = None) -> Decision:
    return Decision(Action.STOP, why, stop_reason=reason, error=error)


def _after_failure(state: WorkflowState, limits: WorkflowLimits, error: ToolError) -> Decision:
    failed = state.last_action
    assert failed is not None
    code = error.error_code

    if code is ErrorCode.UNAUTHORIZED:
        return _stop(StopReason.UNAUTHORIZED, f"The caller may not {failed.value}; retrying cannot change that.", error)

    if code is ErrorCode.SERVICE_UNAVAILABLE and state.consecutive_retries < limits.max_service_retries:
        attempt = state.consecutive_retries + 1
        again = decide(replace(state, last_error=None), limits)
        return replace(
            again, retry=True,
            reason=f"{failed.value} failed with SERVICE_UNAVAILABLE; retry {attempt} of {limits.max_service_retries}.",
        )

    if failed in (Action.RECHECK, Action.OPEN_TICKETS):
        # Re-plan: this step was an improvement, not a necessity. Drop it and
        # carry on with what the run already has.
        rest = decide(replace(state, last_error=None, abandoned=state.abandoned | {failed}), limits)
        return replace(
            rest, abandon=failed,
            reason=f"{failed.value} failed with {code.value}, so it was dropped. {rest.reason}",
        )

    stop_reason = StopReason.SERVICE_UNAVAILABLE if code is ErrorCode.SERVICE_UNAVAILABLE else StopReason.TOOL_FAILED
    return _stop(stop_reason, f"{failed.value} failed with {code.value} and cannot be worked around.", error)


def decide(state: WorkflowState, limits: WorkflowLimits) -> Decision:
    if state.last_error is not None:
        return _after_failure(state, limits, state.last_error)

    if state.check is None:
        return Decision(
            Action.CHECK,
            f"No check has run. Check all {len(state.input.required_items)} checklist items.",
            (_check_call(state, state.input.required_items),),
        )

    unclear = state.unclear_items()
    if (
        unclear
        and state.recheck_rounds < limits.max_recheck_rounds
        and Action.RECHECK not in state.abandoned
    ):
        return Decision(
            Action.RECHECK,
            f"{len(unclear)} item(s) came back Unclear. Check them again in a call of their "
            f"own (round {state.recheck_rounds + 1} of {limits.max_recheck_rounds}).",
            (_check_call(state, [r.item for r in unclear]),),
        )

    if unclear and not state.tickets_opened and Action.OPEN_TICKETS not in state.abandoned:
        return Decision(
            Action.OPEN_TICKETS,
            f"{len(unclear)} item(s) are still Unclear. Open a review ticket for each so an officer decides them.",
            tuple(_ticket_call(state, r) for r in unclear),
        )

    if state.report is None:
        return Decision(Action.REPORT, "The check is settled. Generate the report.", (_report_call(state),))

    return _stop(StopReason.REPORT_READY, "The report is ready for the procurement officer.")
