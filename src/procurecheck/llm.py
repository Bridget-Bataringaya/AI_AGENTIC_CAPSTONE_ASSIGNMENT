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
from typing import Any, Dict, Final, Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .config import Settings

ROLE_SYSTEM: Final[str] = "system"
ROLE_USER: Final[str] = "user"

_RETRY_INSTRUCTION: Final[str] = (
    "Your previous output did not match the required schema; return valid JSON "
    "only, matching the schema exactly, with no prose and no code fences."
)

TModel = TypeVar("TModel", bound=BaseModel)


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

    def _post(self, payload: Dict[str, Any]) -> str:
        try:
            response = self._client.post(self._settings.chat_endpoint, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ModelUnavailableError(
                f"Model request failed against {self._settings.chat_endpoint}. "
                f"Underlying error: {exc}"
            ) from exc
        return response.json().get("message", {}).get("content", "")

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
            "options": {
                "temperature": self._settings.temperature,
                "top_p": self._settings.top_p,
                "num_predict": self._settings.max_output_tokens,
                # Always explicit. Ollama otherwise defaults to 4096 tokens and
                # silently drops the rest of the submission.
                "num_ctx": self._settings.context_tokens,
            },
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
                return schema.model_validate_json(raw)
            except ValidationError as exc:
                last_error = exc
            except json.JSONDecodeError as exc:
                last_error = exc

        raise StructuredOutputError(
            f"The model did not return output matching {schema.__name__} after "
            f"{self._settings.schema_retry_limit + 1} attempts. "
            f"Last raw output: {raw[:500]!r}. Error: {last_error}"
        )
