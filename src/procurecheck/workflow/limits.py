"""The bounds every workflow run stays inside.

The values here are the implementation's defaults. The team's own values for
maximum iterations, approved tools, stop conditions and hand-off conditions are
a separate Week 5 task (ClickUp 123tcvwhmca); they are all parameters of
WorkflowLimits, so adopting them changes configuration, not code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final, FrozenSet

from ..tools.completeness import TOOL_CHECK, TOOL_REPORT
from ..tools.tickets import TOOL_TICKET

# Check, re-check, open tickets and report is four acting iterations. The
# margin leaves room for one retry of each of two steps after an outage.
DEFAULT_MAX_ITERATIONS: Final[int] = 6
DEFAULT_MAX_SERVICE_RETRIES: Final[int] = 1
DEFAULT_MAX_RECHECK_ROUNDS: Final[int] = 1
DEFAULT_RETRY_DELAY_SECONDS: Final[float] = 5.0
APPROVED_TOOLS: Final[FrozenSet[str]] = frozenset({TOOL_CHECK, TOOL_TICKET, TOOL_REPORT})


class StopReason(str, Enum):
    """Why a run ended. Every one of them hands the case to a person."""

    REPORT_READY = "report_ready"
    UNAUTHORIZED = "unauthorized"
    SERVICE_UNAVAILABLE = "service_unavailable"
    TOOL_FAILED = "tool_failed"
    ITERATION_LIMIT = "iteration_limit"
    TOOL_NOT_APPROVED = "tool_not_approved"


@dataclass(frozen=True)
class WorkflowLimits:
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    max_service_retries: int = DEFAULT_MAX_SERVICE_RETRIES
    max_recheck_rounds: int = DEFAULT_MAX_RECHECK_ROUNDS
    retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS
    approved_tools: FrozenSet[str] = field(default_factory=lambda: APPROVED_TOOLS)

    def __post_init__(self) -> None:
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        if self.max_service_retries < 0:
            raise ValueError("max_service_retries cannot be negative")
        if self.max_recheck_rounds < 0:
            raise ValueError("max_recheck_rounds cannot be negative")
        if self.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds cannot be negative")

    def to_trace(self) -> dict:
        return {
            "max_iterations": self.max_iterations,
            "max_service_retries": self.max_service_retries,
            "max_recheck_rounds": self.max_recheck_rounds,
            "retry_delay_seconds": self.retry_delay_seconds,
            "approved_tools": sorted(self.approved_tools),
        }
