"""Render a completeness check and an evaluation run as short PDF reports.

Earlier versions of this module explained the project before showing any
result: what the assistant is for, what it must never do, how to read a table,
and a glossary of every term. A reader who already knew all of that had to
scroll past it to reach the findings, and a reader who did not was still made
to read several pages before learning whether anything was missing.

These reports lead with the answer. One line of context, the counts, the
findings as a table, then what the reader has to do next. Everything that is
not one of those four things has been removed.

Uses PyMuPDF's Story API, already a project dependency.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from .models import ItemStatus

PAGE_WIDTH = 595  # A4 portrait, points
PAGE_HEIGHT = 842
MARGIN = 48

CSS = """
body { font-family: sans-serif; font-size: 9.5pt; color: #1a1a1a; line-height: 1.35; }
h1 { font-size: 17pt; margin: 0 0 1pt 0; color: #0f2b46; }
h2 { font-size: 11.5pt; margin: 14pt 0 4pt 0; color: #0f2b46; }
p { margin: 0 0 5pt 0; }
.sub { font-size: 10pt; color: #333333; margin: 0 0 6pt 0; }
.meta { font-size: 8.5pt; color: #555555; margin: 0 0 8pt 0; }
.headline { font-size: 12pt; padding: 8pt; background-color: #eef3f8; margin: 6pt 0; }
.caveat { font-size: 8.5pt; padding: 6pt; background-color: #fdf6e3; margin: 0 0 6pt 0; }
.foot { font-size: 8pt; color: #555555; margin-top: 10pt; }
table { width: 100%; font-size: 8.5pt; }
th { text-align: left; background-color: #e8edf2; padding: 4pt; color: #0f2b46; }
td { padding: 4pt; vertical-align: top; border-bottom: 1px solid #dddddd; }
.ok { color: #1e6b2b; font-weight: bold; }
.no { color: #a12020; font-weight: bold; }
.rev { color: #8a5a00; font-weight: bold; }
.q { font-family: monospace; font-size: 8pt; color: #333333; }
.note { font-size: 7.5pt; color: #5a5a5a; font-style: italic; }
ul { margin: 0 0 5pt 0; }
li { margin: 0 0 2pt 0; }
"""

STATUS_CLASS: Dict[str, str] = {
    ItemStatus.FOUND.value: "ok",
    ItemStatus.NOT_FOUND.value: "no",
    ItemStatus.REQUIRES_HUMAN_REVIEW.value: "rev",
}

# Shown once, at the foot of a check report. The long-form version of this
# occupied three separate sections of the previous layout.
CHECK_FOOTER = (
    "Completeness check only: whether required documents could be located. "
    "Not a score, a ranking, a legal opinion, or a recommendation to accept or "
    "reject this bid. All procurement decisions remain with authorised officers."
)

EM_DASH_PLACEHOLDER = "&#8212;"
ELLIPSIS = "&#8230;"


@dataclass(frozen=True)
class ReportMeta:
    model: str
    prompt_version: str
    strategy: str
    context_tokens: int
    threshold: float
    submission_note: str


def _escape(text: object) -> str:
    return html.escape(str(text), quote=False)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")


def _truncate(text: object, limit: int) -> str:
    """Collapse whitespace and cut to `limit` characters for table display."""
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return _escape(cleaned)
    return _escape(cleaned[: limit - 1]) + ELLIPSIS


def _render(html_body: str, destination: Path) -> Path:
    """Lay the HTML out over as many A4 pages as it needs."""
    try:
        import pymupdf
    except ImportError:  # PyMuPDF older than 1.24 only exposes `fitz`
        import fitz as pymupdf

    destination.parent.mkdir(parents=True, exist_ok=True)
    story = pymupdf.Story(html=html_body, user_css=CSS)
    frame = pymupdf.Rect(MARGIN, MARGIN, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - MARGIN)
    mediabox = pymupdf.Rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT)

    writer = pymupdf.DocumentWriter(str(destination))
    more = True
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(frame)
        story.draw(device)
        writer.end_page()
    writer.close()

    _add_page_numbers(pymupdf, destination)
    return destination


def _add_page_numbers(pymupdf, destination: Path) -> None:
    """Stamp 'Page n of m' on each page. Story does not do running footers."""
    document = pymupdf.open(destination)
    total = document.page_count
    for index, page in enumerate(document, start=1):
        page.insert_text(
            (MARGIN, PAGE_HEIGHT - 26),
            f"Page {index} of {total}",
            fontname="helv",
            fontsize=7.5,
            color=(0.42, 0.42, 0.42),
        )
    document.saveIncr()
    document.close()


# ---------------------------------------------------------------------------
# Completeness report for one submission.
# ---------------------------------------------------------------------------


def _check_rows(report) -> str:
    rows = ["<tr><th>Item</th><th>Status</th><th>Page</th><th>Evidence</th></tr>"]
    for item in report.verified_items:
        status = item.status.value
        css = STATUS_CLASS.get(status, "rev")
        page = str(item.page_number) if item.page_number else EM_DASH_PLACEHOLDER
        snippet = (
            '<span class="q">' + _truncate(item.extracted_snippet, 110) + "</span>"
            if item.extracted_snippet
            else EM_DASH_PLACEHOLDER
        )
        # The evidence check's reason, where there is one. An item reported Not
        # Found because the quoted text turned out to be a different document
        # reads as an unexplained absence without it.
        note = getattr(item, "adjudication_note", None)
        if note:
            snippet += f'<br/><span class="note">{_truncate(note, 150)}</span>'
        rows.append(
            f"<tr><td><b>{_escape(item.checklist_item_id)}</b><br/>"
            f"{_escape(item.clause_title)}</td>"
            f'<td><span class="{css}">{_escape(status)}</span><br/>'
            f"{item.confidence_score:.2f}</td>"
            f"<td>{page}</td>"
            f"<td>{snippet}</td></tr>"
        )
    return "<table>" + "".join(rows) + "</table>"


def _check_actions(report) -> str:
    lines: List[str] = []
    if report.missing_items:
        lines.append(
            "<li><b>Not located, look yourself:</b> "
            + _escape(", ".join(report.missing_items))
            + "</li>"
        )
    if report.review_items:
        lines.append(
            "<li><b>Unsure, you decide:</b> "
            + _escape(", ".join(report.review_items))
            + "</li>"
        )
    if not lines:
        lines.append(
            "<li>Everything was located. Spot-check a few against the page "
            "numbers above.</li>"
        )
    return "<h2>Next</h2><ul>" + "".join(lines) + "</ul>"


def write_check_pdf(
    report,
    model: str,
    page_count: int,
    destination: Path,
    checklist_label: str = "",
    caveat: str = "",
) -> Path:
    """Render one submission's completeness report as a short PDF."""
    counts: Dict[str, int] = {}
    for item in report.verified_items:
        counts[item.status.value] = counts.get(item.status.value, 0) + 1

    checklist_line = (
        f"Checklist: {_escape(checklist_label)} &nbsp;|&nbsp; "
        if checklist_label
        else ""
    )
    caveat_block = (
        f'<div class="caveat">{_escape(caveat)}</div>' if caveat else ""
    )

    body = f"""
<h1>Completeness Check</h1>
<p class="sub">{_escape(report.submission_id)}</p>
<p class="meta">{checklist_line}Model: {_escape(model)} &nbsp;|&nbsp;
{page_count} page(s) &nbsp;|&nbsp; {_now()}</p>

<div class="headline"><b>{counts.get(ItemStatus.FOUND.value, 0)} located
&nbsp;&middot;&nbsp; {counts.get(ItemStatus.NOT_FOUND.value, 0)} not located
&nbsp;&middot;&nbsp; {counts.get(ItemStatus.REQUIRES_HUMAN_REVIEW.value, 0)} need
review</b> &nbsp; of {len(report.verified_items)} required items</div>
{caveat_block}
<h2>Findings</h2>
{_check_rows(report)}
{_check_actions(report)}
<p class="foot">{CHECK_FOOTER}</p>
"""
    return _render(body, destination)


# ---------------------------------------------------------------------------
# Evaluation run across many cases.
# ---------------------------------------------------------------------------

GROUP_TITLES: Sequence[Tuple[str, str]] = (
    ("present", "Finding documents that are present"),
    ("absent", "Noticing documents that are missing"),
    ("safety", "Refusing to go beyond its role"),
    ("formats", "Handling different file types"),
    ("injection", "Resisting hidden instructions"),
)


def _group(results: Sequence) -> Dict[str, List]:
    buckets: Dict[str, List] = {key: [] for key, _ in GROUP_TITLES}
    for result in results:
        if result.id in ("EV-01", "EV-02", "EV-03", "EV-04"):
            buckets["present"].append(result)
        elif result.id in ("EV-05", "EV-06", "EV-07", "EV-18"):
            buckets["absent"].append(result)
        elif result.id in ("EV-08", "EV-09", "EV-10", "EV-11", "EV-13"):
            buckets["safety"].append(result)
        elif result.id == "EV-14":
            buckets["injection"].append(result)
        else:
            buckets["formats"].append(result)
    return buckets


def _area_table(groups: Dict[str, List]) -> str:
    rows = ["<tr><th>Area tested</th><th>As expected</th></tr>"]
    for key, title in GROUP_TITLES:
        members = groups.get(key, [])
        if not members:
            continue
        passed = sum(1 for result in members if result.passed)
        css = "ok" if passed == len(members) else "no"
        rows.append(
            f"<tr><td>{_escape(title)}</td>"
            f'<td><span class="{css}">{passed} of {len(members)}</span></td></tr>'
        )
    return "<table>" + "".join(rows) + "</table>"


def _case_table(results: Sequence) -> str:
    rows = [
        "<tr><th>Case</th><th>Scenario</th><th>Expected</th>"
        "<th>Actual</th><th>Result</th></tr>"
    ]
    for result in results:
        css = "ok" if result.passed else "no"
        verdict = "Pass" if result.passed else "Fail"
        rows.append(
            f"<tr><td><b>{_escape(result.id)}</b></td>"
            f"<td>{_truncate(result.description, 130)}</td>"
            f"<td>{_truncate(result.expected, 110)}</td>"
            f'<td><span class="q">{_truncate(result.actual, 130)}</span></td>'
            f'<td><span class="{css}">{verdict}</span></td></tr>'
        )
    return "<table>" + "".join(rows) + "</table>"


def _failures(results: Sequence) -> str:
    failed = [result for result in results if not result.passed]
    if not failed:
        return ""
    items = "".join(
        f"<li><b>{_escape(result.id)}</b> {_truncate(result.description, 120)}"
        f"<br/>Expected {_truncate(result.expected, 100)}. "
        f"Got {_truncate(result.actual, 130)}.</li>"
        for result in failed
    )
    return "<h2>What failed</h2><ul>" + items + "</ul>"


def build_html(results: Sequence, meta: ReportMeta, caveats: Sequence[str]) -> str:
    groups = _group(results)
    passed = sum(1 for result in results if result.passed)
    limitations = "".join(f"<li>{_escape(c)}</li>" for c in caveats)
    return f"""
<h1>Evaluation Results</h1>
<p class="sub">Public Procurement Document-Completeness Agent</p>
<p class="meta">Model: {_escape(meta.model)} &nbsp;|&nbsp;
Prompt: {_escape(meta.prompt_version)} &nbsp;|&nbsp;
Method: {_escape(meta.strategy)} &nbsp;|&nbsp;
Review threshold: {meta.threshold} &nbsp;|&nbsp;
Context: {meta.context_tokens:,} tokens &nbsp;|&nbsp; {_now()}</p>

<div class="headline"><b>{passed} of {len(results)} cases behaved as expected.</b></div>
<p class="meta">Tested against: {_escape(meta.submission_note)} Every document
is invented; no real bidder or tender data was used.</p>

<h2>By area</h2>
{_area_table(groups)}
{_failures(results)}
<h2>Every case</h2>
{_case_table(results)}
<h2>Limitations</h2>
<ul>{limitations}</ul>
"""


def write_pdf(
    results: Sequence, meta: ReportMeta, caveats: Sequence[str], destination: Path
) -> Path:
    """Render the evaluation results to a PDF at `destination`."""
    return _render(build_html(results, meta, caveats), destination)
