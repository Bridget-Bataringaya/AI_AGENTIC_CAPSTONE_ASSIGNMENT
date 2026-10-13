"""Observability (Week 7): the run log.

recorder  the events of one run, and the JSON Lines file they are written to
commands  the `logs` command: list, show, summary
"""

from .recorder import (
    DECISION,
    ITEM_OUTCOME,
    MODEL_CALL,
    MODEL_OUTPUT,
    RETRIEVAL,
    RUN_FINISHED,
    RUN_STARTED,
    STATUS_ERROR,
    STATUS_OK,
    TOOL_CALL,
    RunRecorder,
    active,
    clip,
    emit,
    labelled,
    purge_expired,
    recording,
    resolve_log_dir,
    short_hash,
)

__all__ = [
    "DECISION",
    "ITEM_OUTCOME",
    "MODEL_CALL",
    "MODEL_OUTPUT",
    "RETRIEVAL",
    "RUN_FINISHED",
    "RUN_STARTED",
    "STATUS_ERROR",
    "STATUS_OK",
    "TOOL_CALL",
    "RunRecorder",
    "active",
    "clip",
    "emit",
    "labelled",
    "purge_expired",
    "recording",
    "resolve_log_dir",
    "short_hash",
]
