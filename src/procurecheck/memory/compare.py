"""Set a fresh check beside the earlier one, item by item.

The comparison is read by a person. It changes nothing: it is computed after
the run has finished, from statuses the run already settled.

When the document text is identical and an item's status still differs, the
model answered the same question two ways. That is reported as its own line,
because it is a reason for a human look and not evidence of a change in the bid.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..tools.contracts import ItemPresence
from .store import CaseItem, CaseRecord, clean

ADVISORY = (
    "This comparison is advisory. Every item was checked afresh, and the earlier "
    "result changed no status."
)


class ChangeKind(str, Enum):
    NOW_PRESENT = "now_present"
    NO_LONGER_PRESENT = "no_longer_present"
    STILL_MISSING = "still_missing"
    STILL_UNCLEAR = "still_unclear"
    STATUS_CHANGED = "status_changed"
    STILL_PRESENT = "still_present"
    NEW_ITEM = "new_item"
    NOT_CHECKED_NOW = "not_checked_now"


@dataclass(frozen=True)
class ItemChange:
    item: str
    kind: ChangeKind
    before: Optional[ItemPresence]
    after: Optional[ItemPresence]

    @property
    def differs(self) -> bool:
        return self.before is not None and self.after is not None and self.before is not self.after

    def to_trace(self) -> Dict[str, Any]:
        return {
            "item": self.item,
            "change": self.kind.value,
            "before": None if self.before is None else self.before.value,
            "after": None if self.after is None else self.after.value,
        }


def _kind(before: ItemPresence, after: ItemPresence) -> ChangeKind:
    if before is after:
        return {
            ItemPresence.PRESENT: ChangeKind.STILL_PRESENT,
            ItemPresence.MISSING: ChangeKind.STILL_MISSING,
            ItemPresence.UNCLEAR: ChangeKind.STILL_UNCLEAR,
        }[after]
    if after is ItemPresence.PRESENT:
        return ChangeKind.NOW_PRESENT
    if before is ItemPresence.PRESENT:
        return ChangeKind.NO_LONGER_PRESENT
    return ChangeKind.STATUS_CHANGED


@dataclass(frozen=True)
class CaseComparison:
    previous: CaseRecord
    same_document: bool
    same_version: bool
    changes: Tuple[ItemChange, ...]

    def of(self, kind: ChangeKind) -> List[ItemChange]:
        return [c for c in self.changes if c.kind is kind]

    @property
    def inconsistent(self) -> List[ItemChange]:
        """Items whose status differs although the text checked is the same."""
        return [c for c in self.changes if c.differs] if self.same_document else []

    def lines(self) -> Tuple[str, ...]:
        """The comparison as an officer reads it."""
        earlier = self.previous
        when = earlier.recorded_at.strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"Earlier check: {when} by {earlier.recorded_by}, {earlier.overall_status}, "
            f"{earlier.completeness_percentage}% of items present (ProcureCheck {earlier.app_version}).",
            "The document text is identical to the one checked then." if self.same_document
            else "The document text has changed since then.",
        ]
        if not self.same_version:
            lines.append("The earlier check was made by a different version, so a difference may come from the build.")
        lines += [f"Now present, was {c.before.value}: {c.item}" for c in self.of(ChangeKind.NOW_PRESENT)]
        lines += [
            f"No longer present, was Present and is now {c.after.value}: {c.item}. Confirm by hand."
            for c in self.of(ChangeKind.NO_LONGER_PRESENT)
        ]
        lines += [f"Still missing: {c.item}" for c in self.of(ChangeKind.STILL_MISSING)]
        lines += [f"Still unclear: {c.item}" for c in self.of(ChangeKind.STILL_UNCLEAR)]
        lines += [
            f"Was {c.before.value}, is now {c.after.value}: {c.item}"
            for c in self.of(ChangeKind.STATUS_CHANGED)
        ]
        lines += [f"New on the checklist, not checked before: {c.item}" for c in self.of(ChangeKind.NEW_ITEM)]
        lines += [
            f"On the earlier checklist but not this one: {c.item}"
            for c in self.of(ChangeKind.NOT_CHECKED_NOW)
        ]
        unchanged = len(self.of(ChangeKind.STILL_PRESENT))
        if unchanged:
            lines.append(f"Present both times: {unchanged} item(s).")
        if self.inconsistent:
            lines.append(
                f"The same text gave a different answer for {len(self.inconsistent)} item(s). "
                "The model's reading varied, so check those items by hand."
            )
        lines.append(ADVISORY)
        return tuple(lines)

    def to_trace(self) -> Dict[str, Any]:
        return {
            "same_document": self.same_document,
            "same_version": self.same_version,
            "inconsistent_items": [c.item for c in self.inconsistent],
            "changes": [c.to_trace() for c in self.changes],
        }


def _key(item: str) -> str:
    """Stored items were cleaned on the way in, so both sides are cleaned here."""
    return clean(item).lower()


def compare(
    previous: CaseRecord,
    current_items: Sequence[CaseItem],
    document_sha256: str,
    app_version: str,
) -> CaseComparison:
    """Changes in current checklist order, then items only the earlier check had."""
    before = {_key(i.item): i for i in previous.items}
    changes: List[ItemChange] = []
    seen = set()
    for current in current_items:
        key = _key(current.item)
        seen.add(key)
        earlier = before.get(key)
        if earlier is None:
            changes.append(ItemChange(current.item, ChangeKind.NEW_ITEM, None, current.status))
        else:
            changes.append(
                ItemChange(current.item, _kind(earlier.status, current.status), earlier.status, current.status)
            )
    changes += [
        ItemChange(i.item, ChangeKind.NOT_CHECKED_NOW, i.status, None)
        for key, i in before.items() if key not in seen
    ]
    return CaseComparison(
        previous=previous,
        same_document=previous.document_sha256 == document_sha256,
        same_version=previous.app_version == app_version,
        changes=tuple(changes),
    )
