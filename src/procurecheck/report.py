"""Report Generator and Exporter.

Compiles the classification list, evidence locations and submission metadata
into CSV or JSON, always carrying the completeness-check-only disclaimer
required by User Stories AC5 and AC8.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, Final, List

from .models import COMPLETENESS_DISCLAIMER, CompletenessReport, ItemStatus

CSV_COLUMNS: Final[List[str]] = [
    "checklist_item_id",
    "clause_title",
    "status",
    "page_number",
    "extracted_snippet",
    "confidence_score",
]


def _generated_at() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def summarise(report: CompletenessReport) -> Dict[str, int]:
    """Count items by classification.

    These are counts of documents located, not a score or grade of the
    submission's quality, and must never be presented as one.
    """
    counts = {status.value: 0 for status in ItemStatus}
    for item in report.verified_items:
        counts[item.status.value] += 1
    return counts


def to_dict(report: CompletenessReport, model_name: str) -> Dict[str, Any]:
    """Build the full report payload, disclaimer included."""
    return {
        "submission_id": report.submission_id,
        "generated_at": _generated_at(),
        "model": model_name,
        "disclaimer": COMPLETENESS_DISCLAIMER,
        "summary": summarise(report),
        "items": [
            {
                "checklist_item_id": item.checklist_item_id,
                "clause_title": item.clause_title,
                "status": item.status.value,
                "page_number": item.page_number,
                "extracted_snippet": item.extracted_snippet,
                "confidence_score": round(item.confidence_score, 3),
            }
            for item in report.verified_items
        ],
        "missing_items": report.missing_items,
        "items_requiring_human_review": report.review_items,
    }


def to_json(report: CompletenessReport, model_name: str) -> str:
    return json.dumps(to_dict(report, model_name), indent=2, ensure_ascii=False)


def to_csv(report: CompletenessReport, model_name: str) -> str:
    """Render the report as CSV, with the disclaimer as leading comment rows."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["# Submission", report.submission_id])
    writer.writerow(["# Generated", _generated_at()])
    writer.writerow(["# Model", model_name])
    writer.writerow(["# Disclaimer", COMPLETENESS_DISCLAIMER])
    writer.writerow([])
    writer.writerow(CSV_COLUMNS)
    for item in report.verified_items:
        writer.writerow(
            [
                item.checklist_item_id,
                item.clause_title,
                item.status.value,
                item.page_number if item.page_number is not None else "",
                (item.extracted_snippet or "").replace("\n", " "),
                round(item.confidence_score, 3),
            ]
        )
    return buffer.getvalue()


def to_text(report: CompletenessReport, model_name: str) -> str:
    """Render a plain-text report for terminal output."""
    counts = summarise(report)
    lines: List[str] = [
        f"Completeness report for: {report.submission_id}",
        f"Model: {model_name}",
        f"Generated: {_generated_at()}",
        "",
        "  ".join(f"{status}: {count}" for status, count in counts.items()),
        "",
    ]
    for item in report.verified_items:
        location = f"page {item.page_number}" if item.page_number else "no location"
        lines.append(f"[{item.status.value}] {item.checklist_item_id}  {item.clause_title}")
        lines.append(f"    confidence {item.confidence_score:.2f}  ({location})")
        if item.extracted_snippet:
            snippet = item.extracted_snippet.replace("\n", " ")
            lines.append(f"    evidence: {snippet}")
        lines.append("")
    lines.append(COMPLETENESS_DISCLAIMER)
    return "\n".join(lines)
