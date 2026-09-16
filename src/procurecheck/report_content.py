"""What the completeness check report and the evaluation report say.

Layout lives in report_layout.py; this module decides content and order only.
Both reports are rendered to PDF and to Word from the same blocks.

The check report answers, for every checklist item, the question a reviewer
asked of the first real report: what exactly happened, as opposed to what had
to happen? Each item states what the submission had to contain, what the
system did stage by stage, the evidence, what the status does and does not
establish, and what the procurement officer does next.

The evaluation report does the same for test cases: the expected behaviour,
fixed before the run, the actual behaviour in full, and an observation stating
the difference between the two in words rather than a bare Pass or Fail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from .explain import STATUS_MEANING, explain
from .models import COMPLETENESS_DISCLAIMER, ItemStatus
from .report_layout import PROJECT, TONE_BAD, TONE_GOOD, TONE_WARN, Block, Cell, ReportBuilder

STATUS_TONE: Dict[ItemStatus, str] = {
    ItemStatus.FOUND: TONE_GOOD,
    ItemStatus.NOT_FOUND: TONE_BAD,
    ItemStatus.REQUIRES_HUMAN_REVIEW: TONE_WARN,
}

# When nearly everything is Not Found, the likeliest explanation is the wrong
# file or the wrong checklist, not a bidder who filed almost nothing. The first
# real run was exactly that: a test-case document checked as though it were a
# bid.
MOSTLY_ABSENT_SHARE = 0.8


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%d %B %Y")


def _plural(count: int, singular: str, plural: Optional[str] = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


# ---------------------------------------------------------------------------
# Completeness check report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckMeta:
    """Everything about a check run that the report states."""

    submission_name: str
    model: str
    page_count: int
    checklist_label: str = ""
    caveat: str = ""
    pipeline_label: str = ""
    threshold: Optional[float] = None
    evidence_check: Optional[bool] = None
    generated: str = ""


def _check_introduction(builder: ReportBuilder, report, meta: CheckMeta) -> None:
    total = len(report.verified_items)
    checklist = meta.checklist_label or "the supplied checklist"
    builder.section("Introduction")
    builder.paragraph(
        f"This report records a completeness check of the submission "
        f'"{meta.submission_name}". The submission was checked against {checklist}, '
        f"which lists {_plural(total, 'required document')}. The check was run on "
        f"{meta.generated or _today()} using the {meta.model} language model."
    )
    builder.paragraph(
        "A completeness check establishes only whether each required document could "
        "be located. It does not judge the quality, validity or legal effect of any "
        "document, and it does not score, rank or recommend the bid."
    )
    if meta.caveat:
        builder.paragraph(meta.caveat, label="Checklist used.")

    builder.subsection("How each item was checked")
    steps = [
        f"The model was given {'the single page' if meta.page_count == 1 else f'all {meta.page_count} pages'} "
        "of the submission and one checklist item at a time.",
        "It either quoted the passage it judged to be the document, with a page "
        "number, or reported that no passage is the document.",
        "Any quotation was then searched for in the submission text. A quotation "
        "that does not appear word for word is not accepted as evidence.",
    ]
    if meta.evidence_check:
        steps.append(
            "An accepted quotation was shown to the model a second time, with the "
            "rest of the submission withheld. This evidence check asks whether the "
            "passage is the required document or a related one."
        )
    if meta.threshold is not None:
        steps.append(
            f"A match with confidence below {meta.threshold:.2f} was not reported as "
            "Found. It was passed to a person instead."
        )
    builder.bullets(steps)

    number = builder.next_table
    builder.paragraph(
        f"Table {number} defines the three statuses used in this report. Confidence "
        "is the model's own estimate, from 0.00 to 1.00, of how closely a passage "
        "matches the requirement. It is not a score of the bid."
    )
    builder.table(
        "Meaning of each status",
        ["Status", "What it means"],
        [
            [Cell(status.value, STATUS_TONE[status]), STATUS_MEANING[status]]
            for status in ItemStatus
        ],
        widths=(1, 3.2),
    )

    details = [
        ("Submission", meta.submission_name),
        ("Pages read", str(meta.page_count)),
        ("Checklist", checklist),
        ("Required documents", str(total)),
        ("Model", meta.model),
    ]
    if meta.pipeline_label:
        details.append(("Prompt pipeline", meta.pipeline_label))
    if meta.evidence_check is not None:
        details.append(("Evidence check", "On" if meta.evidence_check else "Off"))
    if meta.threshold is not None:
        details.append(("Review threshold", f"{meta.threshold:.2f}"))
    number = builder.next_table
    builder.paragraph(f"Table {number} records the settings of this run.")
    builder.table("Settings of the check", ["Setting", "Value"], details, widths=(1, 2.4))


def _check_summary(builder: ReportBuilder, report) -> None:
    counts = {status: 0 for status in ItemStatus}
    for item in report.verified_items:
        counts[item.status] += 1
    total = len(report.verified_items)

    builder.section("Summary of findings")
    builder.paragraph(
        f"Of the {_plural(total, 'required document')}, {counts[ItemStatus.FOUND]} "
        f"{'was' if counts[ItemStatus.FOUND] == 1 else 'were'} found, "
        f"{counts[ItemStatus.NOT_FOUND]} {'was' if counts[ItemStatus.NOT_FOUND] == 1 else 'were'} "
        f"not found, and {counts[ItemStatus.REQUIRES_HUMAN_REVIEW]} "
        f"{'needs' if counts[ItemStatus.REQUIRES_HUMAN_REVIEW] == 1 else 'need'} a "
        "person to decide."
    )
    if total and counts[ItemStatus.NOT_FOUND] / total >= MOSTLY_ABSENT_SHARE:
        builder.paragraph(
            "Most required documents were not found. Before treating the bid as "
            "incomplete, confirm that the correct file was checked, and that the "
            "checklist matches the bidding document for this tender.",
            label="Check the inputs first.",
        )

    number = builder.next_table
    builder.paragraph(
        f"Table {number} lists every item with its status. Section 3 explains each "
        "item in full, including what the system did and why."
    )
    rows = []
    for item in report.verified_items:
        rows.append(
            [
                Cell(item.checklist_item_id, bold=True),
                item.clause_title,
                Cell(item.status.value, STATUS_TONE[item.status]),
                str(item.page_number) if item.page_number else "None",
                f"{item.confidence_score:.2f}",
            ]
        )
    builder.table(
        "Status of every required document",
        ["Item", "Required document", "Status", "Page", "Confidence"],
        rows,
        widths=(0.8, 3.2, 1.2, 0.6, 0.9),
    )


def _check_items(builder: ReportBuilder, report, meta: CheckMeta) -> None:
    builder.section("Item-by-item findings")
    builder.paragraph(
        "Each item below states what the submission had to contain, what the system "
        "actually did, the evidence it relied on, and what the result means for the "
        "procurement officer."
    )
    for item in report.verified_items:
        story = explain(
            item,
            pages_read=meta.page_count,
            threshold=meta.threshold,
            evidence_check=meta.evidence_check,
        )
        builder.subsection(f"{item.checklist_item_id}: {item.clause_title}")
        builder.paragraph(story.required, label="What had to be present.")
        builder.paragraph(story.happened, label="What the system did.")
        builder.paragraph(story.evidence, label="Evidence.")
        builder.paragraph(
            f"{item.status.value}, confidence {item.confidence_score:.2f}. {story.meaning}",
            label="Result.",
        )
        builder.paragraph(story.next_step, label="Next step.")


def _check_actions(builder: ReportBuilder, report) -> None:
    builder.section("Actions for the procurement officer")
    by_status: Dict[ItemStatus, List[str]] = {status: [] for status in ItemStatus}
    for item in report.verified_items:
        by_status[item.status].append(item.checklist_item_id)

    actions = []
    if by_status[ItemStatus.REQUIRES_HUMAN_REVIEW]:
        actions.append(
            "Decide each item the system could not settle, and record it as Found or "
            "Not Found: " + ", ".join(by_status[ItemStatus.REQUIRES_HUMAN_REVIEW]) + "."
        )
    if by_status[ItemStatus.NOT_FOUND]:
        actions.append(
            "Search the submission by hand for each item not found, and confirm "
            "whether it is truly absent: " + ", ".join(by_status[ItemStatus.NOT_FOUND]) + "."
        )
    if by_status[ItemStatus.FOUND]:
        actions.append(
            "Spot-check the items found against the quoted pages: "
            + ", ".join(by_status[ItemStatus.FOUND]) + "."
        )
    builder.paragraph(
        "The actions below follow from the findings. Section 3 gives the page to "
        "start from where one is known."
    )
    builder.bullets(actions)

    builder.section("Scope of this report")
    builder.paragraph(COMPLETENESS_DISCLAIMER)


def check_report_blocks(report, meta: CheckMeta) -> List[Block]:
    builder = ReportBuilder()
    builder.title_page(
        "Completeness Check Report",
        meta.submission_name,
        meta.generated or _today(),
    )
    _check_introduction(builder, report, meta)
    _check_summary(builder, report)
    _check_items(builder, report, meta)
    _check_actions(builder, report)
    return builder.blocks


# ---------------------------------------------------------------------------
# Evaluation report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvaluationMeta:
    """What the evaluation run was, stated once in the methodology."""

    model: str
    prompt_version: str
    strategy: str
    context_tokens: int
    threshold: float
    submission_note: str
    title: str = "Prompt Evaluation Report"
    subtitle: str = "Expected against actual behaviour"
    source: str = ""


AREA_TITLES: Sequence[Tuple[str, str]] = (
    ("present", "Finding documents that are present"),
    ("absent", "Noticing documents that are missing"),
    ("review", "Passing uncertain matches to a person"),
    ("checklist", "Reading the checklist"),
    ("scope", "Staying within the supplied checklist"),
    ("safety", "Refusing to go beyond its role"),
    ("formats", "Handling different file types"),
    ("injection", "Resisting hidden instructions"),
)


def area_of(result) -> str:
    """The area a case tests. Named on the result, or inferred for EV cases."""
    named = getattr(result, "area", "")
    if named:
        return named
    if result.id in ("EV-01", "EV-02", "EV-03", "EV-04"):
        return "present"
    if result.id in ("EV-05", "EV-06", "EV-07", "EV-18"):
        return "absent"
    if result.id in ("EV-08", "EV-09", "EV-10", "EV-11", "EV-13"):
        return "safety"
    if result.id == "EV-14":
        return "injection"
    return "formats"


def _area_title(key: str) -> str:
    return dict(AREA_TITLES).get(key, key)


def _verdict(passed: bool) -> Cell:
    return Cell("Pass" if passed else "Fail", TONE_GOOD if passed else TONE_BAD)


def _lines(text: str) -> List[str]:
    return [line.strip() for line in str(text).split("\n") if line.strip()]


def _evaluation_methodology(builder: ReportBuilder, results, meta: EvaluationMeta) -> None:
    builder.section("Introduction and objectives")
    source = (
        f" The cases were taken from {meta.source}." if meta.source else ""
    )
    builder.paragraph(
        f"This report records an evaluation of the {PROJECT} against "
        f"{_plural(len(results), 'test case')}.{source} The objective was to "
        "determine, case by case, whether the actual behaviour of the system met "
        "the behaviour expected of it."
    )
    builder.paragraph(
        "Each expected behaviour was written before the case was run and was not "
        "changed afterwards. For every case the report states the expected "
        "behaviour, the actual behaviour in full, and an observation describing any "
        "difference between the two."
    )

    builder.section("Methodology")
    builder.paragraph(
        "Each case was run once through the application, not through the model "
        "alone, so the deterministic checks were exercised as well. A case was "
        "marked Pass only when every part of the expected behaviour was met."
    )
    builder.paragraph(meta.submission_note, label="Documents tested.")
    number = builder.next_table
    builder.paragraph(f"Table {number} records the configuration under which the cases were run.")
    passed = sum(1 for r in results if r.passed)
    builder.table(
        "Configuration of the evaluated run",
        ["Setting", "Value"],
        [
            ("Model", meta.model),
            ("Prompt pipeline", meta.prompt_version),
            ("Matching method", meta.strategy),
            ("Human review threshold", f"{meta.threshold:.2f}"),
            ("Context window", f"{meta.context_tokens:,} tokens"),
            ("Cases run", str(len(results))),
            ("Cases meeting expectation", f"{passed} of {len(results)}"),
            ("Date", _today()),
        ],
        widths=(1, 2.4),
    )


def _evaluation_results(builder: ReportBuilder, results) -> None:
    passed = sum(1 for r in results if r.passed)
    failed = [r for r in results if not r.passed]
    builder.section("Results")
    summary = f"{passed} of {len(results)} cases behaved as expected."
    if failed:
        summary += " The cases that did not were " + ", ".join(r.id for r in failed) + "."
    builder.paragraph(summary)

    groups: Dict[str, List] = {}
    for result in results:
        groups.setdefault(area_of(result), []).append(result)
    rows = []
    for key, title in AREA_TITLES:
        members = groups.pop(key, [])
        if members:
            ok = sum(1 for r in members if r.passed)
            rows.append([title, Cell(f"{ok} of {len(members)}", TONE_GOOD if ok == len(members) else TONE_BAD)])
    for key, members in groups.items():
        ok = sum(1 for r in members if r.passed)
        rows.append([_area_title(key), Cell(f"{ok} of {len(members)}", TONE_GOOD if ok == len(members) else TONE_BAD)])

    number = builder.next_table
    builder.paragraph(f"Table {number} groups the cases by the area of behaviour they tested.")
    builder.table("Cases meeting expectation, by area", ["Area tested", "As expected"], rows, widths=(3, 1))

    number = builder.next_table
    builder.paragraph(
        f"Table {number} summarises every case. Section 4 gives the full expected and "
        "actual behaviour for each one."
    )
    builder.table(
        "Result of every case",
        ["Case", "Area tested", "Scenario", "Result"],
        [
            [
                Cell(r.id, bold=True),
                _area_title(area_of(r)),
                getattr(r, "title", "") or r.description,
                _verdict(r.passed),
            ]
            for r in results
        ],
        widths=(0.8, 1.6, 3.4, 0.7),
    )


def _evaluation_cases(builder: ReportBuilder, results) -> None:
    builder.section("Case-by-case results")
    builder.paragraph(
        "Each case below sets the expected behaviour beside what the system "
        "actually did. The observation states what the difference, if any, means."
    )
    for r in results:
        title = getattr(r, "title", "") or _area_title(area_of(r))
        builder.subsection(f"{r.id}: {title}")
        based_on = getattr(r, "based_on", "")
        if based_on:
            builder.paragraph(based_on, label="Based on.")
        if r.acceptance_criteria:
            builder.paragraph(r.acceptance_criteria, label="Acceptance criteria.")
        objective = getattr(r, "objective", "")
        if objective:
            builder.paragraph(objective, label="Objective.")
        if r.description and r.description != title:
            builder.paragraph(r.description, label="Scenario.")
        if r.submission:
            builder.paragraph(r.submission, label="Document tested.")
        inputs = _lines(getattr(r, "inputs", ""))
        if inputs:
            builder.paragraph("The case supplied the following input.", label="Input.")
            builder.bullets(inputs)
        builder.paragraph(r.expected, label="Expected behaviour.")
        actual = _lines(r.actual)
        if len(actual) > 1:
            builder.paragraph(actual[0], label="Actual behaviour.")
            builder.bullets(actual[1:])
        else:
            builder.paragraph(r.actual, label="Actual behaviour.")
        builder.paragraph("Pass" if r.passed else "Fail", label="Result.")
        observation = getattr(r, "observation", "")
        if observation:
            builder.paragraph(observation, label="Observation.")


def evaluation_report_blocks(results, meta: EvaluationMeta, caveats: Sequence[str]) -> List[Block]:
    builder = ReportBuilder()
    builder.title_page(meta.title, meta.subtitle, _today())
    _evaluation_methodology(builder, results, meta)
    _evaluation_results(builder, results)
    _evaluation_cases(builder, results)

    failed = [r for r in results if not r.passed]
    if failed:
        builder.section("Discussion of failures")
        builder.paragraph(
            "The cases below did not meet expectation. Each is described in full in "
            "Section 4."
        )
        builder.bullets(
            [
                f"{r.id}. {getattr(r, 'observation', '') or r.actual}"
                for r in failed
            ]
        )

    builder.section("Limitations")
    builder.paragraph("The results above are subject to the following limitations.")
    builder.bullets(list(caveats))
    return builder.blocks

