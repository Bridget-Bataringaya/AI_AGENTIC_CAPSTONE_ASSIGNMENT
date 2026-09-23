"""The two tools defined in the Tool / Function Specification.

check_document_completeness wraps the existing Matching Engine rather than
re-implementing it, so a check run through a tool call passes through the same
two model passes and the same three deterministic guards as a check run from
the command line. What changes is only the shape: plain text in, the
specification's Present / Missing / Unclear out.

generate_completeness_report makes no model call. Turning a list of verdicts
into totals and next steps is arithmetic, and arithmetic done by a model is
arithmetic that can be wrong. It also re-checks the percentage it is handed
against the results it is handed, because this tool's input may come from a
model or an outside caller rather than from tool 1 directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final, List, Sequence

from ..config import Settings
from ..engine import ContextOverflowError, MatchingEngine
from ..explain import explain
from ..ingestion.submission import ParsedPage, ParsedSubmission
from ..models import ChecklistItem, ItemStatus
from .contracts import (
    CheckCompletenessInput,
    CheckCompletenessOutput,
    ErrorCode,
    GenerateReportInput,
    GenerateReportOutput,
    ItemPresence,
    ItemResult,
    OverallStatus,
    ReportBody,
    ToolFailure,
)

TOOL_CHECK: Final[str] = "check_document_completeness"
TOOL_REPORT: Final[str] = "generate_completeness_report"

ITEM_ID_TEMPLATE: Final[str] = "REQ-{index:02d}"
TOOL_SUBMISSION_ID: Final[str] = "tool-input"

# A percentage handed to the report tool may be rounded, but not wrong.
PERCENTAGE_TOLERANCE: Final[float] = 0.5
PERCENT_DECIMALS: Final[int] = 1

_PAGE_MARKER: Final[re.Pattern[str]] = re.compile(r"\[PAGE (\d+)\]")
# Signatures of a file passed where its extracted text was expected.
_BINARY_PREFIXES: Final[Sequence[str]] = ("%PDF-", "PK\x03\x04", "\xd0\xcf\x11\xe0")

STATUS_TO_PRESENCE: Final = {
    ItemStatus.FOUND: ItemPresence.PRESENT,
    ItemStatus.NOT_FOUND: ItemPresence.MISSING,
    ItemStatus.REQUIRES_HUMAN_REVIEW: ItemPresence.UNCLEAR,
}


@dataclass(frozen=True)
class ToolContext:
    """What a tool may use beyond its arguments.

    `model_client` is anything with `complete_structured`, so tests can hand in
    a scripted stub and the service-unavailable path can be exercised without
    stopping a real server.
    """

    settings: Settings
    model_client: Any


def percentage(results: Sequence[ItemResult]) -> float:
    present = sum(1 for r in results if r.status is ItemPresence.PRESENT)
    return round(100.0 * present / len(results), PERCENT_DECIMALS)


def _to_submission(text: str) -> ParsedSubmission:
    """Rebuild pages from the "[PAGE n]" markers ingestion writes, if present.

    Text without markers is one page, the same convention the ingestion layer
    uses for Word and plain-text files, so no page number is invented.
    """
    parts = _PAGE_MARKER.split(text)
    if len(parts) == 1:
        return ParsedSubmission(TOOL_SUBMISSION_ID, (ParsedPage(1, text),))
    pages = [
        ParsedPage(int(number), body.strip())
        for number, body in zip(parts[1::2], parts[2::2])
    ]
    if parts[0].strip():
        pages.insert(0, ParsedPage(1, parts[0].strip()))
    return ParsedSubmission(TOOL_SUBMISSION_ID, tuple(pages))


def _validate_document(text: str) -> None:
    if not text.strip():
        raise ToolFailure(
            ErrorCode.EMPTY_DOCUMENT,
            "The submitted procurement document contains no readable content.",
        )
    if "\x00" in text or text.lstrip().startswith(tuple(_BINARY_PREFIXES)):
        raise ToolFailure(
            ErrorCode.UNSUPPORTED_DOCUMENT,
            "The submitted document format is not supported. Send the extracted "
            "text of the document, not the file itself.",
        )


def _checklist(required_items: Sequence[str]) -> List[ChecklistItem]:
    descriptions = [item.strip() for item in required_items if item and item.strip()]
    if not descriptions:
        raise ToolFailure(ErrorCode.MISSING_CHECKLIST, "No completeness checklist was provided.")
    return [
        ChecklistItem(id=ITEM_ID_TEMPLATE.format(index=i), description=d)
        for i, d in enumerate(descriptions, start=1)
    ]


def _reason(clause: object, description: str, threshold: float) -> str:
    explanation = explain(clause, description, threshold=threshold)
    status = clause.status  # type: ignore[attr-defined]
    if status is ItemStatus.FOUND:
        return explanation.evidence
    if status is ItemStatus.REQUIRES_HUMAN_REVIEW:
        return f"{explanation.happened} {explanation.next_step}"
    return explanation.happened


def check_document_completeness(
    args: CheckCompletenessInput, context: ToolContext
) -> CheckCompletenessOutput:
    _validate_document(args.document_text)
    items = _checklist(args.required_items)
    submission = _to_submission(args.document_text)

    engine = MatchingEngine(context.model_client, context.settings)
    try:
        outcome = engine.analyse(items, submission)
    except ContextOverflowError as exc:
        raise ToolFailure(ErrorCode.ANALYSIS_FAILED, str(exc)) from exc

    if outcome.report is None:
        # analyse() only refuses on a user instruction, and none is passed.
        raise ToolFailure(ErrorCode.ANALYSIS_FAILED, "The document could not be analysed.")

    by_id = {item.id: item.description for item in items}
    results = [
        ItemResult(
            item=by_id[clause.checklist_item_id],
            status=STATUS_TO_PRESENCE[clause.status],
            reason=_reason(
                clause, by_id[clause.checklist_item_id], context.settings.human_review_threshold
            ),
        )
        for clause in outcome.report.verified_items
    ]
    return CheckCompletenessOutput(
        document_type=args.document_type,
        completeness_percentage=percentage(results),
        results=results,
    )


def _recommendation(result: ItemResult) -> str:
    """Next steps about the document only. Never a verdict on the bid."""
    if result.status is ItemPresence.MISSING:
        return (
            f"Locate or request the {result.item}. The check did not find it "
            "in the document."
        )
    return (
        f"Have a procurement officer confirm the {result.item} by hand. The "
        "check could not decide whether it is present."
    )


def _validate_results(args: GenerateReportInput) -> None:
    results = args.completeness_results
    if not results:
        raise ToolFailure(
            ErrorCode.NO_ANALYSIS_RESULTS,
            "The report cannot be generated because completeness results were not provided.",
        )
    names = [r.item.strip().lower() for r in results]
    if len(set(names)) != len(names):
        raise ToolFailure(
            ErrorCode.INVALID_RESULTS,
            "The supplied completeness results are invalid: an item appears more than once.",
        )
    expected = percentage(results)
    if abs(expected - args.completeness_percentage) > PERCENTAGE_TOLERANCE:
        raise ToolFailure(
            ErrorCode.INVALID_RESULTS,
            f"The supplied completeness results are invalid: the percentage given, "
            f"{args.completeness_percentage}, does not match the results, which give {expected}.",
        )


def generate_completeness_report(
    args: GenerateReportInput, context: ToolContext
) -> GenerateReportOutput:
    _validate_results(args)
    results = args.completeness_results

    def named(status: ItemPresence) -> List[str]:
        return [r.item for r in results if r.status is status]

    missing = named(ItemPresence.MISSING)
    unclear = named(ItemPresence.UNCLEAR)
    if missing:
        overall = OverallStatus.INCOMPLETE
    elif unclear:
        overall = OverallStatus.NEEDS_REVIEW
    else:
        overall = OverallStatus.COMPLETE

    recommendations = [_recommendation(r) for r in results if r.status is not ItemPresence.PRESENT]
    if not recommendations:
        recommendations = [
            "Every required item was found. This confirms completeness only; it "
            "is not an evaluation of the bid."
        ]

    return GenerateReportOutput(
        report=ReportBody(
            document_name=args.document_name,
            document_type=args.document_type,
            overall_status=overall,
            completeness_percentage=percentage(results),
            present_items=named(ItemPresence.PRESENT),
            missing_items=missing,
            unclear_items=unclear,
            recommendations=recommendations,
        )
    )
