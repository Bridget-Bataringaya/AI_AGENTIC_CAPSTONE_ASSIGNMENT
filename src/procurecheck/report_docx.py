"""Word reports: the working copy produced during development.

The PDF is the system's output of record. While the project is being built,
every report is also written as a Word document with the same content, because
wording is reviewed and corrected in a word processor, not in a PDF viewer.

Content is decided in report_content.py and laid out in report_layout.py, in
the team's Document Format Standard.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .report_content import CheckMeta, EvaluationMeta, check_report_blocks, evaluation_report_blocks
from .report_layout import build_word, write_word


def write_check_docx(report, meta: CheckMeta, destination: Path) -> Path:
    """Write one submission's completeness report as a Word document."""
    return write_word(check_report_blocks(report, meta), destination)


def build_evaluation_document(results: Sequence, meta: EvaluationMeta, caveats: Sequence[str]):
    """The evaluation report as a python-docx Document, for inspection in tests."""
    return build_word(evaluation_report_blocks(results, meta, caveats))


def write_evaluation_docx(
    results: Sequence, meta: EvaluationMeta, caveats: Sequence[str], destination: Path
) -> Path:
    """Write an evaluation run as a Word document."""
    return write_word(evaluation_report_blocks(results, meta, caveats), destination)
