"""Recall before a run, remember after it.

CaseMemory is the only way the workflow touches the store, and it is built so
that memory cannot steer a run:

- recall happens before the loop and its result is handed to nobody until the
  loop has finished. The planner never sees it and it never enters a prompt;
- the comparison is computed from statuses the run already settled;
- a store that cannot be opened, read or written costs the run its comparison
  and nothing else. Neither method raises.

Who may use it is checked here, in code. Reading the history and writing to it
are separate permissions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

from ..tools.authorization import (
    PERMISSION_HISTORY_READ,
    PERMISSION_HISTORY_WRITE,
    Principal,
    is_permitted,
)
from ..tools.contracts import CheckCompletenessOutput, GenerateReportOutput
from .compare import CaseComparison, compare
from .store import CaseHistoryStore, CaseItem, CaseRecord, fingerprint

logger = logging.getLogger(__name__)

NOTE_MAY_NOT_READ = "The caller's role may not read case history, so no earlier check was recalled."
NOTE_MAY_NOT_WRITE = "The caller's role may not write case history, so this check was not remembered."
NOTE_UNREADABLE = "The case history could not be read, so this check was not compared with an earlier one."
NOTE_UNWRITABLE = "The case history could not be written, so this check was not remembered."
NOTE_NO_REPORT = "The run produced no report, so nothing was remembered."
NOTE_FIRST = "No earlier check of this submission is remembered."


@dataclass(frozen=True)
class Recall:
    """What was found before the run started."""

    previous: Optional[CaseRecord] = None
    notes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class MemoryReport:
    """What memory contributed to one run, for the officer and the trace."""

    retention_days: int
    recalled: Optional[CaseRecord] = None
    comparison: Optional[CaseComparison] = None
    stored: Optional[CaseRecord] = None
    notes: Tuple[str, ...] = ()

    def lines(self) -> Tuple[str, ...]:
        lines = () if self.comparison is None else self.comparison.lines()
        lines += self.notes
        if self.stored is not None:
            lines += (
                f"This check was remembered as case {self.stored.case_id} and is kept for "
                f"{self.retention_days} days.",
            )
        return lines

    def to_trace(self) -> Dict[str, Any]:
        return {
            "retention_days": self.retention_days,
            "used_by_planner": False,
            "recalled": None if self.recalled is None else self.recalled.to_trace(),
            "comparison": None if self.comparison is None else self.comparison.to_trace(),
            "stored_case_id": None if self.stored is None else self.stored.case_id,
            "notes": list(self.notes),
        }


class CaseMemory:
    def __init__(
        self,
        store: CaseHistoryStore,
        app_version: str,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._store = store
        self._version = app_version
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def recall(self, submission_id: str, principal: Optional[Principal]) -> Recall:
        if not is_permitted(principal, PERMISSION_HISTORY_READ):
            return Recall(notes=(NOTE_MAY_NOT_READ,))
        try:
            previous = self._store.latest(submission_id)
        except Exception:  # noqa: BLE001 - no fault in memory may stop a check
            logger.exception("Case history could not be read")
            return Recall(notes=(NOTE_UNREADABLE,))
        return Recall(previous=previous, notes=() if previous is not None else (NOTE_FIRST,))

    def conclude(
        self,
        recalled: Recall,
        *,
        submission_id: str,
        document_name: str,
        document_text: str,
        principal: Optional[Principal],
        check: Optional[CheckCompletenessOutput],
        report: Optional[GenerateReportOutput],
        stop_reason: str,
    ) -> MemoryReport:
        """Compare with the earlier check, then remember this one.

        Only a run that reached a report is remembered: its statuses are the
        settled ones, after any re-check.
        """
        notes = recalled.notes
        days = self._store.retention_days
        if check is None or report is None:
            return MemoryReport(days, recalled.previous, notes=notes + (NOTE_NO_REPORT,))

        try:
            items = tuple(CaseItem(r.item, r.status) for r in check.results)
            sha256 = fingerprint(document_text)
            comparison = (
                None if recalled.previous is None
                else compare(recalled.previous, items, sha256, self._version)
            )
        except Exception:  # noqa: BLE001 - the run is finished; it must still be returned
            logger.exception("Case history could not be compared")
            return MemoryReport(days, recalled.previous, notes=notes + (NOTE_UNREADABLE, NOTE_UNWRITABLE))
        if not is_permitted(principal, PERMISSION_HISTORY_WRITE):
            return MemoryReport(days, recalled.previous, comparison, notes=notes + (NOTE_MAY_NOT_WRITE,))

        assert principal is not None
        record = CaseRecord(
            submission_id=submission_id,
            document_name=document_name,
            document_type=check.document_type,
            document_sha256=sha256,
            items=items,
            completeness_percentage=check.completeness_percentage,
            overall_status=report.report.overall_status.value,
            stop_reason=stop_reason,
            recorded_by=principal.user_id,
            recorded_at=self._clock(),
            app_version=self._version,
        )
        try:
            stored = self._store.remember(record)
        except Exception:  # noqa: BLE001 - no fault in memory may stop a check
            logger.exception("Case history could not be written")
            return MemoryReport(days, recalled.previous, comparison, notes=notes + (NOTE_UNWRITABLE,))
        return MemoryReport(days, recalled.previous, comparison, stored, notes)
