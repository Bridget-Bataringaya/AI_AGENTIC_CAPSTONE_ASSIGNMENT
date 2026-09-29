"""publish_completeness_report: the higher-impact action, behind sign-off.

Adding a completeness report to the procurement record is what makes it
official: from then on the evaluation committee works from it. That is why it
needs a person's approval (see approval.py) and the report tools do not.

The record here is simulated: an append-only store held in memory for the
session, the same kind of low-risk stand-in as the review queue. Nothing is
written to a real procurement system. What is real is the control around it:
the call runs only after a procurement officer signs off, the record says who
signed off, and a published report is never overwritten.
"""

from __future__ import annotations

import threading
import unicodedata
from datetime import datetime, timezone
from typing import Callable, Dict, Final, List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from .completeness import PERCENTAGE_TOLERANCE, PERCENT_DECIMALS, ToolContext
from .contracts import ErrorCode, ReportBody, ToolFailure

TOOL_PUBLISH: Final[str] = "publish_completeness_report"
RECORD_ID_TEMPLATE: Final[str] = "REC-{number:06d}"
RECORD_STATUS_PUBLISHED: Final[str] = "published"
LISTED_ITEMS: Final[int] = 5


class PublishReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str = Field(min_length=1, description="The tender submission the report is about")
    report: ReportBody = Field(description="The report returned by generate_completeness_report")


class PublishReportOutput(BaseModel):
    record_id: str
    status: Literal["published"] = RECORD_STATUS_PUBLISHED
    submission_id: str
    overall_status: str
    published_at: datetime
    approved_by: str


def _clean(text: str) -> str:
    """Text from a filename or document, made safe to show in the sign-off prompt.

    Newlines and terminal escape codes are replaced, so a crafted filename or
    checklist line cannot draw a fake "Overall status" line under the real one.
    """
    return "".join(" " if unicodedata.category(c).startswith("C") else c for c in text).strip()


def _listed(items: List[str]) -> str:
    if not items:
        return "none"
    shown = "; ".join(_clean(item) for item in items[:LISTED_ITEMS])
    more = len(items) - LISTED_ITEMS
    return shown if more <= 0 else f"{shown}; and {more} more"


def summarise(args: PublishReportInput) -> str:
    """The sign-off question, written for the officer rather than for code."""
    body = args.report
    return (
        f"Add the completeness report for {_clean(body.document_name)} (submission {_clean(args.submission_id)}) "
        f"to the procurement record, where the evaluation committee will work from it.\n"
        f"  Overall status: {body.overall_status.value}, {body.completeness_percentage}% of items present.\n"
        f"  Missing: {_listed(body.missing_items)}\n"
        f"  Unclear: {_listed(body.unclear_items)}\n"
        f"Once published it is not overwritten."
    )


def _check_report(body: ReportBody) -> None:
    total = len(body.present_items) + len(body.missing_items) + len(body.unclear_items)
    if total == 0:
        raise ToolFailure(ErrorCode.NO_ANALYSIS_RESULTS, "The report lists no checklist items, so it cannot be published.")
    expected = round(100.0 * len(body.present_items) / total, PERCENT_DECIMALS)
    if abs(expected - body.completeness_percentage) > PERCENTAGE_TOLERANCE:
        raise ToolFailure(
            ErrorCode.INVALID_RESULTS,
            f"The report's percentage, {body.completeness_percentage}, does not match its items, "
            f"which give {expected}. It was not published.",
        )


class ProcurementRecord:
    """The simulated procurement record: append-only, one report per submission."""

    def __init__(self, clock: Optional[Callable[[], datetime]] = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        self._entries: List[Tuple[ReportBody, PublishReportOutput]] = []
        self._by_submission: Dict[str, Tuple[ReportBody, PublishReportOutput]] = {}

    def publish(self, request: PublishReportInput, approved_by: str) -> PublishReportOutput:
        with self._lock:
            existing = self._by_submission.get(request.submission_id)
            if existing is not None:
                body, record = existing
                if body == request.report:
                    return record
                raise ToolFailure(
                    ErrorCode.ALREADY_PUBLISHED,
                    f"A different report for submission {request.submission_id} is already on the "
                    f"record as {record.record_id}. A published report is never overwritten.",
                )
            record = PublishReportOutput(
                record_id=RECORD_ID_TEMPLATE.format(number=len(self._entries) + 1),
                submission_id=request.submission_id,
                overall_status=request.report.overall_status.value,
                published_at=self._clock(),
                approved_by=approved_by,
            )
            self._entries.append((request.report, record))
            self._by_submission[request.submission_id] = (request.report, record)
            return record

    def entries(self) -> Tuple[Tuple[ReportBody, PublishReportOutput], ...]:
        with self._lock:
            return tuple(self._entries)


def publish_completeness_report(args: PublishReportInput, context: ToolContext) -> PublishReportOutput:
    approval = context.approval
    if approval is None or not approval.approved or not approval.may_sign_off:
        # The executor's gate normally stops the call first. This is the
        # second lock on the same door, for a handler called any other way.
        raise ToolFailure(ErrorCode.APPROVAL_REQUIRED, "Publishing needs a procurement officer's sign-off.")
    _check_report(args.report)
    record = context.procurement_record
    if record is None:
        raise ToolFailure(
            ErrorCode.SERVICE_UNAVAILABLE,
            "The procurement record is unavailable, so the report was not published. Nothing was changed.",
        )
    return record.publish(args, approved_by=approval.approver.user_id)
