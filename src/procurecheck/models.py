"""Pydantic schemas for the completeness agent.

ClauseVerification and CompletenessReport reproduce the schema fixed in the
Model Selection Note (Sec. 5) and Prompt Specification v1.0 (Sec. 6). The
remaining models support ingestion and the safety boundary and do not alter
that contract.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

REFUSAL_REASON: str = (
    "This system performs document completeness checking only. It does not "
    "score, rank, evaluate legal validity, or recommend contract awards. "
    "Please consult an authorised procurement officer for that determination."
)

COMPLETENESS_DISCLAIMER: str = (
    "This report is a document completeness check only. It records whether "
    "required checklist items could be located in the submission. It does not "
    "constitute a legal review, an eligibility determination, a score, a "
    "ranking, or a recommendation to award or reject any bid. All procurement "
    "decisions remain with authorised human officers."
)


class ItemStatus(str, Enum):
    """The three-way classification confirmed in User Stories AC4 and AC10."""

    FOUND = "Found"
    NOT_FOUND = "Not Found"
    REQUIRES_HUMAN_REVIEW = "Requires Human Review"


class ChecklistItem(BaseModel):
    """One required item extracted from a published procurement checklist."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Unique ID of the checklist item, e.g. CHK-01")
    description: str = Field(description="What the submission is required to contain")

    @field_validator("id", "description")
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("checklist item id and description must not be blank")
        return cleaned


class ClauseVerification(BaseModel):
    """The per-item verdict. Field names are fixed by Prompt Spec v1.0 Sec. 6."""

    checklist_item_id: str = Field(description="Unique ID of the checklist item")
    clause_title: str = Field(description="Name of the required clause or exhibit")
    is_present: bool = Field(description="True if found in submission, False if missing")
    page_number: Optional[int] = Field(
        default=None, description="Page number where the clause appears"
    )
    extracted_snippet: Optional[str] = Field(
        default=None, description="Verbatim text extracted from the submission"
    )
    confidence_score: float = Field(
        description="Match confidence between 0.0 and 1.0", ge=0.0, le=1.0
    )
    requires_human_review: bool = Field(
        description="True if confidence is below the threshold or wording is ambiguous"
    )

    @field_validator("page_number")
    @classmethod
    def _page_number_must_be_positive(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 1:
            return None
        return value

    @property
    def status(self) -> ItemStatus:
        """Derive the user-facing three-way classification.

        Human review takes precedence over present/absent so that a low
        confidence match is never silently reported as Found.
        """
        if self.requires_human_review:
            return ItemStatus.REQUIRES_HUMAN_REVIEW
        return ItemStatus.FOUND if self.is_present else ItemStatus.NOT_FOUND


class CompletenessReport(BaseModel):
    """The full report for one submission."""

    submission_id: str
    verified_items: List[ClauseVerification] = Field(default_factory=list)
    missing_items: List[str] = Field(default_factory=list)

    @property
    def review_items(self) -> List[str]:
        return [
            item.checklist_item_id
            for item in self.verified_items
            if item.status is ItemStatus.REQUIRES_HUMAN_REVIEW
        ]

    @property
    def found_items(self) -> List[str]:
        return [
            item.checklist_item_id
            for item in self.verified_items
            if item.status is ItemStatus.FOUND
        ]

    def with_overridden_item(
        self, checklist_item_id: str, status: ItemStatus
    ) -> "CompletenessReport":
        """Return a NEW report with one item's classification overridden.

        Supports the manual override path required by User Stories AC10. The
        original report is never mutated.
        """
        if status is ItemStatus.REQUIRES_HUMAN_REVIEW:
            raise ValueError("a human override must resolve to Found or Not Found")

        updated = [
            item.model_copy(
                update={
                    "is_present": status is ItemStatus.FOUND,
                    "requires_human_review": False,
                }
            )
            if item.checklist_item_id == checklist_item_id
            else item
            for item in self.verified_items
        ]
        return CompletenessReport(
            submission_id=self.submission_id,
            verified_items=updated,
            missing_items=[
                item.checklist_item_id for item in updated if not item.is_present
            ],
        )


class RefusalResponse(BaseModel):
    """Returned instead of a report when the safety boundary is crossed.

    Wording fixed by Prompt Specification v1.0 Sec. 7.
    """

    refusal: bool = True
    reason: str = REFUSAL_REASON
    trigger: Optional[str] = Field(
        default=None, description="The term that tripped the safety guard"
    )
