"""What the workflow knows, and how one tool result changes it.

WorkflowState is immutable. Each Observe step returns a new state rather than
editing the old one, so the trace can show exactly what the workflow knew when
it made each decision.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Sequence, Tuple

from ..tools.completeness import ITEM_ID_TEMPLATE, percentage
from ..tools.contracts import (
    CheckCompletenessOutput,
    GenerateReportOutput,
    ItemPresence,
    ItemResult,
    ToolError,
)
from ..tools.registry import ToolResult
from ..tools.publishing import PublishReportOutput
from ..tools.tickets import CreateTicketOutput


class Action(str, Enum):
    CHECK = "check"
    RECHECK = "recheck_unclear"
    OPEN_TICKETS = "open_review_tickets"
    REPORT = "generate_report"
    PUBLISH = "publish_report"
    STOP = "stop"


@dataclass(frozen=True)
class WorkflowInput:
    """The one submission a run works on, supplied by the application."""

    submission_id: str
    document_name: str
    document_type: str
    document_text: str
    required_items: Tuple[str, ...]

    def __post_init__(self) -> None:
        # Blank lines are dropped and a repeated item is kept once, in its
        # first position. The report tool refuses duplicate items, so a
        # repeated line would otherwise fail the run after the slow check.
        seen = set()
        items = []
        for raw in self.required_items:
            item = raw.strip()
            if item and item.lower() not in seen:
                seen.add(item.lower())
                items.append(item)
        object.__setattr__(self, "required_items", tuple(items))

    def item_id(self, description: str) -> str:
        """The checklist identifier, REQ-01 and so on, in checklist order."""
        keys = [item.lower() for item in self.required_items]
        return ITEM_ID_TEMPLATE.format(index=keys.index(description.strip().lower()) + 1)


@dataclass(frozen=True)
class WorkflowState:
    input: WorkflowInput
    check: Optional[CheckCompletenessOutput] = None
    recheck_rounds: int = 0
    tickets: Tuple[CreateTicketOutput, ...] = ()
    tickets_opened: bool = False
    report: Optional[GenerateReportOutput] = None
    record: Optional[PublishReportOutput] = None
    last_action: Optional[Action] = None
    last_error: Optional[ToolError] = None
    consecutive_retries: int = 0
    abandoned: FrozenSet[Action] = frozenset()
    notes: Tuple[str, ...] = ()

    def unclear_items(self) -> List[ItemResult]:
        if self.check is None:
            return []
        return [r for r in self.check.results if r.status is ItemPresence.UNCLEAR]

    def sense(self) -> Dict[str, Any]:
        """The Sense step: a summary of everything the next decision may use."""
        counts = {status.value: 0 for status in ItemPresence}
        if self.check is not None:
            for result in self.check.results:
                counts[result.status.value] += 1
        return {
            "checked": self.check is not None,
            "completeness_percentage": None if self.check is None else self.check.completeness_percentage,
            "item_counts": counts,
            "recheck_rounds": self.recheck_rounds,
            "tickets_open": len(self.tickets),
            "report_ready": self.report is not None,
            "published": self.record is not None,
            "last_error": None if self.last_error is None else self.last_error.error_code.value,
            "consecutive_retries": self.consecutive_retries,
            "abandoned": sorted(a.value for a in self.abandoned),
        }


def merge_recheck(
    first: CheckCompletenessOutput, second: CheckCompletenessOutput
) -> CheckCompletenessOutput:
    """Replace the re-checked items' results and recompute the percentage.

    Items not in the re-check keep their first result, so a re-check can only
    change the items it was asked about.
    """
    fresh = {r.item: r for r in second.results}
    results = [fresh.get(r.item, r) for r in first.results]
    return CheckCompletenessOutput(
        document_type=first.document_type,
        completeness_percentage=percentage(results),
        results=results,
    )


def observe(
    state: WorkflowState, action: Action, results: Sequence[ToolResult], retry: bool
) -> WorkflowState:
    """The Observe step: fold the tool results of one Act into a new state."""
    errors = [r.error for r in results if r.error is not None]
    outputs = [r.output for r in results if r.ok]
    updated = replace(
        state,
        last_action=action,
        last_error=errors[0] if errors else None,
        consecutive_retries=state.consecutive_retries + 1 if retry else 0,
    )
    if action is Action.CHECK and outputs:
        return replace(updated, check=outputs[0])
    if action is Action.RECHECK and outputs:
        assert state.check is not None
        return replace(
            updated,
            check=merge_recheck(state.check, outputs[0]),
            recheck_rounds=state.recheck_rounds + 1,
        )
    if action is Action.OPEN_TICKETS:
        known = {t.ticket_id for t in state.tickets}
        new = tuple(t for t in outputs if t.ticket_id not in known)
        return replace(updated, tickets=state.tickets + new, tickets_opened=not errors)
    if action is Action.REPORT and outputs:
        return replace(updated, report=outputs[0])
    if action is Action.PUBLISH and outputs:
        return replace(updated, record=outputs[0])
    return updated
