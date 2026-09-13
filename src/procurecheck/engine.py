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
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, List, Optional, Sequence, Set

from .config import STRATEGY_BATCH, Settings
from .ingestion.submission import ParsedSubmission
from .llm import OllamaClient, StructuredOutputError
from .models import ChecklistItem, ClauseVerification, CompletenessReport, RefusalResponse
from .prompts import (
    PROMPT_VERSION_V1_0,
    PROMPT_VERSION_V1_0_PER_ITEM,
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
    return ClauseVerification(
        checklist_item_id=item.id,
        clause_title=item.description,
        is_present=False,
        page_number=None,
        extracted_snippet=None,
        confidence_score=0.0,
        requires_human_review=True,
    )


def _post_process(
    verification: ClauseVerification,
    item: ChecklistItem,
    submission: ParsedSubmission,
    haystack_normalised: str,
    settings: Settings,
) -> ClauseVerification:
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

    return ClauseVerification(
        checklist_item_id=item.id,
        clause_title=verification.clause_title.strip() or item.description,
        is_present=is_present,
        page_number=page_number if is_present else None,
        extracted_snippet=snippet if is_present else None,
        confidence_score=verification.confidence_score,
        requires_human_review=needs_review,
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

    def analyse(
        self,
        items: Sequence[ChecklistItem],
        submission: ParsedSubmission,
        instruction: Optional[str] = None,
    ) -> AnalysisOutcome:
        """Run the check, refusing first if the request crosses the boundary."""
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
            verifications = self._run_per_item(items, submission_text, submission, haystack)

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
    ) -> List[ClauseVerification]:
        system_prompt = get_prompt(PROMPT_VERSION_V1_0_PER_ITEM)
        results: List[ClauseVerification] = []
        for item in items:
            user_message = build_item_user_message(
                item, submission_text, self._settings.human_review_threshold
            )
            try:
                raw = self._client.complete_structured(
                    system_prompt, user_message, ClauseVerification
                )
            except StructuredOutputError:
                # One unusable answer must not lose the whole report.
                results.append(_unreviewed(item))
                continue
            results.append(_post_process(raw, item, submission, haystack, self._settings))
        return results

    def _run_batch(
        self,
        items: Sequence[ChecklistItem],
        submission_text: str,
        submission: ParsedSubmission,
        haystack: str,
    ) -> List[ClauseVerification]:
        system_prompt = get_prompt(PROMPT_VERSION_V1_0)
        user_message = build_batch_user_message(
            items, submission_text, self._settings.human_review_threshold
        )
        raw_report = self._client.complete_structured(
            system_prompt, user_message, CompletenessReport
        )
        by_id = {v.checklist_item_id: v for v in raw_report.verified_items}

        results: List[ClauseVerification] = []
        for item in items:
            raw = by_id.get(item.id)
            if raw is None:
                results.append(_unreviewed(item))
                continue
            results.append(_post_process(raw, item, submission, haystack, self._settings))
        return results
