"""Tests for the generated reports.

These reports are the deliverable a supervisor or a procurement officer reads,
so what is asserted here is shape rather than prose: the answer appears before
the explanation, the checklist that produced the findings is named, and a run
against the bundled template says so.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from procurecheck import checklists
from procurecheck.models import ClauseVerification, CompletenessReport
from procurecheck.report import to_text
from procurecheck.report_docx import DocxMeta, build_document, write_docx
from procurecheck.report_pdf import ReportMeta, build_html, write_check_pdf


class FakeResult:
    """Stands in for run_evaluation.CaseResult, which lives outside the package."""

    def __init__(self, identifier: str, passed: bool):
        self.id = identifier
        self.acceptance_criteria = "AC4"
        self.submission = "synthetic-submission.pdf"
        self.description = "Item deliberately omitted from the submission."
        self.expected = "Not Found, with no page number"
        self.actual = "Found (confidence 0.95, page 7)"
        self.passed = passed
        self.seconds = 12.0


@pytest.fixture
def report() -> CompletenessReport:
    return CompletenessReport(
        submission_id="synthetic-submission.pdf",
        verified_items=[
            ClauseVerification(
                checklist_item_id="STD-02",
                clause_title="Certificate of incorporation",
                is_present=True,
                page_number=2,
                extracted_snippet="Appendix A is the certificate of incorporation.",
                confidence_score=0.95,
                requires_human_review=False,
            ),
            ClauseVerification(
                checklist_item_id="STD-09",
                clause_title="Bid security",
                is_present=False,
                confidence_score=0.0,
                requires_human_review=False,
            ),
        ],
        missing_items=["STD-09"],
    )


@pytest.fixture
def results():
    return [FakeResult("EV-01", True), FakeResult("EV-05", False)]


@pytest.fixture
def meta_kwargs():
    return {
        "model": "llama3.1:8b",
        "prompt_version": "v2.0-per-item",
        "strategy": "one check per checklist item",
        "context_tokens": 16384,
        "threshold": 0.85,
        "submission_note": "A seven-page synthetic tender submission.",
    }


def test_terminal_report_puts_one_item_on_one_line(report):
    lines = [line for line in to_text(report, "llama3.1:8b").splitlines() if line]

    assert lines[0].startswith("synthetic-submission.pdf")
    assert any(line.startswith("STD-02") and "Found" in line for line in lines)
    assert any(line.startswith("STD-09") and "Not Found" in line for line in lines)


def test_check_pdf_names_the_checklist_and_carries_the_template_caveat(
    report, tmp_path: Path
):
    destination = tmp_path / "check.pdf"

    write_check_pdf(
        report,
        "llama3.1:8b",
        7,
        destination,
        checklist_label=checklists.label_for(checklists.STANDARD),
        caveat=checklists.TEMPLATE_CAVEAT,
    )

    assert destination.is_file()
    pymupdf = pytest.importorskip("pymupdf")
    with pymupdf.open(destination) as document:
        text = "".join(page.get_text() for page in document)

    assert "Completeness Check" in text
    assert "bundled template" in text
    assert "bidding document" in text  # the caveat survived into the page


def test_check_pdf_omits_the_caveat_when_a_real_checklist_was_used(
    report, tmp_path: Path
):
    destination = tmp_path / "check.pdf"

    write_check_pdf(report, "llama3.1:8b", 7, destination, checklist_label="tender-42.csv")

    pymupdf = pytest.importorskip("pymupdf")
    with pymupdf.open(destination) as document:
        text = "".join(page.get_text() for page in document)

    assert "tender-42.csv" in text
    assert "Edit the checklist" not in text


def test_evaluation_html_leads_with_the_result_not_an_explanation(
    results, meta_kwargs
):
    html = build_html(results, ReportMeta(**meta_kwargs), ["One caveat."])

    headline = html.index("1 of 2 cases behaved as expected")
    assert headline < html.index("<h2>")  # the answer precedes every section
    assert "glossary" not in html.lower()


def test_evaluation_html_lists_failures_before_the_full_table(results, meta_kwargs):
    html = build_html(results, ReportMeta(**meta_kwargs), ["One caveat."])

    assert html.index("What failed") < html.index("Every case")


def test_evaluation_html_has_no_failure_section_when_everything_passed(meta_kwargs):
    html = build_html([FakeResult("EV-01", True)], ReportMeta(**meta_kwargs), [])

    assert "What failed" not in html


def test_docx_has_a_title_block_numbered_sections_and_tables(results, meta_kwargs):
    document = build_document(results, DocxMeta(**meta_kwargs), ["One caveat."])

    texts = [paragraph.text for paragraph in document.paragraphs]
    assert "Public Procurement Document-Completeness Agent" in texts
    assert "1. Run details" in texts
    assert "2. Results by area" in texts
    assert len(document.tables) == 3


def test_docx_renumbers_sections_when_there_are_no_failures(meta_kwargs):
    document = build_document([FakeResult("EV-01", True)], DocxMeta(**meta_kwargs), [])

    texts = [paragraph.text for paragraph in document.paragraphs]
    assert "3. Every case" in texts
    assert not any(text.endswith("Failures") for text in texts)


def test_write_docx_produces_a_readable_file(results, meta_kwargs, tmp_path: Path):
    docx = pytest.importorskip("docx")
    destination = tmp_path / "evaluation.docx"

    write_docx(results, DocxMeta(**meta_kwargs), ["One caveat."], destination)

    assert destination.is_file()
    reopened = docx.Document(str(destination))
    assert any("cases behaved as expected" in p.text for p in reopened.paragraphs)
