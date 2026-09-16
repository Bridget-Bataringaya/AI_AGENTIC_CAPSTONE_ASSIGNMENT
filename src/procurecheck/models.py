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


class EvidenceAdjudication(BaseModel):
    """The second model pass: is the quoted passage really the required document?

    The first pass reads the whole submission and is under constant pressure to
    return something, because a plausible passage is almost always available.
    The measured baseline shows exactly that failure: a conflict-of-interest
    declaration returned for an anti-bribery declaration, a certificate of
    registration returned for a certificate of non-blacklisting. Both quotations
    were genuine, so grounding passed them, and both carried confidence 0.95, so
    the review threshold passed them too.

    This schema is answered by a second call that is shown the requirement and
    the quoted passage ONLY. With the document removed there is nothing to
    latch onto, and the question narrows from "find it" to "are these two the
    same document", which an 8B model answers far more reliably. The naming
    fields come first on purpose: the model must state what the passage IS
    before it is allowed to judge, so the verdict follows the naming instead of
    the naming being written to fit a verdict already reached.
    """

    required_document: str = Field(
        description="The document the checklist requirement asks for, named in a few words"
    )
    quoted_document: str = Field(
        description="What the quoted passage actually is, named in a few words"
    )
    same_document: bool = Field(
        description="True if one physical document could carry both names"
    )
    both_required_separately: bool = Field(
        description=(
            "True if a complete submission would contain both as separate "
            "filings, which means the passage is a different document"
        )
    )
    match_confidence: float = Field(
        description=(
            "How strongly the quoted passage satisfies the requirement, "
            "0.0 to 1.0"
        ),
        ge=0.0,
        le=1.0,
    )

    @property
    def accepts(self) -> bool:
        """Whether the evidence survives the check.

        Both signals must agree. They are deliberately redundant: rejecting a
        genuine document costs the officer one item to check by hand, while
        accepting a missing one hides a real gap behind a sign-off.
        """
        return self.same_document and not self.both_required_separately

    def contradicts_itself(self, conflict_score: float) -> bool:
        """A rejection that still scores the passage highly is arguing with itself.

        The field is a match score, not a meta-confidence: asked how sure it is,
        an 8B model answers how well the passage fits, and in the measured runs
        it returns 1.00 on every acceptance and 0.00 on every rejection. A
        rejection that lands in between is the model genuinely torn, which is
        the one case a human should settle rather than the pipeline.
        """
        return not self.accepts and self.match_confidence >= conflict_score

    @property
    def note(self) -> str:
        """One line a reviewer can read without opening the submission."""
        if self.accepts:
            return (
                f"Evidence check: the quoted {self.quoted_document} is the "
                f"required {self.required_document}."
            )
        return (
            f"Evidence check: the quoted text is a {self.quoted_document}, "
            f"not the required {self.required_document}."
        )


class AdjudicatedClause(ClauseVerification):
    """A verdict carrying the evidence check that produced it.

    A subclass rather than a wider ClauseVerification because ClauseVerification
    is the schema sent to the model, fixed by Prompt Specification v1.0 Sec. 6.
    Widening it would oblige the model to fill a field only the pipeline can
    answer. Reports and the API keep consuming ClauseVerification unchanged.
    """

    adjudication: Optional[EvidenceAdjudication] = None
    adjudication_note: Optional[str] = Field(
        default=None,
        description="Why the evidence check changed the verdict, if it did",
    )


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
