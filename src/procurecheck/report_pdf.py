"""PDF reports: the system's output of record.

A PDF is what the system hands a procurement officer, because it cannot be
edited without that being evident. The same content is also written as a Word
document while the project is in development (see report_docx.py), so that
wording can be reviewed and corrected in a word processor.

Content is decided in report_content.py and laid out in report_layout.py, in
the team's Document Format Standard.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .report_content import CheckMeta, EvaluationMeta, check_report_blocks, evaluation_report_blocks
from .report_layout import write_pdf as _write_blocks


def write_check_pdf(report, meta: CheckMeta, destination: Path) -> Path:
    """Render one submission's completeness report as a PDF."""
    return _write_blocks(check_report_blocks(report, meta), destination)


def write_evaluation_pdf(
    results: Sequence, meta: EvaluationMeta, caveats: Sequence[str], destination: Path
) -> Path:
    """Render an evaluation run as a PDF."""
    return _write_blocks(evaluation_report_blocks(results, meta, caveats), destination)
