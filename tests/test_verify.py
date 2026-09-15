"""Tests for the self-check and the progress reporting.

The self-check is what someone runs when they want to know whether the system
works, so the thing that matters most is that it cannot report PASS when
something is broken. Each test here breaks one thing and asserts the verdict
changes.
"""

from __future__ import annotations

import pytest

from procurecheck import verify
from procurecheck.engine import ItemProgress
from procurecheck.models import ChecklistItem, ClauseVerification, ItemStatus


def _check(name: str, outcome: str) -> verify.Check:
    return verify.Check(name=name, outcome=outcome, detail="detail")


def test_quick_run_covers_every_part_that_needs_no_model():
    checks = verify.run(include_model=False)

    instant = [check for check in checks if check.outcome != verify.SKIP]
    assert len(instant) == 5
    assert all(check.outcome == verify.PASS for check in instant), [
        (check.name, check.detail) for check in instant if check.outcome != verify.PASS
    ]


def test_quick_run_skips_rather_than_silently_passing_the_model_checks():
    checks = verify.run(include_model=False)
    skipped = [check for check in checks if check.outcome == verify.SKIP]

    assert len(skipped) == 3
    assert all("skipped" in check.detail for check in skipped)


def test_a_check_that_raises_is_reported_as_a_failure_not_a_crash():
    def explode() -> tuple[bool, str]:
        raise RuntimeError("backend exploded")

    check = verify._timed("Exploding check", explode)

    assert check.outcome == verify.FAIL
    assert "RuntimeError" in check.detail


def test_verdict_says_not_working_when_anything_failed():
    verdict = verify.summarise([_check("A", verify.PASS), _check("B", verify.FAIL)])

    assert verdict.startswith("NOT WORKING")
    assert "B" in verdict


def test_verdict_is_qualified_when_checks_were_skipped():
    verdict = verify.summarise([_check("A", verify.PASS), _check("B", verify.SKIP)])

    assert verdict.startswith("WORKING as far as tested")


def test_verdict_is_unqualified_only_when_everything_ran_and_passed():
    verdict = verify.summarise([_check("A", verify.PASS), _check("B", verify.PASS)])

    assert verdict == "WORKING. All 2 checks passed."


def test_report_refuses_to_claim_it_measured_accuracy():
    report = verify.report(verify.run(include_model=False))

    assert "does not measure accuracy" in report
    assert "run.py evaluate" in report


def test_unsupported_file_check_fails_if_it_only_proved_the_file_was_missing(
    monkeypatch,
):
    """The original version of this check passed against a path that did not
    exist, which proves nothing about the suffix. Guard the guard."""

    def reject_as_missing(path):
        raise verify.UnsupportedDocumentError(f"No such file: {path}")

    monkeypatch.setattr(verify, "parse_submission", reject_as_missing)
    ok, detail = verify._check_unsupported_file_rejected()

    assert ok is False
    assert "not as an unsupported type" in detail


def test_progress_line_is_one_line_and_names_the_item_and_verdict():
    progress = ItemProgress(
        index=3,
        total=22,
        item=ChecklistItem(id="STD-03", description="Trading licence for the year"),
        verification=ClauseVerification(
            checklist_item_id="STD-03",
            clause_title="Trading licence",
            is_present=True,
            page_number=4,
            extracted_snippet="A trading licence is attached.",
            confidence_score=0.95,
            requires_human_review=False,
        ),
        seconds=12.4,
    )

    assert "\n" not in progress.line
    assert progress.line.startswith("[3/22] STD-03 Found")
    assert "p4" in progress.line
    assert "12s" in progress.line


def test_progress_line_reports_a_review_verdict_without_a_page():
    progress = ItemProgress(
        index=1,
        total=1,
        item=ChecklistItem(id="STD-20", description="Professional indemnity insurance"),
        verification=ClauseVerification(
            checklist_item_id="STD-20",
            clause_title="Insurance",
            is_present=True,
            page_number=None,
            extracted_snippet=None,
            confidence_score=0.4,
            requires_human_review=True,
        ),
        seconds=0.2,
    )

    assert ItemStatus.REQUIRES_HUMAN_REVIEW.value in progress.line
    assert " - " in progress.line


def test_engine_reports_progress_for_every_item(monkeypatch):
    """A run without progress output is indistinguishable from a hang, so the
    callback must fire once per item, in order."""
    from procurecheck.config import Settings
    from procurecheck.engine import MatchingEngine
    from procurecheck.ingestion import parse_submission

    submission = parse_submission(verify.SAMPLE_SUBMISSION)
    items = [
        ChecklistItem(id=f"STD-{n:02d}", description=f"Required document {n}")
        for n in range(1, 4)
    ]

    class StubClient:
        def complete_structured(self, system, user, schema):
            return ClauseVerification(
                checklist_item_id="ignored",
                clause_title="ignored",
                is_present=False,
                confidence_score=0.0,
                requires_human_review=False,
            )

    seen: list[ItemProgress] = []
    engine = MatchingEngine(StubClient(), Settings.from_env())  # type: ignore[arg-type]
    engine.analyse(items, submission, on_progress=seen.append)

    assert [progress.index for progress in seen] == [1, 2, 3]
    assert all(progress.total == 3 for progress in seen)
    assert [progress.item.id for progress in seen] == [item.id for item in items]


def test_engine_still_reports_progress_when_an_item_fails_to_parse(monkeypatch):
    """A model answer that cannot be parsed must not make the run go quiet."""
    from procurecheck.config import Settings
    from procurecheck.engine import MatchingEngine
    from procurecheck.ingestion import parse_submission
    from procurecheck.llm import StructuredOutputError

    submission = parse_submission(verify.SAMPLE_SUBMISSION)
    items = [ChecklistItem(id="STD-01", description="Required document 1")]

    class BrokenClient:
        def complete_structured(self, system, user, schema):
            raise StructuredOutputError("unparseable")

    seen: list[ItemProgress] = []
    engine = MatchingEngine(BrokenClient(), Settings.from_env())  # type: ignore[arg-type]
    engine.analyse(items, submission, on_progress=seen.append)

    assert len(seen) == 1
    assert seen[0].verification.status is ItemStatus.REQUIRES_HUMAN_REVIEW


def test_analyse_without_a_callback_still_works():
    """The callback is optional; every existing caller passes nothing."""
    from procurecheck.config import Settings
    from procurecheck.engine import MatchingEngine
    from procurecheck.ingestion import parse_submission

    submission = parse_submission(verify.SAMPLE_SUBMISSION)

    class StubClient:
        def complete_structured(self, system, user, schema):
            return ClauseVerification(
                checklist_item_id="ignored",
                clause_title="ignored",
                is_present=False,
                confidence_score=0.0,
                requires_human_review=False,
            )

    engine = MatchingEngine(StubClient(), Settings.from_env())  # type: ignore[arg-type]
    outcome = engine.analyse(
        [ChecklistItem(id="STD-01", description="Required document 1")], submission
    )

    assert outcome.report is not None
