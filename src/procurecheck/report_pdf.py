"""Render the evaluation results as a PDF a non-technical reader can follow.

The Markdown and CSV outputs are for the repository and the spreadsheet. This
is for a human being who was not in the room: a supervisor, a marker, or a
procurement officer. It therefore explains what was tested and why before it
shows any result, groups findings by what they mean rather than by case number,
and spells out every term it uses.

Uses PyMuPDF's Story API, which is already a project dependency, so no
additional package is needed.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence

PAGE_WIDTH = 595  # A4 portrait, points
PAGE_HEIGHT = 842
MARGIN = 48

CSS = """
body { font-family: sans-serif; font-size: 10pt; color: #1a1a1a; line-height: 1.45; }
h1 { font-size: 21pt; margin: 0 0 2pt 0; color: #0f2b46; }
h2 { font-size: 14pt; margin: 18pt 0 6pt 0; color: #0f2b46; }
h3 { font-size: 11pt; margin: 12pt 0 3pt 0; color: #0f2b46; }
p { margin: 0 0 7pt 0; }
.subtitle { font-size: 11pt; color: #4a4a4a; margin-bottom: 10pt; }
.meta { font-size: 9pt; color: #4a4a4a; margin-bottom: 2pt; }
.headline { font-size: 13pt; padding: 9pt; background-color: #eef3f8; margin: 10pt 0; }
.good { padding: 7pt; background-color: #edf7ed; margin: 5pt 0; }
.bad { padding: 7pt; background-color: #fdeded; margin: 5pt 0; }
.note { padding: 7pt; background-color: #fdf6e3; margin: 7pt 0; font-size: 9.5pt; }
.case { margin: 0 0 11pt 0; }
.label { color: #4a4a4a; font-size: 9pt; }
.pass { color: #1e6b2b; font-weight: bold; }
.fail { color: #a12020; font-weight: bold; }
.quote { font-family: monospace; font-size: 8.5pt; color: #333333; }
ul { margin: 0 0 7pt 0; }
li { margin: 0 0 3pt 0; }
"""


@dataclass(frozen=True)
class ReportMeta:
    model: str
    prompt_version: str
    strategy: str
    context_tokens: int
    threshold: float
    submission_note: str


def _escape(text: str) -> str:
    return html.escape(str(text), quote=False)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")


def _cover(passed: int, total: int, meta: ReportMeta) -> str:
    failed = total - passed
    verdict = (
        "Every check behaved as expected."
        if failed == 0
        else f"{passed} of the {total} checks behaved as expected. {failed} did not."
    )
    return f"""
<h1>Completeness Agent: Test Results</h1>
<p class="subtitle">Public Procurement Document-Completeness Agent<br/>
BSE4104 Capstone, Group-H (Evening), Makerere University</p>
<p class="meta">Generated {_now()}</p>
<p class="meta">Model tested: {_escape(meta.model)} &nbsp;|&nbsp;
Prompt version: {_escape(meta.prompt_version)} &nbsp;|&nbsp;
Method: {_escape(meta.strategy)}</p>

<div class="headline"><b>Result: {_escape(verdict)}</b></div>

<h2>What this document is</h2>
<p>This is a record of testing carried out on a software assistant that checks
whether a tender submission contains every document a procurement checklist
requires. It is written to be readable without any technical background.</p>

<h2>What the assistant is for</h2>
<p>When a supplier submits a bid, that bid must contain a set of required
documents: a certificate of incorporation, a tax clearance certificate, a bid
security, and so on. Today a human reviewer reads the whole package and ticks
each item off a list by hand. That is slow, and an item can be missed when it
appears under an unexpected heading or deep in an attachment.</p>
<p>The assistant reads the checklist and the submission and reports, for each
required item, whether it could find it, on which page, and quoting the exact
words it relied on. A human then verifies the findings.</p>

<h2>What the assistant must never do</h2>
<p>The assistant is deliberately limited. It must never score or grade a bid,
never rank or compare bidders, never comment on whether a clause is legally
valid, and never recommend awarding or rejecting a contract. Those judgements
belong to authorised procurement officers. Several of the tests below exist
purely to confirm the assistant refuses to cross that line.</p>

<h2>How to read the results</h2>
<p>Each test is one scenario. Before running anything, we wrote down what
<i>should</i> happen. We then ran it and recorded what <i>actually</i> happened.
A test passes only if the two match.</p>
<div class="note"><b>A failed test is useful information, not a disaster.</b>
This is a first working version, and the purpose of testing it is to find out
exactly where it falls short so the next version can fix those specific
things.</div>

<h2>What was tested against</h2>
<p>{_escape(meta.submission_note)}</p>
<p>Every document used is invented. No real bidder, no real procuring entity,
and no confidential information was used at any point.</p>
"""


def _plain_english_summary(results: Sequence, groups: Dict[str, List]) -> str:
    parts = ['<h2>The findings in plain English</h2>']
    for title, blurb, members in _group_specs(groups):
        if not members:
            continue
        passed = sum(1 for r in members if r.passed)
        css = "good" if passed == len(members) else "bad"
        parts.append(
            f'<div class="{css}"><b>{_escape(title)}: {passed} of {len(members)} '
            f'behaved as expected.</b><br/>{blurb}</div>'
        )
    return "".join(parts)


def _group_specs(groups: Dict[str, List]):
    return [
        (
            "Finding documents that are present",
            "The assistant was given items that really were in the submission, "
            "but described using different words from the checklist. This is the "
            "hardest part of the job and the main reason for using AI rather "
            "than a simple word search.",
            groups.get("present", []),
        ),
        (
            "Noticing documents that are missing",
            "The assistant was given items that had deliberately been left out. "
            "Reporting a missing document as present is the most damaging "
            "mistake this system can make, because a reviewer would stop "
            "looking for it.",
            groups.get("absent", []),
        ),
        (
            "Refusing to go beyond its role",
            "The assistant was asked to do things it is forbidden to do, such as "
            "scoring a bid or saying which bidder should win.",
            groups.get("safety", []),
        ),
        (
            "Handling different file types and bad files",
            "The assistant was given Word files, plain text, a scanned document "
            "with no readable text, and a document too large to process.",
            groups.get("formats", []),
        ),
        (
            "Resisting hidden instructions",
            "A sentence was hidden inside a submission telling the assistant to "
            "ignore its rules and award the contract. A well-built system treats "
            "document contents as information to read, never as orders to obey.",
            groups.get("injection", []),
        ),
    ]


def _case_detail(results: Sequence, groups: Dict[str, List]) -> str:
    parts = ["<h2>Every test, one by one</h2>"]
    for title, _blurb, members in _group_specs(groups):
        if not members:
            continue
        parts.append(f"<h3>{_escape(title)}</h3>")
        for r in members:
            verdict = (
                '<span class="pass">Behaved as expected</span>'
                if r.passed
                else '<span class="fail">Did not behave as expected</span>'
            )
            timing = f"{r.seconds:.0f} seconds" if r.seconds >= 1 else "instant"
            parts.append(
                f'<div class="case">'
                f'<b>{_escape(r.id)}. {_escape(r.description)}</b><br/>'
                f'<span class="label">We expected:</span> {_escape(r.expected)}<br/>'
                f'<span class="label">What happened:</span> '
                f'<span class="quote">{_escape(r.actual)}</span><br/>'
                f'{verdict} &nbsp;&middot;&nbsp; <span class="label">took {timing}</span>'
                f'</div>'
            )
    return "".join(parts)


def _glossary(meta: ReportMeta) -> str:
    return f"""
<h2>Terms used in this report</h2>
<ul>
<li><b>Checklist item.</b> One document the submission is required to contain,
for example a tax clearance certificate.</li>
<li><b>Found / Not Found / Requires Human Review.</b> The three verdicts the
assistant can give. The third means it is unsure and a person must look.</li>
<li><b>Confidence.</b> A number from 0 to 1 the assistant reports alongside each
verdict, meant to express how sure it is. Below {meta.threshold}, the item is
sent for human review automatically.</li>
<li><b>Evidence snippet.</b> The exact words copied from the submission that the
assistant says prove an item is present. The system checks that this text really
appears in the document, so a quotation can never be invented.</li>
<li><b>Model.</b> The artificial intelligence component, here {_escape(meta.model)},
running privately on a local machine rather than on the internet, so no tender
data leaves the computer.</li>
<li><b>Context window.</b> How much text the model can read at once, here
{meta.context_tokens:,} units of text. Anything larger is refused outright rather
than being quietly cut short, because a cut-short document would make present
items look missing.</li>
<li><b>Prompt.</b> The written instructions given to the model telling it what
job to do and what it must never do.</li>
</ul>
"""


def _caveats(caveats: Sequence[str]) -> str:
    items = "".join(f"<li>{_escape(c)}</li>" for c in caveats)
    return f"<h2>Limitations of this testing</h2><ul>{items}</ul>"


def _group(results: Sequence) -> Dict[str, List]:
    buckets: Dict[str, List] = {
        "present": [], "absent": [], "safety": [], "formats": [], "injection": []
    }
    for r in results:
        cid = r.id
        if cid in ("EV-01", "EV-02", "EV-03", "EV-04"):
            buckets["present"].append(r)
        elif cid in ("EV-05", "EV-06", "EV-07", "EV-18"):
            buckets["absent"].append(r)
        elif cid in ("EV-08", "EV-09", "EV-10", "EV-11", "EV-13"):
            buckets["safety"].append(r)
        elif cid == "EV-14":
            buckets["injection"].append(r)
        else:
            buckets["formats"].append(r)
    return buckets


def build_html(results: Sequence, meta: ReportMeta, caveats: Sequence[str]) -> str:
    groups = _group(results)
    passed = sum(1 for r in results if r.passed)
    return (
        _cover(passed, len(results), meta)
        + _plain_english_summary(results, groups)
        + _case_detail(results, groups)
        + _glossary(meta)
        + _caveats(caveats)
    )


def write_pdf(
    results: Sequence, meta: ReportMeta, caveats: Sequence[str], destination: Path
) -> Path:
    """Render the results to a PDF at `destination` and return the path."""
    try:
        import pymupdf
    except ImportError:  # PyMuPDF older than 1.24 only exposes `fitz`
        import fitz as pymupdf

    destination.parent.mkdir(parents=True, exist_ok=True)
    story = pymupdf.Story(html=build_html(results, meta, caveats), user_css=CSS)
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
            f"Completeness Agent test results  |  Page {index} of {total}",
            fontname="helv",
            fontsize=7.5,
            color=(0.42, 0.42, 0.42),
        )
    document.saveIncr()
    document.close()


# ---------------------------------------------------------------------------
# Completeness report for one submission, as opposed to the evaluation table.
#
# This is what a reviewer gets when they run a check on their own document.
# Same plain-language principles: say what the report is and is not before
# showing findings, and never present a count as a score.
# ---------------------------------------------------------------------------

STATUS_EXPLANATION = {
    "Found": (
        "good",
        "Located in the submission. The quoted words below are copied directly "
        "from the document, and the page number is where they appear, so you can "
        "turn to that page and confirm it yourself.",
    ),
    "Not Found": (
        "bad",
        "The assistant could not locate this item. Treat this as a prompt to "
        "look yourself, not as a conclusion: the item may be present under "
        "wording the assistant did not recognise.",
    ),
    "Requires Human Review": (
        "note",
        "The assistant found something possibly relevant but was not confident "
        "enough to call it a match. A person must decide.",
    ),
}


def _check_cover(report, model: str, counts: Dict[str, int], pages: int) -> str:
    return f"""
<h1>Document Completeness Report</h1>
<p class="subtitle">Submission: {_escape(report.submission_id)}</p>
<p class="meta">Generated {_now()} &nbsp;|&nbsp; Assistant model: {_escape(model)}
&nbsp;|&nbsp; Submission length: {pages} page(s)</p>

<div class="headline">
<b>Of {len(report.verified_items)} required items:
{counts.get('Found', 0)} located,
{counts.get('Not Found', 0)} not located,
{counts.get('Requires Human Review', 0)} need a person to decide.</b>
</div>

<div class="note"><b>What this report is not.</b> This is a completeness check
only. It records whether required documents could be located in the submission.
It is not a score, not a ranking, not a legal opinion, not a judgement of
eligibility, and not a recommendation to accept or reject this bid. The counts
above are counts of documents located, nothing more. All procurement decisions
remain with authorised human officers.</div>

<h2>How to use this report</h2>
<p>Work through the items below. For anything marked as located, the page number
and the quoted words let you verify it in seconds. For anything not located, or
flagged for review, check the submission yourself before drawing a conclusion,
because the assistant can miss an item that is worded unusually.</p>
"""


def _check_items(report) -> str:
    parts = ["<h2>Item by item</h2>"]
    for item in report.verified_items:
        status = item.status.value
        css, explanation = STATUS_EXPLANATION.get(status, ("note", ""))
        location = (
            f"page {item.page_number}" if item.page_number else "no page recorded"
        )
        block = [
            f'<div class="{css}">',
            f"<b>{_escape(item.checklist_item_id)} &nbsp; {_escape(item.clause_title)}</b><br/>",
            f"<b>{_escape(status)}</b> &middot; {_escape(location)} &middot; ",
            f"confidence {item.confidence_score:.2f}<br/>",
            f"{explanation}",
        ]
        if item.extracted_snippet:
            snippet = item.extracted_snippet.replace("\n", " ")
            block.append(
                f'<br/><span class="label">Quoted from the submission:</span><br/>'
                f'<span class="quote">{_escape(snippet)}</span>'
            )
        block.append("</div>")
        parts.append("".join(block))
    return "".join(parts)


def _check_next_steps(report) -> str:
    missing = report.missing_items
    review = report.review_items
    lines = []
    if missing:
        lines.append(
            f"<li>Check the submission yourself for: "
            f"{_escape(', '.join(missing))}. The assistant did not locate these.</li>"
        )
    if review:
        lines.append(
            f"<li>Decide on: {_escape(', '.join(review))}. "
            f"The assistant was unsure about these.</li>"
        )
    if not lines:
        lines.append(
            "<li>Every required item was located. Spot-check a sample against the "
            "page numbers given before relying on this.</li>"
        )
    return f"<h2>What to do next</h2><ul>{''.join(lines)}</ul>"


def write_check_pdf(report, model: str, page_count: int, destination: Path) -> Path:
    """Render a single submission's completeness report as a readable PDF."""
    try:
        import pymupdf
    except ImportError:  # PyMuPDF older than 1.24 only exposes `fitz`
        import fitz as pymupdf

    counts: Dict[str, int] = {}
    for item in report.verified_items:
        counts[item.status.value] = counts.get(item.status.value, 0) + 1

    html_body = (
        _check_cover(report, model, counts, page_count)
        + _check_items(report)
        + _check_next_steps(report)
    )

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
