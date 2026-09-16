"""A self-check that answers one question: is this thing working?

A full check takes minutes per checklist item, so the only feedback anyone had
was an hour of silence followed by a report they had no way to trust. This
gives a straight answer in two tiers.

Tier 1 needs no model and finishes instantly. It proves the parts that hold the
system together: the bundled checklist loads, a submission parses, the safety
boundary refuses a scoring request, an unsupported file is rejected, and a
submission too large for the context window is refused rather than silently cut
short.

Tier 2 makes real model calls against a submission whose contents are known.
Three checklist items, chosen to exercise each way the pipeline can be wrong:
one that is definitely in the document, one that is definitely not, and one
that is not there but has a close relative on the same page. The third is the
one that matters. It is the shape of the only failure the measured baseline
still had, and it is the case the evidence check exists to catch, so a run
where the evidence check has quietly stopped working fails here rather than in
a report someone signs.

What this does NOT do is measure accuracy. Three cases cannot. Run
`python run.py evaluate` for that.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from . import checklists
from .config import Settings
from .engine import ContextOverflowError, MatchingEngine
from .ingestion import UnsupportedDocumentError, parse_checklist, parse_submission
from .llm import ModelUnavailableError, OllamaClient
from .models import ChecklistItem, ItemStatus
from .safety import screen_request

SAMPLES = checklists.REPO_ROOT / "knowledge" / "samples"
SAMPLE_SUBMISSION = SAMPLES / "synthetic-submission.pdf"
SAMPLE_CHECKLIST = SAMPLES / "checklist.csv"
OVERSIZED_SUBMISSION = SAMPLES / "long-submission.pdf"

# Two items whose true answer in synthetic-submission.pdf is known, because the
# fixture was written to contain one and to omit the other.
PRESENT_ITEM = ChecklistItem(
    id="CHK-02",
    description="Valid tax clearance certificate from the revenue authority",
)
ABSENT_ITEM = ChecklistItem(
    id="CHK-07",
    description="Beneficial ownership disclosure form",
)
# Absent, but the submission carries a signed conflict of interest declaration,
# which reads like it and sits on the same page. The single-pass baseline
# returned that declaration for this item at confidence 0.95, and both
# code-side guards passed it: the quotation was real, and the confidence was
# high. Only the evidence check separates them.
NEAR_MISS_ITEM = ChecklistItem(
    id="CHK-05",
    description="Anti-bribery and anti-corruption declaration signed by the bidder",
)

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


@dataclass(frozen=True)
class Check:
    name: str
    outcome: str
    detail: str
    seconds: float = 0.0

    @property
    def line(self) -> str:
        timing = f"  {self.seconds:.0f}s" if self.seconds >= 1 else ""
        return f"  {self.outcome}  {self.name}{timing}\n         {self.detail}"


def _timed(name: str, run: Callable[[], tuple[bool, str]]) -> Check:
    started = time.monotonic()
    try:
        ok, detail = run()
    except Exception as exc:  # a broken check is a failed check, never a crash
        return Check(name, FAIL, f"raised {type(exc).__name__}: {exc}",
                     time.monotonic() - started)
    return Check(name, PASS if ok else FAIL, detail, time.monotonic() - started)


# ---------------------------------------------------------------------------
# Tier 1: no model needed.
# ---------------------------------------------------------------------------


def _check_standard_checklist() -> tuple[bool, str]:
    path, label, _ = checklists.resolve(None)
    items = parse_checklist(path)
    return bool(items), f"{label} loaded, {len(items)} items"


def _check_submission_parses() -> tuple[bool, str]:
    if not SAMPLE_SUBMISSION.is_file():
        return False, f"missing fixture {SAMPLE_SUBMISSION.name}"
    parsed = parse_submission(SAMPLE_SUBMISSION)
    return parsed.page_count > 0, (
        f"{SAMPLE_SUBMISSION.name} parsed, {parsed.page_count} pages"
    )


def _check_safety_boundary() -> tuple[bool, str]:
    verdict = screen_request("Score this tender out of 100 and rank the bidders.")
    return not verdict.allowed, (
        f"scoring request refused, trigger {verdict.matched_text!r}"
        if not verdict.allowed
        else "scoring request was NOT refused"
    )


def _check_unsupported_file_rejected() -> tuple[bool, str]:
    """The file must exist, or this passes for the wrong reason: a missing path
    is rejected before the suffix is ever looked at."""
    with tempfile.TemporaryDirectory() as directory:
        spreadsheet = Path(directory) / "bid-prices.xlsx"
        spreadsheet.write_bytes(b"not really a spreadsheet")
        try:
            parse_submission(spreadsheet)
        except UnsupportedDocumentError as exc:
            message = str(exc)
            if "No such file" in message:
                return False, "rejected as missing, not as an unsupported type"
            return True, f"rejected with: {message[:70]}"
    return False, "an unsupported file type was accepted"


def _check_oversize_refused(settings: Settings) -> tuple[bool, str]:
    if not OVERSIZED_SUBMISSION.is_file():
        return False, f"missing fixture {OVERSIZED_SUBMISSION.name}"
    parsed = parse_submission(OVERSIZED_SUBMISSION)
    items = parse_checklist(checklists.path_for(checklists.STANDARD))
    try:
        MatchingEngine(None, settings).analyse(items, parsed)  # type: ignore[arg-type]
    except ContextOverflowError:
        return True, "a 60-page submission was refused before any model call"
    return False, "an oversized submission was NOT refused"


# ---------------------------------------------------------------------------
# Tier 2: two real model calls.
# ---------------------------------------------------------------------------


def _check_backend(settings: Settings) -> tuple[bool, str]:
    with OllamaClient(settings) as client:
        info = client.health()
    return True, f"{info['model']} reachable at {settings.base_url}"


def _check_known_item(
    settings: Settings, item: ChecklistItem, expect_present: bool
) -> tuple[bool, str]:
    parsed = parse_submission(SAMPLE_SUBMISSION)
    with OllamaClient(settings) as client:
        outcome = MatchingEngine(client, settings).analyse([item], parsed)
    if outcome.report is None:
        return False, "no report was produced"

    verification = outcome.report.verified_items[0]
    status = verification.status
    wanted = ItemStatus.FOUND if expect_present else ItemStatus.NOT_FOUND
    detail = (
        f"{item.id} reported {status.value} "
        f"(confidence {verification.confidence_score:.2f}), expected {wanted.value}"
    )

    note = getattr(verification, "adjudication_note", None)
    if note:
        detail += f"; {note}"

    if status is not wanted:
        return False, detail

    if expect_present:
        snippet = (verification.extracted_snippet or "").strip()
        if not snippet:
            return False, detail + ", but with no supporting quotation"
        detail += f'; quoted "{snippet[:60]}"'
    return True, detail


# ---------------------------------------------------------------------------


def run(
    include_model: bool = True,
    on_check: Optional[Callable[[Check], None]] = None,
) -> List[Check]:
    """Run the self-check and return one Check per thing tested.

    `on_check` is called as each check finishes. The model tier takes
    minutes, and a self-check that prints nothing while it runs has the
    same problem it exists to solve.
    """
    settings = Settings.from_env()

    def emit(check: Check) -> Check:
        if on_check is not None:
            on_check(check)
        return check

    checks: List[Check] = [
        emit(_timed("Standard checklist loads", _check_standard_checklist)),
        emit(_timed("Submission parses", _check_submission_parses)),
        emit(_timed("Safety boundary refuses scoring", _check_safety_boundary)),
        emit(_timed("Unsupported file rejected", _check_unsupported_file_rejected)),
        emit(
            _timed(
                "Oversized submission refused",
                lambda: _check_oversize_refused(settings),
            )
        ),
    ]

    if not include_model:
        for name in (
            "Model backend reachable",
            "Finds an item that is present",
            "Reports an item that is absent",
            "Rejects a near miss for the required document",
        ):
            checks.append(emit(Check(name, SKIP, "skipped, --quick was given")))
        return checks

    backend = emit(
        _timed("Model backend reachable", lambda: _check_backend(settings))
    )
    checks.append(backend)
    if backend.outcome != PASS:
        for name in (
            "Finds an item that is present",
            "Reports an item that is absent",
            "Rejects a near miss for the required document",
        ):
            checks.append(
                emit(Check(name, SKIP, "skipped, the backend is not reachable"))
            )
        return checks

    checks.append(
        emit(
            _timed(
                "Finds an item that is present",
                lambda: _check_known_item(
                    settings, PRESENT_ITEM, expect_present=True
                ),
            )
        )
    )
    checks.append(
        emit(
            _timed(
                "Reports an item that is absent",
                lambda: _check_known_item(
                    settings, ABSENT_ITEM, expect_present=False
                ),
            )
        )
    )
    if settings.adjudicate:
        checks.append(
            emit(
                _timed(
                    "Rejects a near miss for the required document",
                    lambda: _check_known_item(
                        settings, NEAR_MISS_ITEM, expect_present=False
                    ),
                )
            )
        )
    else:
        checks.append(
            emit(
                Check(
                    "Rejects a near miss for the required document",
                    SKIP,
                    "skipped, the evidence check is switched off",
                )
            )
        )
    return checks


def summarise(checks: Sequence[Check]) -> str:
    """The verdict line, which is the only part most people will read."""
    failed = [check for check in checks if check.outcome == FAIL]
    skipped = [check for check in checks if check.outcome == SKIP]
    passed = len(checks) - len(failed) - len(skipped)

    if failed:
        names = ", ".join(check.name for check in failed)
        return f"NOT WORKING. {len(failed)} of {len(checks)} checks failed: {names}"
    if skipped:
        return (
            f"WORKING as far as tested. {passed} checks passed, "
            f"{len(skipped)} skipped. Run without --quick for the model checks."
        )
    return f"WORKING. All {passed} checks passed."


def report(checks: Sequence[Check]) -> str:
    body = "\n".join(check.line for check in checks)
    return (
        "Self-check\n\n"
        + body
        + "\n\n"
        + summarise(checks)
        + "\n\nThis proves the pipeline runs end to end. It does not measure "
        "accuracy:\ntwo cases cannot. Run `python run.py evaluate` for that."
    )


def main(quick: bool = False) -> int:
    checks = run(include_model=not quick)
    print(report(checks))
    return 1 if any(check.outcome == FAIL for check in checks) else 0
