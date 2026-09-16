"""Matching and Classification Engine.

The LLM-backed component from the Architecture and Context Diagram (Sec. 4).
It interprets each checklist requirement, searches the parsed submission for
satisfying text, and classifies each item as Found, Not Found, or Requires
Human Review with an evidence location (User Stories AC3, AC4, AC10).

Strategy note for team review: the default is one model call per checklist
item. Prompt Specification v1.0 Sec. 4 describes a single call carrying the
whole checklist, which is available via PROCURECHECK_STRATEGY=batch. Per item
is the default because an 8B model holds evidence discipline far better over
one requirement than over a dozen at once, and because a malformed answer then
costs one item rather than the whole report. Both paths use the same schema,
constraints and refusal behaviour.

Two model passes, not one. The first pass reads the submission and proposes an
answer. Every item it claims to have found then goes to a second pass that is
shown the requirement and the quoted passage ONLY, and asked whether they are
the same document (see prompts.PROMPT_ADJUDICATOR_V1_0).

That second pass is here because of what the baseline measured. Both surviving
failures, EV-05 and EV-07, are false positives where the first pass quoted real
text from the submission that belongs to a different document: a
conflict-of-interest declaration offered as an anti-bribery declaration, a
certificate of registration offered as a certificate of non-blacklisting. The
two code-side guards cannot catch either. Grounding only asks whether the
quotation is real, and it was. The confidence threshold only asks what the
model claimed, and it claimed 0.95 both times.

Nothing deterministic can tell an anti-bribery declaration from a
conflict-of-interest declaration; that judgement is the work. So it stays with
the model, and what changes is the question the model is asked. Searching a
document always offers a nearest match, and a model asked to search and to
judge in one call judges in favour of what it has just found. Withhold the
document and the task stops being retrieval: two names, one question, no answer
of its own to defend.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Callable, Final, List, Optional, Sequence, Set

from .config import STRATEGY_BATCH, Settings
from .ingestion.submission import ParsedSubmission
from .llm import OllamaClient, StructuredOutputError
from .models import (
    AdjudicatedClause,
    ChecklistItem,
    ClauseVerification,
    CompletenessReport,
    EvidenceAdjudication,
    RefusalResponse,
)
from .prompts import (
    build_adjudication_user_message,
    build_batch_user_message,
    build_item_user_message,
    get_prompt,
)
from .safety import screen_request

# Rough characters-per-token ratio for English prose, used only to refuse
# oversized inputs early rather than to budget anything precisely.
CHARS_PER_TOKEN: Final[int] = 4
PROMPT_OVERHEAD_TOKENS: Final[int] = 2_000

# A quoted snippet shorter than this cannot be checked against the source with
# any confidence, so it is not treated as grounded evidence.
MIN_GROUNDING_FRAGMENT_CHARS: Final[int] = 20
GROUNDING_FRAGMENT_CHARS: Final[int] = 60

_WHITESPACE: Final[re.Pattern] = re.compile(r"\s+")


class ContextOverflowError(RuntimeError):
    """Raised when checklist plus submission exceed the local context window."""


@dataclass(frozen=True)
class ItemProgress:
    """One checklist item finished. Reported live so a long run is visible."""

    index: int
    total: int
    item: ChecklistItem
    verification: ClauseVerification
    seconds: float

    @property
    def line(self) -> str:
        """A single line fit for a terminal, e.g. '[3/22] STD-03 Found 0.95 p4 12s'."""
        location = (
            f"p{self.verification.page_number}"
            if self.verification.page_number
            else "-"
        )
        return (
            f"[{self.index}/{self.total}] {self.item.id} "
            f"{self.verification.status.value} "
            f"{self.verification.confidence_score:.2f} {location} "
            f"{self.seconds:.0f}s  {self.item.description[:48]}"
        )


ProgressCallback = Callable[[ItemProgress], None]


@dataclass(frozen=True)
class AnalysisOutcome:
    """Either a completeness report or a safety refusal, never both."""

    report: Optional[CompletenessReport] = None
    refusal: Optional[RefusalResponse] = None

    @property
    def refused(self) -> bool:
        return self.refusal is not None


def _normalise(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip().lower()


def _snippet_is_grounded(snippet: Optional[str], haystack_normalised: str) -> bool:
    """Check that a quoted snippet really appears in the submission.

    Guards against a fabricated quotation, which is the failure mode most
    likely to mislead a reviewer, since the snippet is what they would
    otherwise trust without opening the source document.
    """
    if not snippet or not snippet.strip():
        return False
    candidate = _normalise(snippet)
    if candidate in haystack_normalised:
        return True
    # Accept a leading fragment too: models often append an ellipsis or trim
    # the tail of a long quotation.
    head = candidate[:GROUNDING_FRAGMENT_CHARS]
    return len(head) >= MIN_GROUNDING_FRAGMENT_CHARS and head in haystack_normalised


def _page_numbers(submission: ParsedSubmission) -> Set[int]:
    return {page.number for page in submission.pages}


def _unreviewed(item: ChecklistItem) -> ClauseVerification:
    """Placeholder used when the model gave no usable answer for an item.

    Reported as requiring human review rather than as confidently missing, so
    that a model failure is never presented to the reviewer as a finding.
    """
    return AdjudicatedClause(
        checklist_item_id=item.id,
        clause_title=item.description,
        is_present=False,
        page_number=None,
        extracted_snippet=None,
        confidence_score=0.0,
        requires_human_review=True,
        adjudication_note="The model gave no usable answer for this item.",
    )


def _post_process(
    verification: ClauseVerification,
    item: ChecklistItem,
    submission: ParsedSubmission,
    haystack_normalised: str,
    settings: Settings,
) -> AdjudicatedClause:
    """Apply deterministic corrections the model must not be trusted to make.

    The confidence threshold, snippet grounding and page-number validity are
    enforced in code rather than left to the model, so that the three-way
    classification is reproducible regardless of model behaviour.
    """
    # Ground the snippet the model actually returned, then truncate only for
    # display. Truncating first would append an ellipsis that no longer matches
    # the source, falsely failing a long but legitimate quotation.
    grounded = _snippet_is_grounded(verification.extracted_snippet, haystack_normalised)

    snippet = verification.extracted_snippet
    if snippet and len(snippet) > settings.snippet_max_chars:
        snippet = snippet[: settings.snippet_max_chars].rstrip() + "..."

    page_number = verification.page_number
    if page_number is not None and page_number not in _page_numbers(submission):
        page_number = None
    claimed_present = verification.is_present
    is_present = claimed_present and grounded

    if claimed_present:
        # An item claimed present needs review if the model was unsure, or if
        # its quotation could not be located in the source document.
        needs_review = (
            verification.requires_human_review
            or verification.confidence_score < settings.human_review_threshold
            or not grounded
        )
    else:
        # Nothing was claimed present, so there is no evidence to doubt. A low
        # confidence score here simply means the model found nothing.
        needs_review = verification.requires_human_review

    return AdjudicatedClause(
        checklist_item_id=item.id,
        clause_title=verification.clause_title.strip() or item.description,
        is_present=is_present,
        page_number=page_number if is_present else None,
        extracted_snippet=snippet if is_present else None,
        confidence_score=verification.confidence_score,
        requires_human_review=needs_review,
        adjudication_note=(
            None
            if grounded or not claimed_present
            else (
                "Reported present, but the quotation could not be located in "
                "the submission."
            )
        ),
    )


def _apply_adjudication(
    clause: AdjudicatedClause,
    adjudication: EvidenceAdjudication,
    settings: Settings,
) -> AdjudicatedClause:
    """Fold the second pass's verdict into the first pass's answer.

    Three outcomes, because a rejection the second pass does not itself stand
    behind must not delete a document the bidder really filed:

    - Accepted. The item stays Found. Its confidence becomes the weaker of the
      two judgements, which is the first point in this pipeline where the
      review threshold does real work: the first pass returns 0.95 for
      everything it finds, so on its own the threshold never fires.
    - Rejected cleanly, the match score low. The item becomes Not Found, with
      the reason recorded for the reviewer.
    - Rejected while still scoring the passage highly. The second pass is
      arguing with itself, so the item goes to human review with its evidence
      intact rather than a document being deleted on a call that was torn.
    """
    if adjudication.accepts:
        confidence = min(clause.confidence_score, adjudication.match_confidence)
        return clause.model_copy(
            update={
                "confidence_score": confidence,
                "requires_human_review": (
                    clause.requires_human_review
                    or confidence < settings.human_review_threshold
                ),
                "adjudication": adjudication,
                "adjudication_note": adjudication.note,
            }
        )

    where = f" on page {clause.page_number}" if clause.page_number else ""
    reason = (
        f"The first pass quoted a {adjudication.quoted_document}{where}. The "
        f"evidence check found that is not the required "
        f"{adjudication.required_document}."
    )

    if adjudication.contradicts_itself(settings.adjudication_conflict_score):
        return clause.model_copy(
            update={
                "requires_human_review": True,
                "confidence_score": min(
                    clause.confidence_score, adjudication.match_confidence
                ),
                "adjudication": adjudication,
                "adjudication_note": (
                    f"{reason} It still rated the passage a "
                    f"{adjudication.match_confidence:.2f} match, so the two "
                    f"halves of that answer disagree and the item is left for "
                    f"a human to settle."
                ),
            }
        )

    return clause.model_copy(
        update={
            "is_present": False,
            "page_number": None,
            "extracted_snippet": None,
            "confidence_score": 0.0,
            "requires_human_review": False,
            "adjudication": adjudication,
            "adjudication_note": reason,
        }
    )


def _assert_fits_context(
    items: Sequence[ChecklistItem], submission_text: str, settings: Settings
) -> None:
    """Refuse oversized input rather than let the backend truncate it silently.

    The budget is the context window actually requested from the backend, not
    the model's theoretical maximum, because that is what will really be read.
    """
    checklist_chars = sum(len(i.id) + len(i.description) for i in items)
    estimated = (checklist_chars + len(submission_text)) // CHARS_PER_TOKEN
    budget = settings.context_tokens - PROMPT_OVERHEAD_TOKENS - settings.max_output_tokens
    if estimated > budget:
        raise ContextOverflowError(
            "Checklist plus submission is roughly {est:,} tokens, above the "
            "{budget:,} token budget of the configured context window "
            "({ctx:,} tokens). Raise PROCURECHECK_CONTEXT_TOKENS if the machine "
            "has the memory, or route to the Google Gemini 1.5 Flash fallback "
            "described in Prompt Specification v1.0 Sec. 7, which is not yet "
            "configured.".format(est=estimated, budget=budget, ctx=settings.context_tokens)
        )


class MatchingEngine:
    """Runs a completeness check for one submission against one checklist."""

    def __init__(self, client: OllamaClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    def _adjudicate(
        self, clause: AdjudicatedClause, item: ChecklistItem
    ) -> AdjudicatedClause:
        """Second pass. Only items claimed present are worth checking.

        An item already reported absent has no evidence to doubt, so it is
        returned untouched rather than spending a model call to confirm a
        negative.
        """
        if not self._settings.adjudicate:
            return clause
        if not clause.is_present or not clause.extracted_snippet:
            return clause

        system_prompt = get_prompt(self._settings.adjudicator_prompt_version)
        user_message = build_adjudication_user_message(
            item, clause.extracted_snippet, clause.page_number
        )
        try:
            adjudication = self._client.complete_structured(
                system_prompt, user_message, EvidenceAdjudication
            )
        except StructuredOutputError:
            # The check could not be completed, so the claim is unverified.
            # Reporting it as Found would present an unchecked answer as a
            # checked one; reporting it as missing would invent a finding.
            return clause.model_copy(
                update={
                    "requires_human_review": True,
                    "adjudication_note": (
                        "The evidence check could not be completed, so this "
                        "match has not been verified."
                    ),
                }
            )
        return _apply_adjudication(clause, adjudication, self._settings)

    def analyse(
        self,
        items: Sequence[ChecklistItem],
        submission: ParsedSubmission,
        instruction: Optional[str] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> AnalysisOutcome:
        """Run the check, refusing first if the request crosses the boundary.

        `on_progress`, if given, is called after each checklist item is
        decided. A per-item call takes minutes on CPU, so a run without it
        prints nothing for an hour and is indistinguishable from a hang.
        """
        verdict = screen_request(instruction)
        if not verdict.allowed:
            return AnalysisOutcome(refusal=verdict.to_refusal())

        if not items:
            raise ValueError("at least one checklist item is required")

        submission_text = submission.as_marked_text()
        _assert_fits_context(items, submission_text, self._settings)
        haystack = _normalise(submission_text)

        if self._settings.strategy == STRATEGY_BATCH:
            verifications = self._run_batch(items, submission_text, submission, haystack)
        else:
            verifications = self._run_per_item(
                items, submission_text, submission, haystack, on_progress
            )

        return AnalysisOutcome(
            report=CompletenessReport(
                submission_id=submission.submission_id,
                verified_items=verifications,
                missing_items=[v.checklist_item_id for v in verifications if not v.is_present],
            )
        )

    def _run_per_item(
        self,
        items: Sequence[ChecklistItem],
        submission_text: str,
        submission: ParsedSubmission,
        haystack: str,
        on_progress: Optional[ProgressCallback] = None,
    ) -> List[AdjudicatedClause]:
        system_prompt = get_prompt(self._settings.resolved_prompt_version)
        results: List[AdjudicatedClause] = []
        total = len(items)
        for index, item in enumerate(items, start=1):
            started = time.monotonic()
            user_message = build_item_user_message(
                item, submission_text, self._settings.human_review_threshold
            )
            try:
                raw = self._client.complete_structured(
                    system_prompt, user_message, ClauseVerification
                )
                verification = self._adjudicate(
                    _post_process(raw, item, submission, haystack, self._settings),
                    item,
                )
            except StructuredOutputError:
                # One unusable answer must not lose the whole report.
                verification = _unreviewed(item)
            results.append(verification)
            if on_progress is not None:
                on_progress(
                    ItemProgress(
                        index=index,
                        total=total,
                        item=item,
                        verification=verification,
                        seconds=time.monotonic() - started,
                    )
                )
        return results

    def _run_batch(
        self,
        items: Sequence[ChecklistItem],
        submission_text: str,
        submission: ParsedSubmission,
        haystack: str,
    ) -> List[AdjudicatedClause]:
        system_prompt = get_prompt(self._settings.resolved_prompt_version)
        user_message = build_batch_user_message(
            items, submission_text, self._settings.human_review_threshold
        )
        raw_report = self._client.complete_structured(
            system_prompt, user_message, CompletenessReport
        )
        by_id = {v.checklist_item_id: v for v in raw_report.verified_items}

        results: List[AdjudicatedClause] = []
        for item in items:
            raw = by_id.get(item.id)
            if raw is None:
                results.append(_unreviewed(item))
                continue
            results.append(
                self._adjudicate(
                    _post_process(raw, item, submission, haystack, self._settings),
                    item,
                )
            )
        return results
