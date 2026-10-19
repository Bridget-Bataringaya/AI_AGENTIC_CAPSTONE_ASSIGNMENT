"""The run log: one line of evidence for each thing a run did.

A workflow trace says what was decided. The run log says what it cost and what
went wrong on the way: every model call with its prompt version, size, tokens
and latency; every tool call with its outcome; every search with its scores;
every planning decision; and how the run ended. One run writes one JSON Lines
file, so a run can be read on its own and many runs can be summed.

The events of one run:

    run_started   who ran what, on which model, prompt and settings
    decision      one planning decision of the workflow, with its reason
    model_call    one request to the model: prompt, sizes, tokens, latency, error
    model_output  whether the answer matched its schema, per attempt
    item_outcome  the verdict on one checklist item and how it was reached
    retrieval     one corpus search: mode, scores, sources, latency
    tool_call     one tool call: caller, outcome, error code, latency
    run_finished  the outcome, the time taken and the totals

What the log deliberately leaves out: the submission's text, any quotation
from it, the prompt text and the model's answer. A prompt is recorded as its
version, a fingerprint and a length, which is enough to tell exactly which
prompt ran, since every version is in prompts.py. Sizes and counts say how much
was sent without saying what. The free text that is kept is not bid content:
checklist item wording, a search query and a planning reason.

Recording must never change a run. Nothing here raises into the caller: an
event that cannot be recorded is dropped, and a log that cannot be written is
reported and skipped.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Final, Iterator, List, Optional, Tuple

from .. import __version__
from ..checklists import REPO_ROOT
from ..config import Settings

logger = logging.getLogger(__name__)

SCHEMA_VERSION: Final[int] = 1
LOG_SUFFIX: Final[str] = ".jsonl"
# Only files named the way write() names them are ever deleted, so a log
# folder that also holds other files loses nothing but its own old logs.
LOG_NAME: Final["re.Pattern[str]"] = re.compile(r"^\d{8}-\d{6}-.+-[0-9a-f]{12}\.jsonl$")
_CONTROL: Final["re.Pattern[str]"] = re.compile(r"[\x00-\x1f\x7f-\x9f]")
FINGERPRINT_CHARS: Final[int] = 16
TEXT_MAX_CHARS: Final[int] = 300

RUN_STARTED: Final[str] = "run_started"
DECISION: Final[str] = "decision"
MODEL_CALL: Final[str] = "model_call"
MODEL_OUTPUT: Final[str] = "model_output"
ITEM_OUTCOME: Final[str] = "item_outcome"
RETRIEVAL: Final[str] = "retrieval"
TOOL_CALL: Final[str] = "tool_call"
RUN_FINISHED: Final[str] = "run_finished"

STATUS_OK: Final[str] = "ok"
STATUS_ERROR: Final[str] = "error"
OUTCOME_UNFINISHED: Final[str] = "unfinished"


def short_hash(text: str) -> str:
    """Enough of a SHA-256 to tell two texts apart, never enough to rebuild one."""
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()[:FINGERPRINT_CHARS]


def clip(text: Any) -> str:
    """Free text kept in the log is short and holds no control characters.

    A log line is printed at a terminal later, so an escape sequence in a
    file name or a query must not survive to be replayed there.
    """
    return " ".join(_CONTROL.sub(" ", str(text)).split())[:TEXT_MAX_CHARS]


def _count(value: Any) -> int:
    """A total is summed from logged values, which may be absent or not a number."""
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def resolve_log_dir(log_dir: str) -> Path:
    directory = Path(log_dir)
    return directory if directory.is_absolute() else REPO_ROOT / directory


class RunRecorder:
    """Collects the events of one run, in order."""

    def __init__(
        self,
        command: str,
        clock: Optional[Callable[[], datetime]] = None,
        run_id: Optional[str] = None,
    ) -> None:
        self.command = command
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._started = time.perf_counter()
        # Orders runs that start within one tick of the wall clock, which on
        # Windows is about 16 ms. The performance counter is shared by every
        # process on the machine and only ever moves forward.
        self.started_ns = time.perf_counter_ns()
        self._started_at = self._clock()
        self._lock = threading.Lock()
        self._events: List[Dict[str, Any]] = []
        self._labels: Tuple[Dict[str, Any], ...] = ()
        self._finished = False
        self.path: Optional[Path] = None

    @property
    def events(self) -> Tuple[Dict[str, Any], ...]:
        with self._lock:
            return tuple(self._events)

    @property
    def finished(self) -> bool:
        return self._finished

    def emit(self, kind: str, **data: Any) -> None:
        try:
            labels: Dict[str, Any] = {}
            for layer in self._labels:
                labels.update(layer)
            with self._lock:
                self._events.append({
                    "schema": SCHEMA_VERSION,
                    "run_id": self.run_id,
                    "seq": len(self._events) + 1,
                    "at": self._clock().isoformat(timespec="milliseconds"),
                    "kind": kind,
                    **labels,
                    **data,
                })
        except Exception:  # noqa: BLE001 - recording must never break the run it records
            logger.warning("A run log event could not be recorded", exc_info=True)

    @contextmanager
    def labelled(self, **labels: Any) -> Iterator[None]:
        """Attach these fields to every event emitted inside the block."""
        previous = self._labels
        self._labels = previous + (labels,)
        try:
            yield
        finally:
            self._labels = previous

    def totals(self) -> Dict[str, Any]:
        events = self.events
        model = [e for e in events if e["kind"] == MODEL_CALL]
        tools = [e for e in events if e["kind"] == TOOL_CALL]
        return {
            "events": len(events),
            "model_calls": len(model),
            "model_errors": sum(1 for e in model if e.get("status") == STATUS_ERROR),
            "model_latency_ms": sum(_count(e.get("latency_ms")) for e in model),
            "prompt_tokens": sum(_count(e.get("prompt_tokens")) for e in model),
            "output_tokens": sum(_count(e.get("output_tokens")) for e in model),
            "tool_calls": len(tools),
            "tool_errors": sum(1 for e in tools if e.get("status") == STATUS_ERROR),
            "retrievals": sum(1 for e in events if e["kind"] == RETRIEVAL),
            "decisions": sum(1 for e in events if e["kind"] == DECISION),
        }

    def finish(self, outcome: str, **data: Any) -> None:
        """The last event of the run. Only the first call counts."""
        if self._finished:
            return
        totals = self.totals()
        self.emit(
            RUN_FINISHED,
            outcome=outcome,
            seconds=round(time.perf_counter() - self._started, 3),
            **data,
            totals=totals,
        )
        self._finished = True

    def write(self, directory: Path) -> Optional[Path]:
        """One JSON object per line. Returns None if the log could not be written."""
        stamp = self._started_at.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")
        slug = re.sub(r"[^a-z0-9]+", "-", self.command.lower()).strip("-") or "run"
        path = directory / f"{stamp}-{slug}-{self.run_id}{LOG_SUFFIX}"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            # ensure_ascii, so text that cannot be encoded (a lone surrogate
            # in a file name) is escaped instead of failing the write.
            lines = [json.dumps(event, ensure_ascii=True, default=str) for event in self.events]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except Exception:  # noqa: BLE001 - a log that cannot be written must not fail the run
            logger.warning("The run log could not be written to %s", directory, exc_info=True)
            return None
        self.path = path
        return path


_ACTIVE: ContextVar[Optional[RunRecorder]] = ContextVar("procurecheck_run_recorder", default=None)


def active() -> Optional[RunRecorder]:
    return _ACTIVE.get()


def emit(kind: str, **data: Any) -> None:
    """Record an event on the run in progress. Does nothing outside a run."""
    recorder = _ACTIVE.get()
    if recorder is not None:
        recorder.emit(kind, **data)


@contextmanager
def labelled(**labels: Any) -> Iterator[None]:
    recorder = _ACTIVE.get()
    if recorder is None:
        yield
        return
    with recorder.labelled(**labels):
        yield


def purge_expired(directory: Path, retention_days: int, now: Optional[datetime] = None) -> int:
    """Delete run logs older than the retention period. Returns how many."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    removed = 0
    try:
        candidates = [p for p in directory.glob(f"*{LOG_SUFFIX}") if LOG_NAME.match(p.name)]
    except OSError:
        return 0
    for path in candidates:
        try:
            if datetime.fromtimestamp(path.stat().st_mtime, timezone.utc) < cutoff:
                path.unlink()
                removed += 1
        except (OSError, OverflowError, ValueError):
            logger.warning("An expired run log could not be deleted: %s", path.name)
    return removed


def run_header(
    settings: Settings,
    *,
    role: Optional[str] = None,
    user: Optional[str] = None,
    submission_name: Optional[str] = None,
    document_text: Optional[str] = None,
    pages: Optional[int] = None,
    checklist_items: Optional[int] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """What a reader needs to reproduce the run: the build, the model, the prompts."""
    header: Dict[str, Any] = {
        "version": __version__,
        "model": settings.model,
        "pipeline": settings.pipeline_label,
        "prompt_version": settings.resolved_prompt_version,
        "adjudicator_prompt_version": settings.adjudicator_prompt_version if settings.adjudicate else None,
        "strategy": settings.strategy,
        "temperature": settings.temperature,
        "top_p": settings.top_p,
        "max_output_tokens": settings.max_output_tokens,
        "context_tokens": settings.context_tokens,
        "human_review_threshold": settings.human_review_threshold,
        "role": role,
        "user": user,
        "checklist_items": checklist_items,
    }
    if submission_name is not None:
        header["submission"] = {
            "name": clip(submission_name),
            "sha256": None if document_text is None else short_hash(document_text),
            "characters": None if document_text is None else len(document_text),
            "pages": pages,
        }
    header.update(extra)
    return header


@contextmanager
def recording(command: str, settings: Settings, **header: Any) -> Iterator[RunRecorder]:
    """Record one run. The log is written when the block ends, however it ends.

    The caller reports the outcome with recorder.finish(...). A block that
    ends without one, or with an exception, is still logged, with what is known.
    """
    recorder = RunRecorder(command)
    try:
        recorder.emit(RUN_STARTED, command=command, started_ns=recorder.started_ns, **run_header(settings, **header))
    except Exception:  # noqa: BLE001 - a header that cannot be built must not stop the run
        logger.warning("The run log header could not be recorded", exc_info=True)
    token = _ACTIVE.set(recorder)
    try:
        yield recorder
    except BaseException as exc:
        _safely(recorder.finish, STATUS_ERROR, error_kind=type(exc).__name__)
        raise
    finally:
        _ACTIVE.reset(token)
        _safely(_close, recorder, settings)


def _close(recorder: RunRecorder, settings: Settings) -> None:
    recorder.finish(OUTCOME_UNFINISHED)
    if settings.logs_enabled:
        directory = resolve_log_dir(settings.log_dir)
        recorder.write(directory)
        purge_expired(directory, settings.log_retention_days)


def _safely(action: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Closing a log happens while a run's own result, or its own error, is on
    its way out. Nothing raised here may replace either."""
    try:
        action(*args, **kwargs)
    except Exception:  # noqa: BLE001
        logger.warning("The run log could not be closed", exc_info=True)
