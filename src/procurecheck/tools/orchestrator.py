"""Tool calling through the application layer.

The model is offered the tools and proposes calls. The application decides
whether each proposal runs. A run goes like this:

    request -> safety guard -> model turn -> proposed call(s)
            -> ToolExecutor (exists? permitted? valid? run, check output)
            -> result back to the model -> ... -> final answer -> safety guard

Four things the model cannot do, however it is prompted:

- run a tool: it only names one; execution happens in ToolExecutor;
- choose the document or checklist: those arguments are bound from the session
  and anything the model writes into them is discarded;
- loop forever: the run stops after `max_turns` model turns;
- deliver a verdict on the bid: a request that asks for one is refused before
  the model is called, and a final answer that gives one is withheld.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any, Dict, Final, List, Mapping, Optional, Protocol, Tuple

from ..llm import ModelUnavailableError
from ..prompts import PROMPT_ORCHESTRATOR_V1_0, build_orchestrator_user_message
from ..safety import screen_request
from .authorization import Principal
from .completeness import TOOL_CHECK, TOOL_REPORT
from .contracts import (
    CheckCompletenessOutput,
    ErrorCode,
    GenerateReportOutput,
    ToolError,
)
from .registry import ToolExecutor, ToolResult

DEFAULT_MAX_TURNS: Final[int] = 5
ROLE_SYSTEM: Final[str] = "system"
ROLE_USER: Final[str] = "user"
ROLE_ASSISTANT: Final[str] = "assistant"
ROLE_TOOL: Final[str] = "tool"

WITHHELD_ANSWER: Final[str] = (
    "The model's summary was withheld because it crossed the safety boundary. "
    "The tool results in this run are unchanged and can be read directly."
)


class ChatModel(Protocol):
    def chat_with_tools(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]: ...


@dataclass(frozen=True)
class AgentSession:
    """What the application holds for the tools during one run."""

    document_name: str
    document_text: str
    required_items: Tuple[str, ...]
    last_check: Optional[CheckCompletenessOutput] = None

    def bound_arguments(self, tool: str) -> Dict[str, Any]:
        if tool == TOOL_CHECK:
            return {"document_text": self.document_text, "required_items": list(self.required_items)}
        if tool == TOOL_REPORT:
            bound: Dict[str, Any] = {"document_name": self.document_name}
            if self.last_check is None:
                # No results to bind. The tool then answers NO_ANALYSIS_RESULTS,
                # which tells the model what to do next.
                return {**bound, "document_type": "unknown", "completeness_percentage": 0.0}
            return {
                **bound,
                "document_type": self.last_check.document_type,
                "completeness_percentage": self.last_check.completeness_percentage,
                "completeness_results": [
                    r.model_dump(mode="json") for r in self.last_check.results
                ],
            }
        return {}


@dataclass(frozen=True)
class AgentRun:
    """Everything that happened in one run, in order."""

    request: str
    principal: Optional[Principal]
    tool_results: Tuple[ToolResult, ...] = ()
    final_message: Optional[str] = None
    error: Optional[ToolError] = None
    model_turns: int = 0
    discarded_arguments: Tuple[str, ...] = ()
    check: Optional[CheckCompletenessOutput] = None
    report: Optional[GenerateReportOutput] = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_trace(self) -> Dict[str, Any]:
        return {
            "request": self.request,
            "principal": None if self.principal is None else {
                "user_id": self.principal.user_id, "role": self.principal.role,
            },
            "prompt_version": "orchestrator-v1.0",
            "model_turns": self.model_turns,
            "status": "success" if self.ok else "error",
            "error": None if self.error is None else self.error.to_dict(),
            "discarded_model_arguments": list(self.discarded_arguments),
            "tool_calls": [r.to_trace() for r in self.tool_results],
            "final_message": self.final_message,
            "report": None if self.report is None else self.report.model_dump(mode="json"),
        }


@dataclass(frozen=True)
class ProposedCall:
    name: str
    arguments: Dict[str, Any]
    problem: Optional[ToolError] = None


def parse_tool_calls(message: Mapping[str, Any]) -> List[ProposedCall]:
    """Read the model's proposed calls without trusting their shape.

    A malformed entry becomes a ProposedCall carrying the problem, so it is
    answered with a structured error the model can read, not dropped silently
    and not allowed to raise.
    """
    raw_calls = message.get("tool_calls") or []
    if not isinstance(raw_calls, list):
        return [ProposedCall("", {}, ToolError(
            error_code=ErrorCode.INVALID_ARGUMENTS, message="tool_calls must be a list.",
        ))]
    calls: List[ProposedCall] = []
    for raw in raw_calls:
        function = raw.get("function") if isinstance(raw, dict) else None
        if not isinstance(function, dict):
            calls.append(ProposedCall("", {}, ToolError(
                error_code=ErrorCode.INVALID_ARGUMENTS,
                message="A proposed tool call had no function to call.",
            )))
            continue
        name = str(function.get("name") or "")
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError as exc:
                calls.append(ProposedCall(name, {}, ToolError(
                    error_code=ErrorCode.INVALID_ARGUMENTS,
                    message=f"The arguments for {name} were not valid JSON: {exc}.",
                )))
                continue
        if not isinstance(arguments, dict):
            calls.append(ProposedCall(name, {}, ToolError(
                error_code=ErrorCode.INVALID_ARGUMENTS,
                message=f"The arguments for {name} must be a JSON object.",
            )))
            continue
        calls.append(ProposedCall(name, arguments))
    return calls


def _refused_throughout(results: List[ToolResult]) -> Optional[ToolError]:
    """A run whose every tool call was refused for permission is itself refused.

    Otherwise the run would end with a final answer and no error, and a caller
    checking only the outcome would read a fully refused run as a success.
    """
    if results and all(
        r.error is not None and r.error.error_code is ErrorCode.UNAUTHORIZED for r in results
    ):
        return results[0].error
    return None


@dataclass
class _RunState:
    session: AgentSession
    results: List[ToolResult] = field(default_factory=list)
    discarded: List[str] = field(default_factory=list)
    report: Optional[GenerateReportOutput] = None


class ToolCallingAgent:
    def __init__(
        self, model: ChatModel, executor: ToolExecutor, max_turns: int = DEFAULT_MAX_TURNS
    ) -> None:
        if max_turns < 1:
            raise ValueError("max_turns must be at least 1")
        self._model = model
        self._executor = executor
        self._max_turns = max_turns

    def _execute(self, call: ProposedCall, principal: Optional[Principal], state: _RunState) -> ToolResult:
        if call.problem is not None:
            return ToolResult(call.name, call.arguments, error=call.problem)
        spec = self._executor.registry.get(call.name)
        bound_names = spec.bound_fields if spec else ()
        overridden = sorted(k for k in call.arguments if k in bound_names)
        state.discarded.extend(f"{call.name}.{k}" for k in overridden)
        model_args = {k: v for k, v in call.arguments.items() if k not in bound_names}
        arguments = {**model_args, **state.session.bound_arguments(call.name)}
        result = self._executor.execute(call.name, arguments, principal)

        if result.ok and isinstance(result.output, CheckCompletenessOutput):
            state.session = replace(state.session, last_check=result.output)
        if result.ok and isinstance(result.output, GenerateReportOutput):
            state.report = result.output
        return result

    def _finish(self, request: str, principal: Optional[Principal], state: _RunState,
                turns: int, final: Optional[str] = None,
                error: Optional[ToolError] = None) -> AgentRun:
        return AgentRun(
            request=request,
            principal=principal,
            tool_results=tuple(state.results),
            final_message=final,
            error=error,
            model_turns=turns,
            discarded_arguments=tuple(state.discarded),
            check=state.session.last_check,
            report=state.report,
        )

    def run(self, request: str, principal: Optional[Principal], session: AgentSession) -> AgentRun:
        state = _RunState(session=session)
        verdict = screen_request(request)
        if not verdict.allowed:
            refusal = verdict.to_refusal()
            return self._finish(request, principal, state, 0, error=ToolError(
                error_code=ErrorCode.REFUSED, message=refusal.reason,
            ))

        messages: List[Dict[str, Any]] = [
            {"role": ROLE_SYSTEM, "content": PROMPT_ORCHESTRATOR_V1_0},
            {"role": ROLE_USER, "content": build_orchestrator_user_message(
                request, session.document_name, len(session.required_items))},
        ]
        tools = self._executor.registry.definitions()

        for turn in range(1, self._max_turns + 1):
            try:
                message = self._model.chat_with_tools(messages, tools)
            except ModelUnavailableError as exc:
                return self._finish(request, principal, state, turn, error=ToolError(
                    error_code=ErrorCode.SERVICE_UNAVAILABLE,
                    message=f"The model backend is unavailable, so no tool was chosen. {exc}",
                ))

            calls = parse_tool_calls(message)
            if not calls:
                answer = str(message.get("content") or "").strip()
                if not screen_request(answer).allowed:
                    answer = WITHHELD_ANSWER
                return self._finish(request, principal, state, turn, final=answer,
                                    error=_refused_throughout(state.results))

            messages.append({
                "role": ROLE_ASSISTANT,
                "content": str(message.get("content") or ""),
                "tool_calls": message.get("tool_calls"),
            })
            for call in calls:
                result = self._execute(call, principal, state)
                state.results.append(result)
                messages.append({
                    "role": ROLE_TOOL,
                    "tool_name": result.tool,
                    "content": json.dumps(result.payload(), ensure_ascii=False),
                })

        return self._finish(request, principal, state, self._max_turns, error=ToolError(
            error_code=ErrorCode.STEP_LIMIT_REACHED,
            message=(
                f"The model was still calling tools after {self._max_turns} turns, so the "
                "run was stopped. The tool results so far are kept in the trace."
            ),
        ))
