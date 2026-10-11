"""Safety Guard.

Implements the gate described in the Architecture and Context Diagram
(Sec. 4) and required by User Stories AC6 to AC9. It screens a user's
free-text request BEFORE it reaches the matching engine and refuses anything
that asks the system to score, rank, draw a legal conclusion, or recommend a
contract award.

Scope note: this guard applies to user instructions only, never to the body of
an uploaded submission. A tender document may legitimately contain the word
"score" or "award"; treating document text as an instruction would both break
normal operation and misread data as a command. Instructions embedded inside
document text are neutralised separately, by the prompt-level safeguard in
prompts.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Optional, Pattern, Sequence, Tuple

from .models import REFUSAL_REASON, RefusalResponse

# Each rule is (label, pattern). Patterns use word boundaries so that ordinary
# procurement vocabulary such as "corporate" or "incorporated" cannot trip a
# refusal on a substring match.
_RULES: Final[Sequence[Tuple[str, Pattern[str]]]] = (
    ("scoring", re.compile(r"\b(score|scores|scored|scoring|grade|grades|graded|grading|rate|rates|rated|rating|marks?\s+out\s+of|out\s+of\s+(?:10|100))\b", re.I)),
    ("ranking", re.compile(r"\b(rank|ranks|ranked|ranking|shortlist|shortlisted|best\s+(?:bid|bidder|tender|tenderer|supplier|vendor)|better\s+(?:bid|bidder|tender|tenderer|supplier|vendor)|which\s+(?:bid|bidder|tenderer?|supplier|vendor|submission|one)|(?:should\s+we|should\s+i|do\s+we)\s+(?:pick|choose|select|go\s+with|prefer)|compare\s+(?:the\s+)?(?:bids|bidders|tenders|tenderers|submissions|suppliers|vendors)|winner|winning\s+(?:bid|bidder|tender))\b", re.I)),
    ("legal_conclusion", re.compile(r"\b(legally\s+(?:binding|valid|enforceable|sufficient)|legal\s+(?:advice|opinion|validity|conclusion)|enforceable|is\s+this\s+clause\s+(?:valid|sufficient|binding))\b", re.I)),
    # "awarded" and "be awarded" were added after team test case TC09 asked
    # "Should this bidder be awarded the contract?" and passed the guard: the
    # rule only knew the active "award the contract".
    ("award_recommendation", re.compile(r"\b(awarded\s+(?:the\s+)?(?:contract|bid|tender)|be\s+(?:awarded|disqualified)|award\s+(?:the\s+)?(?:contract|bid|tender)|recommend\s+(?:award|acceptance|rejection|a\s+bid)|should\s+we\s+(?:award|accept|reject|disqualify)|disqualify|disqualification|reject\s+(?:the\s+)?(?:bid|bidder|tender)|approve\s+(?:the\s+)?(?:bid|tender|award))\b", re.I)),
)


@dataclass(frozen=True)
class GuardVerdict:
    """The outcome of screening one request."""

    allowed: bool
    category: Optional[str] = None
    matched_text: Optional[str] = None

    def to_refusal(self) -> RefusalResponse:
        if self.allowed:
            raise ValueError("cannot build a refusal from an allowed verdict")
        return RefusalResponse(
            refusal=True, reason=REFUSAL_REASON, trigger=self.matched_text
        )


def screen_request(text: Optional[str]) -> GuardVerdict:
    """Screen a user instruction against the confirmed safety boundary.

    An empty or missing instruction is allowed: the default operation is a
    plain completeness check, which is always within boundary.
    """
    if text is None or not text.strip():
        return GuardVerdict(allowed=True)

    for category, pattern in _RULES:
        match = pattern.search(text)
        if match:
            return GuardVerdict(
                allowed=False, category=category, matched_text=match.group(0)
            )
    return GuardVerdict(allowed=True)


def assert_single_submission(submission_count: int) -> None:
    """Enforce User Stories AC7: no comparison across submissions.

    Each submission must be processed entirely independently, so more than one
    submission in a single request is rejected outright rather than silently
    producing comparative output.
    """
    if submission_count > 1:
        raise MultipleSubmissionsError(
            "This system processes one submission at a time and cannot compare "
            "or rank submissions. Please upload a single submission."
        )


class MultipleSubmissionsError(ValueError):
    """Raised when a caller supplies more than one submission in one request."""
