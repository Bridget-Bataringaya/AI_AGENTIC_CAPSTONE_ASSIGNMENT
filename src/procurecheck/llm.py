"""Ollama client with schema-enforced structured output.

Deviation note for team review: the Model Selection Note (Sec. 5) sketches this
integration using Pydantic AI. This module instead calls Ollama's /api/chat
endpoint directly and passes the Pydantic JSON schema in the request's `format`
field, which makes Ollama constrain generation to that schema at decode time.
The reasons are that it removes a dependency layer between the team's schema
and the running model, it enforces the schema in the sampler rather than
checking it after the fact, and the sample code in the Note as written does not
run (Agent() does not accept base_url and api_key directly). The schema,
prompts, parameters and refusal behaviour are unchanged.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Final, List, Optional, Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import Settings
from .observability import MODEL_CALL, MODEL_OUTPUT, STATUS_ERROR, STATUS_OK, emit, short_hash

ROLE_SYSTEM: Final[str] = "system"
ROLE_USER: Final[str] = "user"

_RETRY_INSTRUCTION: Final[str] = (
    "Your previous output did not match the required schema; return valid JSON "
    "only, matching the schema exactly, with no prose and no code fences."
)

TModel = TypeVar("TModel", bound=BaseModel)

logger = logging.getLogger(__name__)


def _to_ms(nanoseconds: Any) -> Optional[int]:
    """Ollama reports its durations in nanoseconds."""
    return None if not isinstance(nanoseconds, (int, float)) else int(nanoseconds / 1_000_000)


class ModelUnavailableError(RuntimeError):
    """Raised when the model backend cannot be reached or the model is absent."""


class StructuredOutputError(RuntimeError):
    """Raised when the model could not produce schema-valid output after retries."""


class OllamaClient:
    """A thin, synchronous client for a local Ollama server."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=settings.request_timeout_seconds)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "OllamaClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def health(self) -> Dict[str, Any]:
        """Confirm the server is reachable and the configured model is present."""
        try:
            response = self._client.get(self._settings.tags_endpoint)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ModelUnavailableError(
                f"Cannot reach the model backend at {self._settings.base_url}. "
                f"Start it with `ollama serve`. Underlying error: {exc}"
            ) from exc

        available = [entry.get("name", "") for entry in response.json().get("models", [])]
        if self._settings.model not in available:
            raise ModelUnavailableError(
                f"Model {self._settings.model!r} is not installed. Available: "
                f"{', '.join(available) or 'none'}. "
                f"Pull it with `ollama pull {self._settings.model}`."
            )
        return {"backend": self._settings.base_url, "model": self._settings.model,
                "available_models": available}

    def _record_call(
        self,
        payload: Dict[str, Any],
        started: float,
        body: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
    ) -> None:
        """One model_call event: what was sent, by size, and what it cost.

        The prompt is recorded as a fingerprint and a length, the messages as
        a count and a length. No prompt text and no answer text is logged.

        A backend can answer with a body of any shape. Whatever it sends, the
        call it answered must not fail because the log could not describe it.
        """
        try:
            self._emit_call(payload, started, body, error)
        except Exception:  # noqa: BLE001 - recording must never fail the call it records
            logger.warning("A model call could not be recorded", exc_info=True)

    def _emit_call(
        self,
        payload: Dict[str, Any],
        started: float,
        body: Optional[Dict[str, Any]],
        error: Optional[Exception],
    ) -> None:
        messages = [m for m in (payload.get("messages") or []) if isinstance(m, dict)]
        system = str(next((m.get("content") or "" for m in messages if m.get("role") == ROLE_SYSTEM), ""))
        event: Dict[str, Any] = {
            "model": payload.get("model"),
            "structured": "format" in payload,
            "tools_offered": len(payload.get("tools") or []),
            "messages": len(messages),
            "system_prompt_sha256": short_hash(system) if system else None,
            "system_prompt_chars": len(system),
            "input_chars": sum(len(str(m.get("content") or "")) for m in messages),
            "options": payload.get("options"),
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "status": STATUS_OK if error is None else STATUS_ERROR,
        }
        if error is not None:
            response = getattr(error, "response", None)
            event["error_kind"] = type(error).__name__
            event["http_status"] = getattr(response, "status_code", None)
        if isinstance(body, dict):
            message = body.get("message") if isinstance(body.get("message"), dict) else {}
            event.update({
                "output_chars": len(str(message.get("content") or "")),
                "tool_calls_proposed": len(message["tool_calls"]) if isinstance(message.get("tool_calls"), list) else 0,
                "prompt_tokens": body.get("prompt_eval_count"),
                "output_tokens": body.get("eval_count"),
                "load_ms": _to_ms(body.get("load_duration")),
                "prompt_eval_ms": _to_ms(body.get("prompt_eval_duration")),
                "eval_ms": _to_ms(body.get("eval_duration")),
                "done_reason": body.get("done_reason"),
            })
        emit(MODEL_CALL, **event)

    def _post_message(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        started = time.perf_counter()
        try:
            response = self._client.post(self._settings.chat_endpoint, json=payload)
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            self._record_call(payload, started, error=exc)
            raise ModelUnavailableError(
                f"Model request failed against {self._settings.chat_endpoint}. "
                f"Underlying error: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            self._record_call(payload, started, error=exc)
            raise ModelUnavailableError(
                f"The model backend at {self._settings.chat_endpoint} answered "
                f"with something other than JSON. Underlying error: {exc}"
            ) from exc
        self._record_call(payload, started, body=body if isinstance(body, dict) else None)
        message = body.get("message") if isinstance(body, dict) else None
        return message if isinstance(message, dict) else {}

    def _post(self, payload: Dict[str, Any]) -> str:
        return self._post_message(payload).get("content", "")

    def _options(self) -> Dict[str, Any]:
        return {
            "temperature": self._settings.temperature,
            "top_p": self._settings.top_p,
            "num_predict": self._settings.max_output_tokens,
            # Always explicit. Ollama otherwise defaults to 4096 tokens and
            # silently drops the rest of the submission.
            "num_ctx": self._settings.context_tokens,
        }

    def chat_with_tools(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """One model turn with tools on offer. Returns the assistant message.

        The model only proposes calls. It never runs one: the message comes
        back to the orchestrator, which validates, authorises and executes
        each proposed call itself (tools/registry.py).
        """
        return self._post_message({
            "model": self._settings.model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": self._options(),
        })

    def complete_structured(
        self, system_prompt: str, user_message: str, schema: Type[TModel]
    ) -> TModel:
        """Call the model and return an instance of `schema`.

        On a schema validation failure the same request is retried with a
        corrective instruction appended, up to settings.schema_retry_limit
        times. A final failure raises rather than returning a silently empty
        result, per Prompt Specification v1.0 Sec. 7.
        """
        messages = [
            {"role": ROLE_SYSTEM, "content": system_prompt},
            {"role": ROLE_USER, "content": user_message},
        ]
        payload: Dict[str, Any] = {
            "model": self._settings.model,
            "messages": messages,
            "stream": False,
            "format": schema.model_json_schema(),
            "options": self._options(),
        }

        last_error: Exception | None = None
        raw = ""
        for attempt in range(self._settings.schema_retry_limit + 1):
            if attempt > 0:
                payload = {
                    **payload,
                    "messages": messages
                    + [
                        {"role": ROLE_USER, "content": _RETRY_INSTRUCTION},
                    ],
                }
            raw = self._post(payload)
            try:
                parsed = schema.model_validate_json(raw)
            except ValidationError as exc:
                last_error = exc
            except json.JSONDecodeError as exc:
                last_error = exc
            else:
                emit(MODEL_OUTPUT, schema=schema.__name__, attempt=attempt + 1, valid=True)
                return parsed
            emit(MODEL_OUTPUT, schema=schema.__name__, attempt=attempt + 1, valid=False,
                 error_kind=type(last_error).__name__)

        raise StructuredOutputError(
            f"The model did not return output matching {schema.__name__} after "
            f"{self._settings.schema_retry_limit + 1} attempts. "
            f"Last raw output: {raw[:500]!r}. Error: {last_error}"
        )
