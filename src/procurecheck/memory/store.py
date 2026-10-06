"""The case history store: what is kept between runs, and for how long.

One row per finished check of a submission. The fields, and why each is kept:

    submission_id            finds the earlier checks of the same submission
    document_name            tells the officer which file was checked
    document_type            the kind of document the checklist was applied to
    document_sha256          shows whether the text changed, without keeping it
    items (item, status)     the earlier result the new one is set beside
    completeness_percentage  the earlier headline figure
    overall_status           Complete, Incomplete or Needs Review
    stop_reason              how the earlier run ended
    recorded_by              who ran it
    recorded_at              when; retention is counted from here
    app_version              which build produced it

Deliberately not kept: the document text, any quotation from it, and the
model's written reasons, which can quote it. A bid can carry personal and
commercial detail, and none of it is needed to say what changed.

The store is a single SQLite file, so it needs no server and nothing to
install. Every query is parameterised. Records older than the retention period
are deleted the next time the store is opened for any operation, so an expired
record is never recalled even if nobody ran `memory purge`. Each deletion is
logged with a time, a user and a count, and not with the submission it removed.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import unicodedata
from contextlib import closing, contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Final, Iterator, List, Optional, Tuple

from ..checklists import REPO_ROOT
from ..tools.contracts import ItemPresence

SCHEMA_VERSION: Final[int] = 1
STORE_FILENAME: Final[str] = "case-history.sqlite3"
BUSY_TIMEOUT_SECONDS: Final[float] = 5.0
OWNER_ONLY: Final[int] = 0o600
SUBMISSION_ID_MAX_CHARS: Final[int] = 120
TEXT_MAX_CHARS: Final[int] = 300

CAUSE_FORGET: Final[str] = "forget"
CAUSE_RETENTION: Final[str] = "retention"
RETENTION_ACTOR: Final[str] = "retention"

_SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS cases (
    case_id INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id TEXT NOT NULL COLLATE NOCASE,
    document_name TEXT NOT NULL,
    document_type TEXT NOT NULL,
    document_sha256 TEXT NOT NULL,
    completeness_percentage REAL NOT NULL,
    overall_status TEXT NOT NULL,
    stop_reason TEXT NOT NULL,
    recorded_by TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    app_version TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS cases_by_submission ON cases (submission_id, case_id);
CREATE INDEX IF NOT EXISTS cases_by_time ON cases (recorded_at);
CREATE TABLE IF NOT EXISTS case_items (
    case_id INTEGER NOT NULL REFERENCES cases (case_id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    item TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (case_id, position)
);
CREATE TABLE IF NOT EXISTS deletions (
    deletion_id INTEGER PRIMARY KEY AUTOINCREMENT,
    deleted_at TEXT NOT NULL,
    deleted_by TEXT NOT NULL,
    cause TEXT NOT NULL,
    cases_removed INTEGER NOT NULL
);
"""

_CASE_COLUMNS: Final[str] = (
    "case_id, submission_id, document_name, document_type, document_sha256, "
    "completeness_percentage, overall_status, stop_reason, recorded_by, recorded_at, app_version"
)


class MemoryUnavailableError(Exception):
    """The store could not be opened, read or written.

    Callers treat this as "no memory this time": the check still runs and its
    result is unaffected.
    """


def fingerprint(text: str) -> str:
    """SHA-256 of the extracted text: enough to tell two versions apart.

    A PDF extractor can emit a lone surrogate, which plain UTF-8 refuses to
    encode; surrogatepass keeps the fingerprint defined for any text.
    """
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def clean(text: str) -> str:
    """Stored text is shown at a terminal later, so control characters go."""
    cleaned = "".join(" " if unicodedata.category(c).startswith("C") else c for c in text)
    return " ".join(cleaned.split())[:TEXT_MAX_CHARS]


def validate_submission_id(raw: str) -> str:
    """The identifier an officer chooses to tie a resubmission to its case."""
    value = clean(raw)
    if not value:
        raise ValueError("The submission id is empty.")
    if len(raw.strip()) > SUBMISSION_ID_MAX_CHARS:
        raise ValueError(f"The submission id is longer than {SUBMISSION_ID_MAX_CHARS} characters.")
    return value


def resolve_store_path(memory_dir: str) -> Path:
    """A relative directory is taken from the repository root, not from
    wherever the command happened to be run."""
    directory = Path(memory_dir)
    if not directory.is_absolute():
        directory = REPO_ROOT / directory
    return directory / STORE_FILENAME


@dataclass(frozen=True)
class CaseItem:
    item: str
    status: ItemPresence


@dataclass(frozen=True)
class CaseRecord:
    """One finished check of one submission."""

    submission_id: str
    document_name: str
    document_type: str
    document_sha256: str
    items: Tuple[CaseItem, ...]
    completeness_percentage: float
    overall_status: str
    stop_reason: str
    recorded_by: str
    recorded_at: datetime
    app_version: str
    case_id: Optional[int] = None

    def to_trace(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "submission_id": self.submission_id,
            "document_name": self.document_name,
            "document_type": self.document_type,
            "document_sha256": self.document_sha256,
            "completeness_percentage": self.completeness_percentage,
            "overall_status": self.overall_status,
            "stop_reason": self.stop_reason,
            "recorded_by": self.recorded_by,
            "recorded_at": self.recorded_at.isoformat(timespec="seconds"),
            "app_version": self.app_version,
            "items": [{"item": i.item, "status": i.status.value} for i in self.items],
        }


@dataclass(frozen=True)
class SubmissionSummary:
    submission_id: str
    checks: int
    last_checked: datetime
    last_status: str


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def _to_second(moment: datetime) -> datetime:
    """UTC, to the second: the precision the store keeps."""
    return _utc(moment).astimezone(timezone.utc).replace(microsecond=0)


def _stamp(moment: datetime) -> str:
    """Fixed-width UTC text, so the stored times sort as times."""
    return _to_second(moment).strftime("%Y-%m-%dT%H:%M:%S+00:00")


class CaseHistoryStore:
    def __init__(
        self,
        path: Path,
        retention_days: int,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if retention_days < 1:
            raise ValueError("retention_days must be at least 1")
        self._path = Path(path)
        self._retention = timedelta(days=retention_days)
        self._retention_days = retention_days
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def path(self) -> Path:
        return self._path

    @property
    def retention_days(self) -> int:
        return self._retention_days

    @contextmanager
    def _session(self, purge: bool = True) -> Iterator[sqlite3.Connection]:
        """One transaction, with expired records already gone."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            is_new = not self._path.exists()
            connection = sqlite3.connect(self._path, timeout=BUSY_TIMEOUT_SECONDS)
        except (sqlite3.Error, OSError) as exc:
            raise MemoryUnavailableError(f"The case history could not be opened: {exc}") from exc
        try:
            with closing(connection):
                if is_new:
                    self._restrict_to_owner()
                connection.execute("PRAGMA foreign_keys = ON")
                # A deleted record is overwritten with zeros rather than left
                # readable in the file's free pages.
                connection.execute("PRAGMA secure_delete = ON")
                with connection:
                    self._migrate(connection)
                    if purge:
                        self._purge(connection)
                    yield connection
        except sqlite3.Error as exc:
            raise MemoryUnavailableError(f"The case history could not be used: {exc}") from exc

    def _restrict_to_owner(self) -> None:
        # Effective on POSIX. On Windows the file inherits the folder's
        # access list, which is the control there.
        try:
            os.chmod(self._path, OWNER_ONLY)
        except OSError:
            pass

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == SCHEMA_VERSION:
            return
        if version != 0:
            raise MemoryUnavailableError(
                f"The case history was written by a different version (schema {version}, "
                f"this build reads schema {SCHEMA_VERSION})."
            )
        # Every statement is IF NOT EXISTS, so two first runs at once, or a
        # run interrupted before the version is set, leave a usable store.
        connection.executescript(_SCHEMA)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _purge(self, connection: sqlite3.Connection) -> int:
        cutoff = _stamp(self._clock() - self._retention)
        removed = connection.execute("DELETE FROM cases WHERE recorded_at < ?", (cutoff,)).rowcount
        connection.execute("DELETE FROM deletions WHERE deleted_at < ?", (cutoff,))
        if removed:
            self._log_deletion(connection, RETENTION_ACTOR, CAUSE_RETENTION, removed)
        return removed

    def _log_deletion(self, connection: sqlite3.Connection, by: str, cause: str, removed: int) -> None:
        connection.execute(
            "INSERT INTO deletions (deleted_at, deleted_by, cause, cases_removed) VALUES (?, ?, ?, ?)",
            (_stamp(self._clock()), clean(by), cause, removed),
        )

    @staticmethod
    def _read(connection: sqlite3.Connection, row: Tuple[Any, ...]) -> CaseRecord:
        item_rows = connection.execute(
            "SELECT item, status FROM case_items WHERE case_id = ? ORDER BY position", (row[0],)
        ).fetchall()
        try:
            items = tuple(CaseItem(item, ItemPresence(status)) for item, status in item_rows)
            recorded_at = datetime.fromisoformat(row[9])
        except (ValueError, TypeError) as exc:
            # A status or time the application never writes means the file was
            # edited or damaged. The record is not trusted in part.
            raise MemoryUnavailableError(f"Stored case {row[0]} could not be read: {exc}") from exc
        return CaseRecord(
            case_id=row[0], submission_id=row[1], document_name=row[2], document_type=row[3],
            document_sha256=row[4], completeness_percentage=row[5], overall_status=row[6],
            stop_reason=row[7], recorded_by=row[8], recorded_at=recorded_at, app_version=row[10],
            items=items,
        )

    def remember(self, record: CaseRecord) -> CaseRecord:
        """Append one case. Earlier cases of the same submission are kept."""
        if not record.items:
            raise ValueError("A case with no checklist items is not remembered.")
        submission_id = validate_submission_id(record.submission_id)
        with self._session() as connection:
            cursor = connection.execute(
                "INSERT INTO cases (submission_id, document_name, document_type, document_sha256, "
                "completeness_percentage, overall_status, stop_reason, recorded_by, recorded_at, "
                "app_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    submission_id, clean(record.document_name), clean(record.document_type),
                    record.document_sha256, record.completeness_percentage,
                    clean(record.overall_status), clean(record.stop_reason),
                    clean(record.recorded_by), _stamp(record.recorded_at), clean(record.app_version),
                ),
            )
            case_id = cursor.lastrowid
            connection.executemany(
                "INSERT INTO case_items (case_id, position, item, status) VALUES (?, ?, ?, ?)",
                [(case_id, position, clean(i.item), i.status.value)
                 for position, i in enumerate(record.items)],
            )
        return self._as_stored(record, case_id, submission_id)

    @staticmethod
    def _as_stored(record: CaseRecord, case_id: Optional[int], submission_id: str) -> CaseRecord:
        """The record exactly as a later read will return it."""
        return replace(
            record,
            case_id=case_id,
            submission_id=submission_id,
            document_name=clean(record.document_name),
            document_type=clean(record.document_type),
            overall_status=clean(record.overall_status),
            stop_reason=clean(record.stop_reason),
            recorded_by=clean(record.recorded_by),
            recorded_at=_to_second(record.recorded_at),
            app_version=clean(record.app_version),
            items=tuple(CaseItem(clean(i.item), i.status) for i in record.items),
        )

    def history(self, submission_id: str) -> Tuple[CaseRecord, ...]:
        """Every remembered check of one submission, newest first."""
        with self._session() as connection:
            rows = connection.execute(
                f"SELECT {_CASE_COLUMNS} FROM cases WHERE submission_id = ? ORDER BY case_id DESC",
                (clean(submission_id),),
            ).fetchall()
            return tuple(self._read(connection, row) for row in rows)

    def latest(self, submission_id: str) -> Optional[CaseRecord]:
        with self._session() as connection:
            row = connection.execute(
                f"SELECT {_CASE_COLUMNS} FROM cases WHERE submission_id = ? "
                "ORDER BY case_id DESC LIMIT 1",
                (clean(submission_id),),
            ).fetchone()
            return None if row is None else self._read(connection, row)

    def submissions(self) -> Tuple[SubmissionSummary, ...]:
        """One line per submission that has a remembered check."""
        with self._session() as connection:
            rows = connection.execute(
                "SELECT c.submission_id, n.checks, c.recorded_at, c.overall_status FROM cases c "
                "JOIN (SELECT MAX(case_id) AS case_id, COUNT(*) AS checks FROM cases "
                "GROUP BY submission_id) n ON n.case_id = c.case_id ORDER BY c.case_id DESC"
            ).fetchall()
        summaries: List[SubmissionSummary] = []
        for submission_id, checks, recorded_at, status in rows:
            try:
                summaries.append(SubmissionSummary(submission_id, checks, datetime.fromisoformat(recorded_at), status))
            except (ValueError, TypeError) as exc:
                raise MemoryUnavailableError(f"A stored time could not be read: {exc}") from exc
        return tuple(summaries)

    def forget(self, submission_id: str, deleted_by: str) -> int:
        """Delete every remembered check of one submission. Returns how many."""
        with self._session() as connection:
            removed = connection.execute(
                "DELETE FROM cases WHERE submission_id = ?", (clean(submission_id),)
            ).rowcount
            if removed:
                self._log_deletion(connection, deleted_by, CAUSE_FORGET, removed)
            return removed

    def purge_expired(self) -> int:
        """Delete what is past retention now. Every other call does this too."""
        with self._session(purge=False) as connection:
            return self._purge(connection)

    def deletions(self) -> Tuple[Tuple[datetime, str, str, int], ...]:
        """The deletion log: when, by whom, why and how many. Never which."""
        with self._session() as connection:
            rows = connection.execute(
                "SELECT deleted_at, deleted_by, cause, cases_removed FROM deletions ORDER BY deletion_id"
            ).fetchall()
        try:
            return tuple((datetime.fromisoformat(at), by, cause, removed) for at, by, cause, removed in rows)
        except (ValueError, TypeError) as exc:
            raise MemoryUnavailableError(f"A stored time could not be read: {exc}") from exc
