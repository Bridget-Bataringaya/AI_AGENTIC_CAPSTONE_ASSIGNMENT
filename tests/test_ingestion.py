"""Ingestion tests, covering User Stories AC1 and AC2."""

from __future__ import annotations

from pathlib import Path

import pytest

from procurecheck.ingestion import (
    EmptyChecklistError,
    UnsupportedDocumentError,
    parse_checklist,
    parse_submission,
    renumber,
)
from procurecheck.ingestion.submission import EmptyDocumentError


def test_csv_checklist_is_parsed_into_items(sample_checklist_path: Path) -> None:
    items = parse_checklist(sample_checklist_path)
    assert len(items) == 10
    assert items[0].id == "CHK-01"
    assert "Certificate of Incorporation" in items[0].description


def test_plain_text_checklist_strips_list_decoration(tmp_path: Path) -> None:
    path = tmp_path / "checklist.txt"
    path.write_text(
        "1. Certificate of incorporation\n"
        "2) Tax clearance certificate\n"
        "- Bid security\n"
        "* Signed conflict of interest declaration\n"
        "\n"
        "ABC\n",  # too short, treated as a heading
        encoding="utf-8",
    )
    items = parse_checklist(path)
    assert [i.description for i in items] == [
        "Certificate of incorporation",
        "Tax clearance certificate",
        "Bid security",
        "Signed conflict of interest declaration",
    ]
    assert [i.id for i in items] == ["CHK-01", "CHK-02", "CHK-03", "CHK-04"]


def test_unsupported_checklist_type_is_rejected(tmp_path: Path) -> None:
    """AC2: an unsupported file must produce a clear error, not proceed."""
    path = tmp_path / "checklist.xlsx"
    path.write_bytes(b"not really a spreadsheet")
    with pytest.raises(UnsupportedDocumentError) as exc:
        parse_checklist(path)
    assert "Unsupported checklist type" in str(exc.value)


def test_empty_checklist_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "checklist.txt"
    path.write_text("\n\n   \n", encoding="utf-8")
    with pytest.raises(EmptyChecklistError):
        parse_checklist(path)


def test_renumber_returns_a_new_sequential_list(sample_checklist_path: Path) -> None:
    """AC1: the user may edit or delete items before running the check."""
    items = parse_checklist(sample_checklist_path)
    edited = [item for item in items if item.id != "CHK-01"]
    renumbered = renumber(edited)
    assert renumbered[0].id == "CHK-01"
    assert renumbered[0].description == items[1].description
    assert len(renumbered) == 9
    # The originals are untouched.
    assert items[0].id == "CHK-01"


def test_submission_pdf_preserves_page_markers(sample_submission_path: Path) -> None:
    """AC3: evidence must carry a verifiable page number."""
    parsed = parse_submission(sample_submission_path)
    assert parsed.page_count == 7
    marked = parsed.as_marked_text()
    for number in range(1, 8):
        assert f"[PAGE {number}]" in marked
    assert parsed.scanned_pages == []


def test_submission_rejects_unsupported_type(tmp_path: Path) -> None:
    path = tmp_path / "submission.zip"
    path.write_bytes(b"PK\x03\x04")
    with pytest.raises(UnsupportedDocumentError):
        parse_submission(path)


def test_submission_rejects_empty_text(tmp_path: Path) -> None:
    path = tmp_path / "submission.txt"
    path.write_text("   \n\n", encoding="utf-8")
    with pytest.raises(EmptyDocumentError) as exc:
        parse_submission(path)
    assert "OCR" in str(exc.value)


def test_missing_file_is_reported_clearly(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedDocumentError):
        parse_submission(tmp_path / "does-not-exist.pdf")
