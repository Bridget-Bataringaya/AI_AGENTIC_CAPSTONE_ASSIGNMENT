"""Runtime configuration for the Public Procurement Document-Completeness Agent.

Every value here is sourced from the environment so that no model name,
endpoint or threshold is hardcoded into application logic. Defaults match the
settings fixed in the team's Model Selection Note (Sec. 6) and Prompt
Specification v1.0 (Sec. 5).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Final

# Defaults confirmed in the Model Selection Note and Prompt Specification v1.0.
DEFAULT_MODEL: Final[str] = "llama3.1:8b"
DEFAULT_BASE_URL: Final[str] = "http://localhost:11434"
DEFAULT_TEMPERATURE: Final[float] = 0.0
DEFAULT_TOP_P: Final[float] = 0.9
DEFAULT_MAX_OUTPUT_TOKENS: Final[int] = 2048
DEFAULT_HUMAN_REVIEW_THRESHOLD: Final[float] = 0.85

# The context window actually requested from the backend.
#
# Llama 3.1 8B supports 128k tokens, as recorded in the Accessible Model
# Documentation, but Ollama defaults num_ctx to 4096 and will silently discard
# anything beyond it. Silent truncation is the worst failure mode this system
# can have: a required document that IS in the submission would be reported
# missing. So the window is always requested explicitly.
#
# The default is 16384 rather than 128000 because the KV cache for Llama 3.1 8B
# costs roughly 128 KB per token, so a full 128k window needs about 16 GB of
# memory on top of the weights. 16384 tokens costs about 2 GB and holds roughly
# 45 pages of text. Raise it if the machine has the memory.
DEFAULT_CONTEXT_TOKENS: Final[int] = 16_384

# Operational defaults, not drawn from the team documents.
#
# The timeout has to cover the slowest realistic single call, not the typical
# one. On the CPU-only development machine a per-item call under prompt v2.0
# has taken as long as 432 seconds, and the first call of a run also carries
# model load. A timeout that trips mid-run costs the whole evaluation, so the
# default is generous: it exists to catch a hung backend, not to bound
# ordinary slowness. Lower it on hardware with a GPU.
DEFAULT_REQUEST_TIMEOUT_SECONDS: Final[float] = 1800.0
DEFAULT_SCHEMA_RETRY_LIMIT: Final[int] = 1
DEFAULT_SNIPPET_MAX_CHARS: Final[int] = 400

# Matching strategies. PER_ITEM issues one model call per checklist item;
# BATCH follows Prompt Specification v1.0 literally and asks for the whole
# report in a single call. See docs note in engine.py.
STRATEGY_PER_ITEM: Final[str] = "per_item"
STRATEGY_BATCH: Final[str] = "batch"

# The numbered prompt version the run uses. The per-item or batch form is
# derived from the strategy above, so this names the iteration only. v1.0 is
# kept selectable so the v1.0 baseline in docs/evaluation/ can be reproduced
# and compared against. See prompts/prompt-version-history.md.
DEFAULT_PROMPT_VERSION: Final[str] = "v2.0"


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings. Build with Settings.from_env()."""

    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    temperature: float = DEFAULT_TEMPERATURE
    top_p: float = DEFAULT_TOP_P
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    context_tokens: int = DEFAULT_CONTEXT_TOKENS
    human_review_threshold: float = DEFAULT_HUMAN_REVIEW_THRESHOLD
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS
    schema_retry_limit: int = DEFAULT_SCHEMA_RETRY_LIMIT
    snippet_max_chars: int = DEFAULT_SNIPPET_MAX_CHARS
    strategy: str = STRATEGY_PER_ITEM
    prompt_version: str = DEFAULT_PROMPT_VERSION

    def __post_init__(self) -> None:
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("temperature must be between 0.0 and 2.0")
        if not 0.0 < self.top_p <= 1.0:
            raise ValueError("top_p must be greater than 0.0 and at most 1.0")
        if not 0.0 <= self.human_review_threshold <= 1.0:
            raise ValueError("human_review_threshold must be between 0.0 and 1.0")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        if self.context_tokens <= self.max_output_tokens:
            raise ValueError("context_tokens must exceed max_output_tokens")
        if self.strategy not in (STRATEGY_PER_ITEM, STRATEGY_BATCH):
            raise ValueError(
                f"strategy must be {STRATEGY_PER_ITEM!r} or {STRATEGY_BATCH!r}"
            )
        # Imported here rather than at module level so that the registry stays
        # the single source of truth for which versions exist, without config
        # taking a permanent dependency on the prompt text.
        from .prompts import SELECTABLE_PROMPT_VERSIONS

        if self.prompt_version not in SELECTABLE_PROMPT_VERSIONS:
            selectable = ", ".join(SELECTABLE_PROMPT_VERSIONS)
            raise ValueError(
                f"prompt_version must be one of: {selectable}. "
                f"Got {self.prompt_version!r}."
            )

    @property
    def chat_endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/api/chat"

    @property
    def tags_endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/api/tags"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            model=_env_str("PROCURECHECK_MODEL", DEFAULT_MODEL),
            base_url=_env_str("PROCURECHECK_BASE_URL", DEFAULT_BASE_URL),
            temperature=_env_float("PROCURECHECK_TEMPERATURE", DEFAULT_TEMPERATURE),
            top_p=_env_float("PROCURECHECK_TOP_P", DEFAULT_TOP_P),
            max_output_tokens=_env_int(
                "PROCURECHECK_MAX_OUTPUT_TOKENS", DEFAULT_MAX_OUTPUT_TOKENS
            ),
            context_tokens=_env_int(
                "PROCURECHECK_CONTEXT_TOKENS", DEFAULT_CONTEXT_TOKENS
            ),
            human_review_threshold=_env_float(
                "PROCURECHECK_HUMAN_REVIEW_THRESHOLD", DEFAULT_HUMAN_REVIEW_THRESHOLD
            ),
            request_timeout_seconds=_env_float(
                "PROCURECHECK_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS
            ),
            schema_retry_limit=_env_int(
                "PROCURECHECK_SCHEMA_RETRY_LIMIT", DEFAULT_SCHEMA_RETRY_LIMIT
            ),
            snippet_max_chars=_env_int(
                "PROCURECHECK_SNIPPET_MAX_CHARS", DEFAULT_SNIPPET_MAX_CHARS
            ),
            strategy=_env_str("PROCURECHECK_STRATEGY", STRATEGY_PER_ITEM),
            prompt_version=_env_str(
                "PROCURECHECK_PROMPT_VERSION", DEFAULT_PROMPT_VERSION
            ),
        )

    @property
    def resolved_prompt_version(self) -> str:
        """The registry id of the prompt this run will actually send."""
        from .prompts import resolve_prompt_version

        return resolve_prompt_version(
            self.prompt_version, per_item=self.strategy == STRATEGY_PER_ITEM
        )
