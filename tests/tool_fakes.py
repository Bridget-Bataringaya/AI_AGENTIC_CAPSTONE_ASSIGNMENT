"""Stand-ins for the model, shared by the tool and orchestration tests.

StubModelClient answers the Matching Engine's structured calls, so the check
tool runs its real pipeline without a server. ScriptedChat plays the model's
side of a tool-calling conversation turn by turn, so every odd thing a model
can say is reproducible.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from procurecheck.config import Settings
from procurecheck.llm import ModelUnavailableError
from procurecheck.models import ClauseVerification, EvidenceAdjudication
from procurecheck.tools import (
    AgentSession,
    Principal,
    ToolCallingAgent,
    ToolContext,
    ToolExecutor,
    default_registry,
)

TAX_TEXT = "A Tax Clearance Certificate reference TCC/2026/00417 is enclosed."
DOCUMENT = f"[PAGE 1]\nTender reference SYN/2026/001 for civil works.\n\n[PAGE 2]\n{TAX_TEXT}"
ITEMS = ["Valid tax clearance certificate", "Bid securing declaration"]

OFFICER = Principal(user_id="officer-1", role="procurement_officer")
COMMITTEE = Principal(user_id="committee-1", role="evaluation_committee")
BIDDER = Principal(user_id="bidder-1", role="bidder")

SESSION = AgentSession("bid.pdf", DOCUMENT, tuple(ITEMS))
FINAL = {"content": "The document is Incomplete at 50%. Missing: Bid securing declaration."}


class StubModelClient:
    """Finds the tax clearance certificate on page 2 and nothing else."""

    def __init__(self, unavailable: bool = False) -> None:
        self.unavailable = unavailable
        self.calls = 0

    def complete_structured(self, system_prompt, user_message, schema):
        self.calls += 1
        if self.unavailable:
            raise ModelUnavailableError("Cannot reach the model backend (test).")
        if schema is EvidenceAdjudication:
            return EvidenceAdjudication(
                required_document="tax clearance certificate",
                quoted_document="tax clearance certificate",
                same_document=True,
                both_required_separately=False,
                match_confidence=1.0,
            )
        item = user_message.split("CHECKLIST ITEM:")[1].split("SUBMISSION TEXT")[0]
        if "tax clearance" in item.lower():
            return ClauseVerification(
                checklist_item_id="REQ-01", clause_title="Tax clearance certificate",
                is_present=True, page_number=2, extracted_snippet=TAX_TEXT,
                confidence_score=0.95, requires_human_review=False,
            )
        return ClauseVerification(
            checklist_item_id="REQ-02", clause_title="Bid securing declaration",
            is_present=False, confidence_score=0.0, requires_human_review=False,
        )


def executor(client: Any = None) -> ToolExecutor:
    return ToolExecutor(default_registry(), ToolContext(Settings(), client or StubModelClient()))


def tool_call(name: str, arguments: Any = None) -> Dict[str, Any]:
    return {"function": {"name": name, "arguments": {} if arguments is None else arguments}}


class ScriptedChat:
    """Returns one scripted assistant message per turn, and records what it saw."""

    def __init__(self, turns: Sequence[Any]) -> None:
        self._turns = list(turns)
        self.seen: List[List[Dict[str, Any]]] = []
        self.tools_offered: Optional[List[Dict[str, Any]]] = None

    def chat_with_tools(self, messages, tools):
        self.seen.append([dict(m) for m in messages])
        self.tools_offered = tools
        if not self._turns:
            raise AssertionError("the model was called more times than scripted")
        turn = self._turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        return turn

    @property
    def calls(self) -> int:
        return len(self.seen)


class FakeOllama(StubModelClient):
    """Stands in for OllamaClient: structured calls and tool-calling turns."""

    script: List[Any] = []

    def __init__(self, settings=None) -> None:
        super().__init__()
        self._chat = ScriptedChat(list(FakeOllama.script))

    def chat_with_tools(self, messages, tools):
        return self._chat.chat_with_tools(messages, tools)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return None


def run_agent(turns, principal=OFFICER, client=None, request="Check this bid for completeness.", max_turns=5):
    """One orchestrated run against SESSION with a scripted model."""
    chat = ScriptedChat(turns)
    agent = ToolCallingAgent(chat, executor(client), max_turns=max_turns)
    return agent.run(request, principal, SESSION), chat
