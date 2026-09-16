"""Segmentation: turn one corpus document into ordered, heading-aware blocks.

A block is the smallest unit the chunker may not split unless it is oversized:
a paragraph, a table row, a PDF text block, or a run of OCR lines ending in a
full stop. Each block carries the heading it sits under, so a chunk can say
where in the document it came from and so the heading's words are searchable
alongside the text beneath it.

Why not reuse ingestion.submission: that reader serves the completeness check,
where a Word document is one page and its tables are appended at the end.
Retrieval needs body order kept (a table row read out of place is how a "Yes"
gets bound to the wrong header) and headings kept. The submission reader is
left untouched so the recorded Week 2 evaluation still reproduces.

Page numbers: PDFs and OCR text have real pages. Word files have none until
rendered, but the PPDA standard documents print "Page N of M" into the body at
the end of each page, so blocks before such a marker are given printed page N.
Blocks with no marker after them keep page None rather than a guessed number.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, Iterator, List, Optional, Sequence, Set

from .corpus import CorpusDocument

_WHITESPACE: Final[re.Pattern] = re.compile(r"\s+")
_PAGE_OF: Final[re.Pattern] = re.compile(r"^page\s+(\d+)\s+of\s+\d+$", re.IGNORECASE)
_ROMAN_PAGE: Final[re.Pattern] = re.compile(r"^page\s+[ivxlc]+$", re.IGNORECASE)
_BARE_NUMBER: Final[re.Pattern] = re.compile(r"^\d{1,5}$")
_TOC_LINE: Final[re.Pattern] = re.compile(r"(\.{4,}|\t)\s*\d{1,4}\s*$")
_MAJOR_PREFIX: Final[re.Pattern] = re.compile(
    r"^(part|section|chapter|schedule|annex|appendix)\b", re.IGNORECASE
)
_NUMBERED_TITLE: Final[re.Pattern] = re.compile(r"^\s*(\d{1,3})\.\s*\n(.+)", re.DOTALL)
_TERMINAL_PUNCTUATION: Final[str] = ".;:,"
_MINOR_WORDS: Final[frozenset] = frozenset(
    "a an and as at by for from in of on or the to under with".split()
)
MAX_HEADING_WORDS: Final[int] = 12
MAX_TITLE_LINES: Final[int] = 3
RUNNING_HEADER_MAX_WORDS: Final[int] = 15
RUNNING_HEADER_MIN_PAGES: Final[int] = 3
TITLE_CASE_SHARE: Final[float] = 0.6


@dataclass(frozen=True)
class Block:
    text: str
    page: Optional[int]
    heading: Optional[str]


def clean(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def looks_like_heading(text: str) -> bool:
    """Short, unpunctuated, and set in capitals or title case.

    Used where the file carries no heading style: PDFs, OCR text, and Word
    paragraphs styled as body text that are visibly headings.
    """
    words = text.split()
    if not 2 <= len(words) <= MAX_HEADING_WORDS or text[-1] in _TERMINAL_PUNCTUATION:
        return False
    # A list item such as "Bankrupt; or" is short and capitalised, but a
    # heading never carries a semicolon or trails off on a joining word.
    if ";" in text or words[-1].lower() in _MINOR_WORDS:
        return False
    if text.isupper() or _MAJOR_PREFIX.match(text):
        return True
    significant = [w for w in words if w.lower() not in _MINOR_WORDS]
    capitalised = [w for w in significant if w[:1].isupper()]
    return bool(significant) and len(capitalised) / len(significant) >= TITLE_CASE_SHARE


class _HeadingTrail:
    """The current major heading (Part, Section) and the heading under it."""

    def __init__(self) -> None:
        self.major: Optional[str] = None
        self.minor: Optional[str] = None

    def push(self, text: str, major: bool) -> None:
        if major:
            self.major, self.minor = text, None
        else:
            self.minor = text

    @property
    def path(self) -> Optional[str]:
        parts = [p for p in (self.major, self.minor) if p]
        return " > ".join(parts) or None


def _style_is_major(style: str) -> bool:
    return style in ("title", "heading 1", "t1", "tk1") or style.startswith("tk")


def _docx_blocks(path: Path) -> Iterator[Block]:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx.Document(str(path))
    trail = _HeadingTrail()
    pending: List[Block] = []

    for element in document.element.body.iterchildren():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = Paragraph(element, document)
            text = clean(paragraph.text)
            if not text:
                continue
            page_marker = _PAGE_OF.match(text)
            if page_marker or _ROMAN_PAGE.match(text):
                number = int(page_marker.group(1)) if page_marker else None
                yield from (replace(block, page=number) for block in pending)
                pending = []
                continue
            style = (paragraph.style.name if paragraph.style is not None else "").lower()
            if style.startswith("toc") or _TOC_LINE.search(paragraph.text):
                continue
            styled = style.startswith("heading") or style in ("title", "t1", "tk1", "tk2", "tk3")
            if styled or looks_like_heading(text):
                trail.push(text, _style_is_major(style) or bool(_MAJOR_PREFIX.match(text)))
            pending.append(Block(text=text, page=None, heading=trail.path))
        elif tag == "tbl":
            for row in Table(element, document).rows:
                cells: List[str] = []
                for cell in row.cells:
                    value = clean(cell.text)
                    # Merged cells repeat their text once per grid column.
                    if value and (not cells or cells[-1] != value):
                        cells.append(value)
                if cells:
                    pending.append(Block(text=" | ".join(cells), page=None, heading=trail.path))
    yield from pending


def _is_layout_heading(text: str) -> bool:
    """The stricter heading test for PDF and OCR text.

    In a PDF every wrapped line of a title-case title is its own block, so the
    title-case test splits one title into a run of one-line "sections". Only
    capitals or a Part/Section prefix count here; numbered regulation titles are
    caught separately.
    """
    words = text.split()
    if not 2 <= len(words) <= MAX_HEADING_WORDS or text[-1] in _TERMINAL_PUNCTUATION or ";" in text:
        return False
    return text.isupper() or bool(_MAJOR_PREFIX.match(text))


def _repeated(pages: Sequence[Sequence[str]]) -> Set[str]:
    """Short texts printed on several pages: running headers and footers."""
    counts: Counter = Counter()
    for texts in pages:
        counts.update({t for t in texts if len(t.split()) <= RUNNING_HEADER_MAX_WORDS})
    return {text for text, pages_seen in counts.items() if pages_seen >= RUNNING_HEADER_MIN_PAGES}


def _numbered_title(raw: str) -> Optional[str]:
    """'13.
Rules for open domestic bidding.
(1) ...' -> '13. Rules for open domestic bidding.'"""
    numbered = _NUMBERED_TITLE.match(raw)
    if not numbered:
        return None
    title_lines: List[str] = []
    for line in numbered.group(2).splitlines()[:MAX_TITLE_LINES]:
        title_lines.append(line.strip())
        if line.strip().endswith("."):
            break
    return f"{numbered.group(1)}. {clean(' '.join(title_lines))}"


def _pdf_blocks(path: Path) -> Iterator[Block]:
    try:
        import pymupdf
    except ImportError:  # PyMuPDF older than 1.24 only exposes `fitz`
        import fitz as pymupdf

    with pymupdf.open(path) as document:
        pages = [
            [(raw[4], clean(raw[4])) for raw in page.get_text("blocks", sort=True) if raw[6] == 0]
            for page in document
        ]
    running = _repeated([[text for _raw, text in blocks] for blocks in pages])
    trail = _HeadingTrail()
    for number, blocks in enumerate(pages, start=1):
        for raw, text in blocks:
            if not text or text in running or _BARE_NUMBER.match(text) or _TOC_LINE.search(raw):
                continue
            title = _numbered_title(raw)
            if title:
                trail.push(title, False)
            elif _is_layout_heading(text):
                trail.push(text, bool(_MAJOR_PREFIX.match(text)))
            yield Block(text=text, page=number, heading=trail.path)


def _ocr_blocks(directory: Path) -> Iterator[Block]:
    """One text file per page, named <doc>_pNN.txt. A block ends at a full stop."""
    page_files = sorted(directory.glob("*_p*.txt"))
    pages = [
        [clean(line) for line in f.read_text(encoding="utf-8").splitlines() if clean(line)]
        for f in page_files
    ]
    running = _repeated(pages)
    trail = _HeadingTrail()
    for page_file, lines_on_page in zip(page_files, pages):
        number = int(page_file.stem.rsplit("_p", 1)[1])
        lines: List[str] = []
        for line in lines_on_page:
            if line in running or _BARE_NUMBER.match(line):
                continue
            if not lines and _is_layout_heading(line):
                trail.push(line, bool(_MAJOR_PREFIX.match(line)))
            lines.append(line)
            if line.endswith((".", ":", ";")):
                yield Block(text=" ".join(lines), page=number, heading=trail.path)
                lines = []
        if lines:
            yield Block(text=" ".join(lines), page=number, heading=trail.path)


def _text_blocks(path: Path) -> Iterator[Block]:
    """Plain text: blank lines separate blocks, and the file is one page."""
    trail = _HeadingTrail()
    for paragraph in path.read_text(encoding="utf-8", errors="replace").split("\n\n"):
        text = clean(paragraph.lstrip("#"))
        if not text:
            continue
        if looks_like_heading(text):
            trail.push(text, bool(_MAJOR_PREFIX.match(text)))
        yield Block(text=text, page=1, heading=trail.path)


def segment(document: CorpusDocument) -> List[Block]:
    """Blocks of one document, in reading order."""
    source = document.text_source
    if source.is_dir():
        return list(_ocr_blocks(source))
    suffix = source.suffix.lower()
    if suffix == ".docx":
        return list(_docx_blocks(source))
    if suffix == ".pdf":
        return list(_pdf_blocks(source))
    if suffix in (".txt", ".md"):
        return list(_text_blocks(source))
    raise ValueError(f"{document.doc_id}: no segmenter for {suffix!r} ({source.name}).")
