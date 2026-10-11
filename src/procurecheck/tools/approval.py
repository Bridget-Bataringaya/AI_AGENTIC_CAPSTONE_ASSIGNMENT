"""Human approval before a higher-impact action (Week 4, ClickUp 123tcvwfnzg).

The AI Boundary Matrix (Week 1) puts report sign-off in its "Human Approval
Required" category: a completeness report cannot be added to the official
procurement record, or sent to the evaluation committee, without explicit
sign-off from an authorised officer. A tool whose ToolSpec sets
`requires_approval` is held by the ToolExecutor at that point:

    exists? -> permitted? -> arguments valid? -> APPROVED BY A PERSON? -> run

The gate fails closed. With no approver present the call ends as
APPROVAL_REQUIRED and nothing happens. A decline, or an approval from someone
who may not sign off, ends as APPROVAL_DENIED. Either way the decision, who
made it and when, is kept on the ToolResult and so in every trace.

The approval is asked of a person, never of the model, and the model is never
offered a tool that needs one.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Protocol, TextIO

from .authorization import PERMISSION_SIGN_OFF, Principal

APPROVE_WORD = "APPROVE"


@dataclass(frozen=True)
class ApprovalRequest:
    """What the person is asked to approve, in words they can check."""

    tool: str
    summary: str
    requested_by: Optional[Principal]


@dataclass(frozen=True)
class ApprovalDecision:
    approved: bool
    approver: Optional[Principal]
    note: str
    decided_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def may_sign_off(self) -> bool:
        return self.approver is not None and self.approver.may(PERMISSION_SIGN_OFF)

    def to_trace(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "approver": None if self.approver is None else {
                "user_id": self.approver.user_id, "role": self.approver.role,
            },
            "note": self.note,
            "decided_at": self.decided_at.isoformat(timespec="seconds"),
        }


class Approver(Protocol):
    def decide(self, request: ApprovalRequest) -> ApprovalDecision: ...


class ConsoleApprover:
    """Asks the officer at the terminal. Anything but the approve word declines.

    Input that is not an interactive terminal declines without being read, so
    an answer piped in by a script (`echo APPROVE | ...`) never counts as a
    person's sign-off, and a run left unattended can never publish.

    The officer is whoever runs the command; the command line is a trusted
    local entry point, so the person who started the check may also sign it
    off. Requiring a second officer is recorded as open work.
    """

    def __init__(
        self,
        officer: Principal,
        read: Optional[Callable[[str], str]] = None,
        out: Optional[TextIO] = None,
        interactive: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._officer = officer
        self._read = read or input
        self._out = out or sys.stderr
        self._interactive = interactive or (lambda: sys.stdin is not None and sys.stdin.isatty())

    def decide(self, request: ApprovalRequest) -> ApprovalDecision:
        print(f"\nSign-off needed for {request.tool}.", file=self._out)
        print(request.summary, file=self._out)
        if not self._interactive():
            return ApprovalDecision(
                False, self._officer,
                "No one was at an interactive terminal to sign off, so the action was declined.",
            )
        print(f"Type {APPROVE_WORD} to sign off, or anything else to decline: ", end="", file=self._out, flush=True)
        try:
            answer = self._read("")
        except EOFError:
            return ApprovalDecision(False, self._officer, "No answer was given, so the action was declined.")
        if answer.strip() == APPROVE_WORD:
            return ApprovalDecision(True, self._officer, "Signed off at the terminal.")
        return ApprovalDecision(False, self._officer, "Declined at the terminal.")
