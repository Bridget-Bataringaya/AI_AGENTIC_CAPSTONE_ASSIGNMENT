"""The workflow loop, by direct orchestration.

One iteration is one pass through the loop:

    Sense    summarise the state            WorkflowState.sense
    Plan     choose the next action         planner.decide
    Act      run its tool calls             ToolExecutor.execute
    Observe  fold the results into state    state.observe
    Stop or re-plan                         decide again, from the new state

Every tool call still goes through the ToolExecutor, so the Week 4 checks
(the tool exists, the caller is permitted, the arguments and the answer match
their schemas) apply to the workflow exactly as they apply to the model.
On top of those, the runner enforces two bounds of its own: a call to a tool
outside the approved list is never made, and the run stops after
max_iterations acting iterations whatever the plan says.

Every run ends in a hand-off to a person. A finished report is advisory: the
officer confirms it, resolves the tickets and chases the missing items.

Case history (Week 6) sits outside the loop. The earlier check is recalled
before the loop starts and set beside the new one only after the loop has
ended, so nothing remembered can reach the planner, a prompt or a status.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..memory.recall import CaseMemory, MemoryReport, Recall
from ..tools.authorization import Principal
from ..tools.contracts import CheckCompletenessOutput, ErrorCode, GenerateReportOutput, ToolError
from ..tools.publishing import PublishReportOutput
from ..tools.registry import ToolExecutor, ToolResult
from ..tools.tickets import CreateTicketOutput
from .limits import StopReason, WorkflowLimits
from .planner import Decision, decide
from .state import Action, WorkflowInput, WorkflowState, observe

logger = logging.getLogger(__name__)

HANDOFF_ROLE = "procurement_officer"

# How a stop that is not a finished report reads to a client that only looks
# at the error envelope. The trace always carries the full stop reason.
STOP_ERROR_CODE: Dict[StopReason, ErrorCode] = {
    StopReason.ITERATION_LIMIT: ErrorCode.STEP_LIMIT_REACHED,
    StopReason.TOOL_NOT_APPROVED: ErrorCode.REFUSED,
}


@dataclass(frozen=True)
class StepRecord:
    iteration: int
    sensed: Dict[str, Any]
    decision: Decision
    results: Tuple[ToolResult, ...]

    def to_trace(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "sense": self.sensed,
            "plan": self.decision.to_trace(),
            "act": [r.to_trace() for r in self.results],
            "observe": [
                "success" if r.ok else f"error {r.error.error_code.value}" for r in self.results
            ],
        }


@dataclass(frozen=True)
class Handoff:
    """Who takes the case next, why, and what they need to do."""

    to: str
    reason: str
    actions: Tuple[str, ...]

    def to_trace(self) -> Dict[str, Any]:
        return {"to": self.to, "reason": self.reason, "actions": list(self.actions)}


@dataclass(frozen=True)
class WorkflowRun:
    stop_reason: StopReason
    stop_detail: str
    handoff: Handoff
    steps: Tuple[StepRecord, ...]
    limits: WorkflowLimits
    principal: Optional[Principal]
    check: Optional[CheckCompletenessOutput] = None
    report: Optional[GenerateReportOutput] = None
    record: Optional[PublishReportOutput] = None
    tickets: Tuple[CreateTicketOutput, ...] = ()
    notes: Tuple[str, ...] = ()
    error: Optional[ToolError] = None
    memory: Optional[MemoryReport] = None

    @property
    def ok(self) -> bool:
        return self.stop_reason in (StopReason.REPORT_READY, StopReason.PUBLISHED)

    @property
    def iterations(self) -> int:
        return len(self.steps)

    def to_trace(self) -> Dict[str, Any]:
        return {
            "principal": None if self.principal is None else {
                "user_id": self.principal.user_id, "role": self.principal.role,
            },
            "orchestration": "direct",
            "limits": self.limits.to_trace(),
            "iterations": self.iterations,
            "status": "success" if self.ok else "error",
            "stop_reason": self.stop_reason.value,
            "stop_detail": self.stop_detail,
            "error": None if self.error is None else self.error.to_dict(),
            "handoff": self.handoff.to_trace(),
            "notes": list(self.notes),
            "steps": [s.to_trace() for s in self.steps],
            "tickets": [t.model_dump(mode="json") for t in self.tickets],
            "report": None if self.report is None else self.report.model_dump(mode="json"),
            "record": None if self.record is None else self.record.model_dump(mode="json"),
            "memory": None if self.memory is None else self.memory.to_trace(),
        }


def _handoff(state: WorkflowState, stop: StopReason, detail: str, limits: WorkflowLimits) -> Handoff:
    if stop in (StopReason.REPORT_READY, StopReason.PUBLISHED, StopReason.NOT_PUBLISHED):
        assert state.report is not None
        body = state.report.report
        ticketed = {t.item_id for t in state.tickets}
        actions: List[str] = [f"Locate or request: {item}" for item in body.missing_items]
        actions += [f"Resolve review ticket {t.ticket_id} ({t.item_id})" for t in state.tickets]
        actions += [
            f"Flag for review by hand, no ticket could be opened: {item}"
            for item in body.unclear_items
            if state.input.item_id(item) not in ticketed
        ]
        if state.record is not None:
            record = state.record
            actions.append(
                f"On the procurement record as {record.record_id}, signed off by {record.approved_by}."
            )
            lead = "The report is signed off and published"
        elif stop is StopReason.NOT_PUBLISHED:
            actions.append("Sign off and publish the report once it has been reviewed; it is not on the record.")
            lead = "The report is ready but was not published"
        else:
            actions.append("Sign off the report before it goes on the procurement record.")
            lead = "The report is ready"
        return Handoff(
            HANDOFF_ROLE,
            f"{lead}: {body.overall_status.value}, "
            f"{body.completeness_percentage}% of items present. The findings are advisory.",
            tuple(actions),
        )
    if stop is StopReason.UNAUTHORIZED:
        return Handoff(HANDOFF_ROLE, detail, ("Ask a procurement officer to run the workflow.",))
    if stop is StopReason.SERVICE_UNAVAILABLE:
        return Handoff(HANDOFF_ROLE, detail, (
            f"The model backend stayed unavailable after {limits.max_service_retries} retry(ies). "
            "Start it and run the workflow again; no item has been recorded as checked.",
        ))
    if stop is StopReason.ITERATION_LIMIT:
        actions = [
            f"The run used all {limits.max_iterations} iterations before finishing. "
            "Read the trace, then check the remaining steps by hand or run it again with a higher limit.",
        ]
        if state.report is not None:
            body = state.report.report
            actions.append(
                f"A report was generated before the limit: {body.overall_status.value}, "
                f"{body.completeness_percentage}% of items present. It is in the trace."
            )
        return Handoff(HANDOFF_ROLE, detail, tuple(actions))
    return Handoff(HANDOFF_ROLE, detail, ("Check the submission by hand; the workflow could not finish.",))


class WorkflowRunner:
    def __init__(
        self,
        executor: ToolExecutor,
        limits: Optional[WorkflowLimits] = None,
        sleep: Callable[[float], None] = time.sleep,
        memory: Optional[CaseMemory] = None,
    ) -> None:
        self._executor = executor
        self._limits = limits or WorkflowLimits()
        self._sleep = sleep
        self._memory = memory

    def _finish(
        self, state: WorkflowState, steps: List[StepRecord], principal: Optional[Principal],
        stop: StopReason, detail: str, error: Optional[ToolError] = None,
    ) -> WorkflowRun:
        if error is None and stop in STOP_ERROR_CODE:
            error = ToolError(error_code=STOP_ERROR_CODE[stop], message=detail)
        return WorkflowRun(
            stop_reason=stop,
            stop_detail=detail,
            handoff=_handoff(state, stop, detail, self._limits),
            steps=tuple(steps),
            limits=self._limits,
            principal=principal,
            check=state.check,
            report=state.report,
            record=state.record,
            tickets=state.tickets,
            notes=state.notes,
            error=error,
        )

    def run(self, workflow_input: WorkflowInput, principal: Optional[Principal]) -> WorkflowRun:
        memory = self._memory
        recalled = Recall() if memory is None else memory.recall(workflow_input.submission_id, principal)
        run = self._run_loop(workflow_input, principal)
        if memory is None:
            return run
        return replace(run, memory=memory.conclude(
            recalled,
            submission_id=workflow_input.submission_id,
            document_name=workflow_input.document_name,
            document_text=workflow_input.document_text,
            principal=principal,
            check=run.check,
            report=run.report,
            stop_reason=run.stop_reason.value,
        ))

    def _run_loop(self, workflow_input: WorkflowInput, principal: Optional[Principal]) -> WorkflowRun:
        # The latest state is kept outside the loop so that, if the loop
        # faults, the hand-off still carries whatever the run had found.
        latest = [WorkflowState(input=workflow_input)]
        steps: List[StepRecord] = []
        try:
            return self._loop(latest, steps, principal)
        except Exception:  # noqa: BLE001 - a fault in the loop must still end in a hand-off
            logger.exception("Workflow run failed unexpectedly")
            return self._finish(
                latest[0], steps, principal, StopReason.TOOL_FAILED,
                "The workflow failed unexpectedly and was stopped. The steps so far are in the trace.",
                ToolError(error_code=ErrorCode.ANALYSIS_FAILED, message="The workflow failed unexpectedly."),
            )

    def _loop(
        self, latest: List[WorkflowState], steps: List[StepRecord], principal: Optional[Principal]
    ) -> WorkflowRun:
        limits = self._limits
        state = latest[0]
        while True:
            sensed = state.sense()
            decision = decide(state, limits)
            if decision.abandon is not None:
                # Recorded before anything else, so a dropped step is noted
                # even when the decision that follows it is to stop.
                state = replace(
                    state,
                    last_error=None,
                    abandoned=state.abandoned | {decision.abandon},
                    notes=state.notes + (decision.reason,),
                )
            if decision.action is Action.STOP:
                assert decision.stop_reason is not None
                return self._finish(state, steps, principal, decision.stop_reason,
                                    decision.reason, decision.error)
            if len(steps) >= limits.max_iterations:
                return self._finish(
                    state, steps, principal, StopReason.ITERATION_LIMIT,
                    f"Stopped after {limits.max_iterations} iterations with {decision.action.value} still to do.",
                )
            unapproved = sorted({c.tool for c in decision.calls} - limits.approved_tools)
            if unapproved:
                return self._finish(
                    state, steps, principal, StopReason.TOOL_NOT_APPROVED,
                    f"The plan needed {', '.join(unapproved)}, which is not an approved tool.",
                )

            if decision.retry:
                self._sleep(limits.retry_delay_seconds)

            results = tuple(
                self._executor.execute(call.tool, call.arguments, principal) for call in decision.calls
            )
            state = observe(state, decision.action, results, decision.retry)
            latest[0] = state
            steps.append(StepRecord(len(steps) + 1, sensed, decision, results))
