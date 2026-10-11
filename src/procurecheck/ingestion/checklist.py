"""Checklist Ingestion and Parsing.

Accepts a published procurement checklist in PDF, CSV or TXT form and extracts
a structured list of required items, which the user may then edit before a
check is run (User Stories AC1).
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Final, List, Sequence, Tuple

from ..models import ChecklistItem
from .submission import UnsupportedDocumentError

SUPPORTED_SUFFIXES: Final[Tuple[str, ...]] = (".csv", ".txt", ".md", ".pdf")
ID_PREFIX: Final[str] = "CHK"

# Header names accepted when reading a CSV checklist, lowercased.
_ID_HEADERS: Final[Tuple[str, ...]] = ("id", "item_id", "ref", "reference", "code", "no", "no.")
_DESCRIPTION_HEADERS: Final[Tuple[str, ...]] = (
    "description", "requirement", "item", "document", "clause", "name", "title",
)

# Leading list decoration to strip from a plain-text checklist line, e.g.
# "1.", "1)", "a.", "-", "*", "CHK-01:".
_LEADING_DECORATION: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:[-*\u2022\u2023\u25cf\u25aa]+|\(?\d{1,3}[.)]|[a-zA-Z][.)]|CHK-\d+\s*[:.]?)\s*",
    re.IGNORECASE,
)

# Lines shorter than this are treated as headings or page furniture, not
# requirements.
MIN_DESCRIPTION_CHARS: Final[int] = 6


class EmptyChecklistError(ValueError):
    """Raised when no requirements could be extracted from a checklist file."""


def format_item_id(index: int) -> str:
    return f"{ID_PREFIX}-{index:02d}"


def _clean_line(line: str) -> str:
    return _LEADING_DECORATION.sub("", line).strip().strip("|").strip()


def _items_from_lines(lines: Sequence[str]) -> List[ChecklistItem]:
    items: List[ChecklistItem] = []
    for line in lines:
        description = _clean_line(line)
        if len(description) < MIN_DESCRIPTION_CHARS:
            continue
        items.append(
            ChecklistItem(id=format_item_id(len(items) + 1), description=description)
        )
    return items


def _pick_column(headers: Sequence[str], candidates: Sequence[str]) -> int | None:
    normalised = [header.strip().lower() for header in headers]
    for candidate in candidates:
        if candidate in normalised:
            return normalised.index(candidate)
    return None


def _items_from_csv(text: str) -> List[ChecklistItem]:
    rows = [row for row in csv.reader(io.StringIO(text)) if any(c.strip() for c in row)]
    if not rows:
        return []

    header = rows[0]
    id_column = _pick_column(header, _ID_HEADERS)
    description_column = _pick_column(header, _DESCRIPTION_HEADERS)

    # No recognisable header: treat every row as data, first column as the
    # requirement text.
    if description_column is None:
        return _items_from_lines([row[0] for row in rows])

    items: List[ChecklistItem] = []
    for row in rows[1:]:
        if description_column >= len(row):
            continue
        description = row[description_column].strip()
        if len(description) < MIN_DESCRIPTION_CHARS:
            continue
        raw_id = (
            row[id_column].strip()
            if id_column is not None and id_column < len(row)
            else ""
        )
        items.append(
            ChecklistItem(
                id=raw_id or format_item_id(len(items) + 1), description=description
            )
        )
    return items


def _text_from_pdf(path: Path) -> str:
    try:
        import pymupdf
    except ImportError:  # PyMuPDF older than 1.24 only exposes `fitz`
        import fitz as pymupdf

    with pymupdf.open(path) as document:
        return "\n".join(page.get_text("text") for page in document)


def parse_checklist(path: Path | str) -> List[ChecklistItem]:
    """Parse a checklist file into an ordered list of required items."""
    path = Path(path)
    if not path.is_file():
        raise UnsupportedDocumentError(f"No such file: {path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedDocumentError(
            f"Unsupported checklist type {suffix!r}. Supported types: "
            f"{', '.join(SUPPORTED_SUFFIXES)}."
        )

    try:
        if suffix == ".pdf":
            items = _items_from_lines(_text_from_pdf(path).splitlines())
        elif suffix == ".csv":
            items = _items_from_csv(path.read_text(encoding="utf-8", errors="replace"))
        else:
            items = _items_from_lines(
                path.read_text(encoding="utf-8", errors="replace").splitlines()
            )
    except UnsupportedDocumentError:
        raise
    except Exception as exc:
        raise UnsupportedDocumentError(
            f"Could not read checklist {path.name}. The file may be corrupted. "
            f"Underlying error: {exc}"
        ) from exc

    if not items:
        raise EmptyChecklistError(
            f"No checklist requirements could be extracted from {path.name}. "
            f"Check that the correct file was uploaded."
        )
    return items


def renumber(items: Sequence[ChecklistItem]) -> List[ChecklistItem]:
    """Return a NEW list with sequential CHK-nn ids, for use after the user
    has edited, added or deleted items (User Stories AC1)."""
    return [
        item.model_copy(update={"id": format_item_id(index)})
        for index, item in enumerate(items, start=1)
    ]
