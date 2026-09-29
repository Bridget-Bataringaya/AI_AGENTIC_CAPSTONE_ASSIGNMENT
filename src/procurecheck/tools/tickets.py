"""create_review_ticket: the low-risk side-effect tool.

Implements the Third Tool Specification (Johnson, Week 4, ClickUp
123tcvwfnxf). The tool writes one draft entry into the session's review queue
so that an item the check could not decide stays visible to the procurement
officer after the workflow moves on. It decides nothing:

- the ticket is a draft, held in memory for the current session only, and
  touches no procurement record, file or outside system;
- creating it does not change the item's status; the item stays Unclear;
- the queue offers no way to resolve, approve or dismiss a ticket, so neither
  the model nor the workflow can close one. Only an officer can, through the
  human review interface, which is outside this module.

Per the specification it is called by the application (the workflow, after an
Unclear finding), never proposed by the model, so its ToolSpec is not offered
to the model. If the queue is unavailable the call fails openly with
SERVICE_UNAVAILABLE and the item must be flagged by hand.

A second call for the same submission and item returns the ticket already
open instead of creating another, so a retried step changes nothing twice.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, Final, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from .completeness import ToolContext
from .contracts import ErrorCode, ToolFailure

TOOL_TICKET: Final[str] = "create_review_ticket"
TICKET_ID_TEMPLATE: Final[str] = "RVW-{number:06d}"
TICKET_STATUS_CREATED: Final[str] = "draft_created"
REASON_MAX_CHARS: Final[int] = 1000
SNIPPET_MAX_CHARS: Final[int] = 1000


class SuggestedStatus(str, Enum):
    """A starting point for the officer, never a final answer."""

    AMBIGUOUS = "AMBIGUOUS"
    MISSING = "MISSING"


class CreateTicketInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str = Field(min_length=1, description="The tender submission the ticket belongs to")
    item_id: str = Field(min_length=1, description="The checklist item the ticket concerns")
    reason: str = Field(
        min_length=1, max_length=REASON_MAX_CHARS,
        description="Why the item needs a human look",
    )
    suggested_status: SuggestedStatus = Field(description="AMBIGUOUS or MISSING")
    evidence_snippet: Optional[str] = Field(default=None, max_length=SNIPPET_MAX_CHARS)
    page_reference: Optional[int] = Field(default=None, ge=1)


class CreateTicketOutput(BaseModel):
    ticket_id: str
    status: Literal["draft_created"] = TICKET_STATUS_CREATED
    submission_id: str
    item_id: str
    created_at: datetime
    resolved: Literal[False] = False


class ReviewQueue:
    """The session's review queue: append and read, never resolve."""

    def __init__(self, clock: Optional[Callable[[], datetime]] = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        self._entries: List[Tuple[CreateTicketInput, CreateTicketOutput]] = []
        self._open: Dict[Tuple[str, str], CreateTicketOutput] = {}

    def create(self, request: CreateTicketInput) -> CreateTicketOutput:
        key = (request.submission_id, request.item_id)
        with self._lock:
            existing = self._open.get(key)
            if existing is not None:
                return existing
            ticket = CreateTicketOutput(
                ticket_id=TICKET_ID_TEMPLATE.format(number=len(self._entries) + 1),
                submission_id=request.submission_id,
                item_id=request.item_id,
                created_at=self._clock(),
            )
            self._entries.append((request, ticket))
            self._open[key] = ticket
            return ticket

    def entries(self) -> Tuple[Tuple[CreateTicketInput, CreateTicketOutput], ...]:
        """Every ticket with the request that opened it, for the officer's view."""
        with self._lock:
            return tuple(self._entries)


def create_review_ticket(args: CreateTicketInput, context: ToolContext) -> CreateTicketOutput:
    queue = context.review_queue
    if queue is None:
        raise ToolFailure(
            ErrorCode.SERVICE_UNAVAILABLE,
            "The session review queue is unavailable, so no ticket was created. "
            "Flag this item for review by hand.",
        )
    return queue.create(args)
