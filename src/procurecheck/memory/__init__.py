"""Persistent memory (Week 6): the case history of a submission.

The one justified use: a bidder is asked for missing documents and submits
again. The officer then needs to know what changed since the last check, and
which requested items arrived. Without memory that means finding the old
report and reading the two side by side.

store     what is kept, for how long, and how it is deleted
compare   the fresh check set beside the earlier one
recall    recall before a run, remember after it; never steers the run
commands  the `memory` command: list, show, forget, purge
"""

from .compare import CaseComparison, ChangeKind, ItemChange, compare
from .recall import CaseMemory, MemoryReport, Recall
from .store import (
    CaseHistoryStore,
    CaseItem,
    CaseRecord,
    MemoryUnavailableError,
    SubmissionSummary,
    fingerprint,
    resolve_store_path,
    validate_submission_id,
)

__all__ = [
    "CaseComparison",
    "CaseHistoryStore",
    "CaseItem",
    "CaseMemory",
    "CaseRecord",
    "ChangeKind",
    "ItemChange",
    "MemoryReport",
    "MemoryUnavailableError",
    "Recall",
    "SubmissionSummary",
    "compare",
    "fingerprint",
    "resolve_store_path",
    "validate_submission_id",
]
