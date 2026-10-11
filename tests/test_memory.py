"""Case history: the store, the comparison, and its place around the workflow."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from procurecheck import __version__, api
from procurecheck.cli import main
from procurecheck.config import Settings
from procurecheck.memory import (
    CaseHistoryStore,
    CaseItem,
    CaseMemory,
    CaseRecord,
    ChangeKind,
    MemoryUnavailableError,
    compare,
    fingerprint,
    resolve_store_path,
    validate_submission_id,
)
from procurecheck.memory import commands as memory_commands
from procurecheck.memory.recall import (
    NOTE_FIRST,
    NOTE_MAY_NOT_READ,
    NOTE_NO_REPORT,
    NOTE_UNREADABLE,
    NOTE_UNWRITABLE,
)
from procurecheck.tools import ReviewQueue, ToolContext, ToolExecutor, default_registry
from procurecheck.tools.contracts import ItemPresence
from procurecheck.workflow import StopReason, WorkflowInput, WorkflowLimits, WorkflowRunner
from procurecheck.workflow import commands as workflow_commands

from tool_fakes import BIDDER, COMMITTEE, DOCUMENT, ITEMS, OFFICER, TAX_TEXT, FakeOllama, StubModelClient

NOW = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)
RETENTION_DAYS = 30
TAX, BID_SECURITY = ITEMS
PRESENT, MISSING, UNCLEAR = ItemPresence.PRESENT, ItemPresence.MISSING, ItemPresence.UNCLEAR
INPUT = WorkflowInput("bid-a", "bid-a.pdf", "Bid Document", DOCUMENT, tuple(ITEMS))


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(tmp_path, clock):
    return CaseHistoryStore(tmp_path / "memory" / "cases.sqlite3", RETENTION_DAYS, clock)


def case(submission_id="bid-a", statuses=(PRESENT, MISSING), recorded_at=NOW, text=DOCUMENT, version=__version__):
    items = tuple(CaseItem(item, status) for item, status in zip(ITEMS, statuses))
    present = sum(1 for s in statuses if s is PRESENT)
    return CaseRecord(
        submission_id=submission_id, document_name=f"{submission_id}.pdf", document_type="Bid Document",
        document_sha256=fingerprint(text), items=items,
        completeness_percentage=round(100.0 * present / len(statuses), 1),
        overall_status="Incomplete", stop_reason="report_ready", recorded_by="officer-1",
        recorded_at=recorded_at, app_version=version,
    )


def run(store, client=None, principal=OFFICER, workflow_input=INPUT, clock=None):
    context = ToolContext(Settings(), client or StubModelClient(), review_queue=ReviewQueue())
    memory = None if store is None else CaseMemory(store, __version__, clock)
    runner = WorkflowRunner(
        ToolExecutor(default_registry(), context), WorkflowLimits(retry_delay_seconds=0),
        sleep=lambda _s: None, memory=memory,
    )
    return runner.run(workflow_input, principal)


class EverythingPresent(StubModelClient):
    """A resubmission in which the bid securing declaration has arrived."""

    def complete_structured(self, system_prompt, user_message, schema):
        answer = super().complete_structured(system_prompt, user_message, schema)
        if hasattr(answer, "is_present") and not answer.is_present:
            return answer.model_copy(update={
                "is_present": True, "page_number": 2, "extracted_snippet": TAX_TEXT,
                "confidence_score": 0.95,
            })
        return answer


class TestStore:
    def test_a_remembered_case_is_read_back_as_it_was_written(self, store):
        stored = store.remember(case())
        assert stored.case_id == 1
        assert store.latest("bid-a") == stored

    def test_latest_is_the_newest_and_history_is_newest_first(self, store, clock):
        first = store.remember(case())
        clock.advance(days=1)
        second = store.remember(case(statuses=(PRESENT, PRESENT), recorded_at=clock.now))
        assert store.latest("bid-a") == second
        assert store.history("bid-a") == (second, first)

    def test_one_submission_never_sees_another(self, store):
        store.remember(case("bid-a"))
        store.remember(case("bid-b", statuses=(MISSING, MISSING)))
        assert [c.submission_id for c in store.history("bid-a")] == ["bid-a"]
        assert store.latest("bid-c") is None

    def test_the_submission_id_matches_whatever_its_letter_case(self, store):
        store.remember(case("Bid-A"))
        assert store.latest("bid-a") is not None

    def test_submissions_lists_one_line_each_with_the_latest_status(self, store, clock):
        store.remember(case("bid-a"))
        clock.advance(hours=1)
        store.remember(case("bid-a", recorded_at=clock.now))
        store.remember(case("bid-b", recorded_at=clock.now))
        summary = {s.submission_id: s.checks for s in store.submissions()}
        assert summary == {"bid-a": 2, "bid-b": 1}

    def test_a_case_past_retention_is_never_recalled(self, store, clock):
        store.remember(case())
        clock.advance(days=RETENTION_DAYS + 1)
        assert store.latest("bid-a") is None
        assert store.history("bid-a") == ()

    def test_a_case_inside_retention_is_kept(self, store, clock):
        store.remember(case())
        clock.advance(days=RETENTION_DAYS - 1)
        assert store.latest("bid-a") is not None

    def test_purge_reports_how_many_it_deleted_and_logs_a_count_only(self, store, clock):
        store.remember(case("bid-a"))
        store.remember(case("bid-b"))
        clock.advance(days=RETENTION_DAYS + 1)
        assert store.purge_expired() == 2
        (_at, by, cause, removed), = store.deletions()
        assert (by, cause, removed) == ("retention", "retention", 2)

    def test_forget_deletes_every_case_of_one_submission_and_its_items(self, store):
        store.remember(case("bid-a"))
        store.remember(case("bid-a"))
        store.remember(case("bid-b"))
        assert store.forget("bid-a", deleted_by="officer-1") == 2
        assert store.latest("bid-a") is None and store.latest("bid-b") is not None
        with sqlite3.connect(store.path) as connection:
            assert connection.execute("SELECT COUNT(*) FROM case_items").fetchone()[0] == len(ITEMS)

    def test_the_deletion_log_does_not_name_the_submission(self, store):
        store.remember(case("bid-secret"))
        store.forget("bid-secret", deleted_by="officer-1")
        with sqlite3.connect(store.path) as connection:
            dump = "\n".join(connection.iterdump())
        assert "bid-secret" not in dump

    def test_forgetting_something_unknown_deletes_nothing(self, store):
        assert store.forget("never-seen", deleted_by="officer-1") == 0
        assert store.deletions() == ()

    def test_a_submission_id_cannot_inject_sql(self, store):
        store.remember(case("bid-a"))
        assert store.forget("x' OR '1'='1", deleted_by="officer-1") == 0
        assert store.latest("bid-a") is not None

    def test_control_characters_are_stripped_before_storing(self, store):
        stored = store.remember(CaseRecord(**{
            **case().__dict__, "document_name": "bid\x1b[31m.pdf\nOverall status: Complete",
        }))
        assert store.latest("bid-a").document_name == "bid [31m.pdf Overall status: Complete"
        assert stored.case_id is not None

    def test_a_case_with_no_items_is_not_remembered(self, store):
        with pytest.raises(ValueError):
            store.remember(CaseRecord(**{**case().__dict__, "items": ()}))

    def test_a_file_that_is_not_a_database_is_reported_not_crashed_on(self, tmp_path):
        path = tmp_path / "cases.sqlite3"
        path.write_text("this is not a database, and it is long enough to be read as a header")
        with pytest.raises(MemoryUnavailableError):
            CaseHistoryStore(path, RETENTION_DAYS).latest("bid-a")

    def test_a_status_the_application_never_writes_makes_the_case_unreadable(self, store):
        store.remember(case())
        with sqlite3.connect(store.path) as connection:
            connection.execute("UPDATE case_items SET status = 'Approved'")
        with pytest.raises(MemoryUnavailableError):
            store.latest("bid-a")

    def test_a_store_from_a_newer_schema_is_refused(self, store):
        store.remember(case())
        with sqlite3.connect(store.path) as connection:
            connection.execute("PRAGMA user_version = 99")
        with pytest.raises(MemoryUnavailableError):
            store.latest("bid-a")

    def test_a_forgotten_case_is_gone_from_the_file_itself(self, store):
        store.remember(case("bid-secret-7731"))
        store.forget("bid-secret-7731", deleted_by="officer-1")
        raw = store.path.read_bytes()
        assert b"bid-secret-7731" not in raw and TAX.encode() not in raw

    def test_a_store_left_half_created_still_opens(self, store):
        store.remember(case())
        with sqlite3.connect(store.path) as connection:
            connection.execute("PRAGMA user_version = 0")
        assert store.latest("bid-a") is not None

    def test_a_time_that_is_not_text_makes_the_case_unreadable(self, store):
        store.remember(case())
        with sqlite3.connect(store.path) as connection:
            connection.execute("UPDATE cases SET recorded_at = X'FFFF'")
        with pytest.raises(MemoryUnavailableError):
            store.latest("bid-a")

    def test_text_with_a_lone_surrogate_still_has_a_fingerprint(self):
        assert len(fingerprint("a\ud800b")) == 64

    def test_retention_must_be_at_least_a_day(self, tmp_path):
        with pytest.raises(ValueError):
            CaseHistoryStore(tmp_path / "x.sqlite3", 0)

    @pytest.mark.parametrize("raw", ["", "   ", "\x00\x1b", "x" * 121])
    def test_a_blank_or_oversized_submission_id_is_refused(self, raw):
        with pytest.raises(ValueError):
            validate_submission_id(raw)

    def test_a_relative_memory_dir_is_taken_from_the_repository_root(self):
        path = resolve_store_path("data/memory")
        assert path.is_absolute() and path.parent.name == "memory"


class TestCompare:
    def kinds(self, before, after, **kwargs):
        previous = case(statuses=before, **kwargs)
        current = tuple(CaseItem(item, status) for item, status in zip(ITEMS, after))
        return compare(previous, current, fingerprint(DOCUMENT), __version__)

    @pytest.mark.parametrize("before,after,kind", [
        (MISSING, PRESENT, ChangeKind.NOW_PRESENT),
        (UNCLEAR, PRESENT, ChangeKind.NOW_PRESENT),
        (PRESENT, MISSING, ChangeKind.NO_LONGER_PRESENT),
        (PRESENT, UNCLEAR, ChangeKind.NO_LONGER_PRESENT),
        (MISSING, MISSING, ChangeKind.STILL_MISSING),
        (UNCLEAR, UNCLEAR, ChangeKind.STILL_UNCLEAR),
        (PRESENT, PRESENT, ChangeKind.STILL_PRESENT),
        (MISSING, UNCLEAR, ChangeKind.STATUS_CHANGED),
        (UNCLEAR, MISSING, ChangeKind.STATUS_CHANGED),
    ])
    def test_each_pair_of_statuses_has_one_meaning(self, before, after, kind):
        comparison = self.kinds((PRESENT, before), (PRESENT, after))
        assert comparison.changes[1].kind is kind

    def test_a_changed_checklist_shows_new_and_dropped_items(self):
        previous = case()
        current = (CaseItem(TAX, PRESENT), CaseItem("Powers of attorney", MISSING))
        comparison = compare(previous, current, fingerprint(DOCUMENT), __version__)
        assert [c.kind for c in comparison.changes] == [
            ChangeKind.STILL_PRESENT, ChangeKind.NEW_ITEM, ChangeKind.NOT_CHECKED_NOW,
        ]
        assert comparison.changes[2].item == BID_SECURITY

    def test_items_match_whatever_their_letter_case_or_spacing(self):
        previous = case()
        current = (CaseItem(f"  {TAX.upper()} ", PRESENT), CaseItem(BID_SECURITY, MISSING))
        comparison = compare(previous, current, fingerprint(DOCUMENT), __version__)
        assert not comparison.of(ChangeKind.NEW_ITEM)

    def test_an_item_matches_its_stored_form_after_cleaning(self, store):
        messy = "Tax  clearance\ncertificate"
        stored = store.remember(CaseRecord(**{**case().__dict__, "items": (CaseItem(messy, MISSING),)}))
        comparison = compare(stored, (CaseItem(messy, PRESENT),), fingerprint(DOCUMENT), __version__)
        assert [c.kind for c in comparison.changes] == [ChangeKind.NOW_PRESENT]

    def test_a_changed_document_is_said_to_have_changed(self):
        comparison = self.kinds((PRESENT, MISSING), (PRESENT, PRESENT), text="an earlier version")
        assert not comparison.same_document and not comparison.inconsistent
        assert "The document text has changed since then." in comparison.lines()

    def test_the_same_text_with_a_different_answer_is_flagged_for_a_human(self):
        comparison = self.kinds((PRESENT, MISSING), (PRESENT, PRESENT))
        assert comparison.same_document
        assert [c.item for c in comparison.inconsistent] == [BID_SECURITY]
        assert any("check those items by hand" in line for line in comparison.lines())

    def test_a_different_version_is_called_out(self):
        comparison = self.kinds((PRESENT, MISSING), (PRESENT, MISSING), version="0.3.1")
        assert not comparison.same_version
        assert any("different version" in line for line in comparison.lines())

    def test_the_lines_say_what_arrived_what_is_outstanding_and_that_it_is_advisory(self):
        lines = self.kinds((MISSING, MISSING), (PRESENT, MISSING), text="earlier").lines()
        assert f"Now present, was Missing: {TAX}" in lines
        assert f"Still missing: {BID_SECURITY}" in lines
        assert lines[-1].startswith("This comparison is advisory")

    def test_a_regression_asks_for_a_check_by_hand(self):
        lines = self.kinds((PRESENT, PRESENT), (PRESENT, MISSING), text="earlier").lines()
        assert any(line.startswith("No longer present") and "Confirm by hand" in line for line in lines)


class TestWorkflowMemory:
    def test_the_first_run_recalls_nothing_and_remembers_the_check(self, store):
        result = run(store)
        assert result.memory.recalled is None and result.memory.comparison is None
        assert NOTE_FIRST in result.memory.notes
        remembered = store.latest("bid-a")
        assert remembered == result.memory.stored
        assert [(i.item, i.status) for i in remembered.items] == [(TAX, PRESENT), (BID_SECURITY, MISSING)]
        assert remembered.recorded_by == OFFICER.user_id and remembered.app_version == __version__

    def test_the_second_run_shows_what_changed_since_the_first(self, store):
        run(store)
        resubmitted = WorkflowInput("bid-a", "bid-a-v2.pdf", "Bid Document", DOCUMENT + "\nMore.", tuple(ITEMS))
        result = run(store, EverythingPresent(), workflow_input=resubmitted)
        comparison = result.memory.comparison
        assert not comparison.same_document
        assert [c.item for c in comparison.of(ChangeKind.NOW_PRESENT)] == [BID_SECURITY]
        assert f"Now present, was Missing: {BID_SECURITY}" in result.memory.lines()
        assert len(store.history("bid-a")) == 2

    def test_an_earlier_all_present_case_cannot_make_a_missing_item_present(self, store):
        store.remember(case(statuses=(PRESENT, PRESENT)))
        with_memory, without = run(store), run(None)
        assert with_memory.check == without.check
        assert with_memory.report == without.report
        assert with_memory.report.report.missing_items == [BID_SECURITY]

    def test_memory_changes_no_decision_no_handoff_and_no_stop(self, store):
        store.remember(case(statuses=(PRESENT, PRESENT)))
        with_memory, without = run(store), run(None)
        assert [s.decision for s in with_memory.steps] == [s.decision for s in without.steps]
        assert [s.sensed for s in with_memory.steps] == [s.sensed for s in without.steps]
        assert with_memory.handoff == without.handoff
        assert with_memory.stop_reason is without.stop_reason

    def test_the_model_is_never_shown_the_earlier_case(self, store):
        store.remember(CaseRecord(**{**case().__dict__, "document_name": "CANARY-EARLIER-CASE.pdf"}))

        class Recording(StubModelClient):
            prompts = []

            def complete_structured(self, system_prompt, user_message, schema):
                Recording.prompts.append(system_prompt + user_message)
                return super().complete_structured(system_prompt, user_message, schema)

        result = run(store, Recording())
        assert result.memory.recalled is not None and Recording.prompts
        assert not any("CANARY" in prompt or "Earlier check" in prompt for prompt in Recording.prompts)

    def test_no_document_text_and_no_reason_is_written_to_the_store(self, store):
        run(store)
        raw = store.path.read_bytes()
        assert TAX_TEXT.encode() not in raw and b"TCC/2026/00417" not in raw
        assert b"SYN/2026/001" not in raw

    def test_a_bidder_is_refused_and_leaves_no_trace_in_memory(self, store):
        result = run(store, principal=BIDDER)
        assert result.stop_reason is StopReason.UNAUTHORIZED
        assert NOTE_MAY_NOT_READ in result.memory.notes and NOTE_NO_REPORT in result.memory.notes
        assert store.submissions() == ()

    def test_a_role_without_history_rights_recalls_nothing(self, store):
        store.remember(case())
        recalled = CaseMemory(store, __version__).recall("bid-a", COMMITTEE)
        assert recalled.previous is None and recalled.notes == (NOTE_MAY_NOT_READ,)
        assert CaseMemory(store, __version__).recall("bid-a", None).previous is None

    def test_a_run_that_reaches_no_report_is_not_remembered(self, store):
        result = run(store, StubModelClient(unavailable=True))
        assert result.stop_reason is StopReason.SERVICE_UNAVAILABLE
        assert result.memory.stored is None and NOTE_NO_REPORT in result.memory.notes
        assert store.submissions() == ()

    def test_a_broken_store_costs_the_comparison_and_nothing_else(self, tmp_path):
        path = tmp_path / "cases.sqlite3"
        path.write_text("this is not a database, and it is long enough to be read as a header")
        result = run(CaseHistoryStore(path, RETENTION_DAYS))
        assert result.ok and result.report.report.missing_items == [BID_SECURITY]
        assert result.memory.notes == (NOTE_UNREADABLE, NOTE_UNWRITABLE)
        assert result.memory.stored is None

    def test_any_fault_in_the_store_is_contained(self, store, monkeypatch):
        def explode(*_args, **_kwargs):
            raise RuntimeError("an error nobody listed")

        monkeypatch.setattr(store, "latest", explode)
        monkeypatch.setattr(store, "remember", explode)
        result = run(store)
        assert result.ok and result.memory.notes == (NOTE_UNREADABLE, NOTE_UNWRITABLE)

    def test_a_document_with_a_lone_surrogate_is_still_remembered(self, store):
        odd = WorkflowInput("bid-a", "bid-a.pdf", "Bid Document", DOCUMENT + "\ud800", tuple(ITEMS))
        result = run(store, workflow_input=odd)
        assert result.ok and result.memory.stored is not None

    def test_the_trace_records_what_memory_did_and_that_the_planner_did_not_use_it(self, store):
        run(store)
        trace = run(store).to_trace()["memory"]
        assert trace["used_by_planner"] is False
        assert trace["recalled"]["case_id"] == 1 and trace["stored_case_id"] == 2
        assert trace["comparison"]["same_document"] is True
        assert trace["comparison"]["inconsistent_items"] == []
        json.dumps(trace)

    def test_without_memory_the_trace_says_so(self):
        assert run(None).to_trace()["memory"] is None


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow_commands, "OllamaClient", FakeOllama)
    submission = tmp_path / "bid.txt"
    submission.write_text(DOCUMENT, encoding="utf-8")
    checklist = tmp_path / "checklist.txt"
    checklist.write_text("\n".join(ITEMS), encoding="utf-8")
    return submission, checklist, tmp_path / "trace.json"


def workflow(files, *extra):
    submission, checklist, trace = files
    return main(["workflow", "--submission", str(submission), "--checklist", str(checklist),
                 "--trace", str(trace), "--retry-delay", "0", *extra])


def trace_of(files):
    return json.loads(files[2].read_text(encoding="utf-8"))


class TestWorkflowCommand:
    def test_two_runs_of_one_submission_end_in_a_comparison(self, files, capsys):
        assert workflow(files) == 0
        assert trace_of(files)["memory"]["recalled"] is None
        assert workflow(files) == 0
        memory = trace_of(files)["memory"]
        assert memory["recalled"]["submission_id"] == "bid" and memory["stored_case_id"] == 2
        captured = capsys.readouterr()
        assert "Case history:" in captured.out and "Earlier check:" in captured.out
        assert "Case history: on for submission bid" in captured.err

    def test_a_submission_id_ties_a_renamed_file_to_its_case(self, files):
        assert workflow(files, "--submission-id", "SYN-2026-001") == 0
        renamed = files[0].with_name("bid-resubmitted.txt")
        renamed.write_text(DOCUMENT, encoding="utf-8")
        assert workflow((renamed, files[1], files[2]), "--submission-id", "SYN-2026-001") == 0
        trace = trace_of(files)
        assert trace["submission_id"] == "SYN-2026-001"
        assert trace["memory"]["recalled"]["document_name"] == "bid.txt"

    def test_no_memory_recalls_nothing_and_writes_nothing(self, files, tmp_path, capsys):
        assert workflow(files, "--no-memory") == 0
        assert trace_of(files)["memory"] is None
        assert not (tmp_path / "case-history").exists()
        assert "Case history: off" in capsys.readouterr().err

    def test_the_environment_can_turn_memory_off(self, files, tmp_path, monkeypatch):
        monkeypatch.setenv("PROCURECHECK_MEMORY", "off")
        assert workflow(files) == 0
        assert trace_of(files)["memory"] is None and not (tmp_path / "case-history").exists()

    def test_a_blank_submission_id_is_an_input_error(self, files):
        assert workflow(files, "--submission-id", "   ") == 1

    def test_a_retention_below_one_day_is_a_configuration_error(self, files, monkeypatch):
        monkeypatch.setenv("PROCURECHECK_MEMORY_RETENTION_DAYS", "0")
        assert workflow(files) == 1


class _Terminal:
    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


class TestMemoryCommand:
    def test_list_says_when_nothing_is_remembered(self, capsys):
        assert main(["memory", "list"]) == 0
        assert "Nothing is remembered" in capsys.readouterr().out

    def test_list_and_show_after_a_run(self, files, capsys):
        workflow(files)
        capsys.readouterr()
        assert main(["memory", "list"]) == 0
        assert "bid: 1 check(s)" in capsys.readouterr().out
        assert main(["memory", "show", "--submission-id", "bid"]) == 0
        out = capsys.readouterr().out
        assert f"- Present: {TAX}" in out and f"- Missing: {BID_SECURITY}" in out

    def test_show_of_an_unknown_submission_exits_1(self, capsys):
        assert main(["memory", "show", "--submission-id", "absent"]) == 1
        assert "No check of absent is remembered" in capsys.readouterr().out

    def test_forget_asks_for_the_submission_id_to_be_typed(self, files, monkeypatch, capsys):
        workflow(files)
        monkeypatch.setattr("sys.stdin", _Terminal(True))
        monkeypatch.setattr("builtins.input", lambda _prompt: "bid")
        assert main(["memory", "forget", "--submission-id", "bid"]) == 0
        assert "Deleted 1 remembered check(s) of bid." in capsys.readouterr().out
        assert main(["memory", "show", "--submission-id", "bid"]) == 1

    def test_forget_with_the_wrong_id_typed_deletes_nothing(self, files, monkeypatch):
        workflow(files)
        monkeypatch.setattr("sys.stdin", _Terminal(True))
        monkeypatch.setattr("builtins.input", lambda _prompt: "yes")
        assert main(["memory", "forget", "--submission-id", "bid"]) == 1
        assert main(["memory", "show", "--submission-id", "bid"]) == 0

    def test_forget_with_no_one_at_the_terminal_needs_yes(self, files, monkeypatch):
        workflow(files)
        monkeypatch.setattr("sys.stdin", _Terminal(False))
        assert main(["memory", "forget", "--submission-id", "bid"]) == 1
        assert main(["memory", "forget", "--submission-id", "bid", "--yes"]) == 0

    def test_forget_confirms_against_the_id_as_stored(self, files, monkeypatch):
        workflow(files)
        monkeypatch.setattr("sys.stdin", _Terminal(True))
        monkeypatch.setattr("builtins.input", lambda _prompt: "bid")
        assert main(["memory", "forget", "--submission-id", "  bid  "]) == 0

    def test_a_blank_submission_id_is_an_input_error(self):
        assert main(["memory", "show", "--submission-id", "   "]) == 1

    def test_forget_of_an_unknown_submission_exits_1(self):
        assert main(["memory", "forget", "--submission-id", "absent", "--yes"]) == 1

    def test_purge_reports_the_count(self, capsys):
        assert main(["memory", "purge"]) == 0
        assert "Deleted 0 check(s) older than 180 days." in capsys.readouterr().out

    @pytest.mark.parametrize("role", ["bidder", "guest", "evaluation_committee"])
    @pytest.mark.parametrize("action", [
        ["list"], ["show", "--submission-id", "bid"], ["forget", "--submission-id", "bid", "--yes"], ["purge"],
    ])
    def test_only_an_officer_may_read_or_delete_history(self, files, role, action, capsys):
        workflow(files)
        capsys.readouterr()
        assert main(["memory", *action, "--role", role]) == 1
        captured = capsys.readouterr()
        assert "Refused" in captured.err and TAX not in captured.out
        assert main(["memory", "show", "--submission-id", "bid"]) == 0

    def test_a_damaged_store_exits_2(self, tmp_path, capsys):
        directory = tmp_path / "case-history"
        directory.mkdir()
        (directory / "case-history.sqlite3").write_text("not a database " * 10)
        assert main(["memory", "list"]) == 2
        assert "Case history unavailable" in capsys.readouterr().err

    def test_the_command_opens_the_configured_store(self, tmp_path):
        store = memory_commands.open_store(Settings(memory_dir=str(tmp_path), memory_retention_days=7))
        assert store.path.parent == tmp_path and store.retention_days == 7


OFFICER_KEY = "officer-key"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PROCURECHECK_API_KEYS", f"{OFFICER_KEY}:procurement_officer:alice")
    monkeypatch.setattr(api, "OllamaClient", FakeOllama)
    return TestClient(api.app)


def post_workflow(client, tmp_path, **form):
    submission = tmp_path / "bid.txt"
    submission.write_text(DOCUMENT, encoding="utf-8")
    checklist = tmp_path / "checklist.txt"
    checklist.write_text("\n".join(ITEMS), encoding="utf-8")
    with submission.open("rb") as s, checklist.open("rb") as c:
        return client.post("/workflow", headers={"X-API-Key": OFFICER_KEY},
                           files={"submission": s, "checklist": c}, data=form)


class TestWorkflowRoute:
    def test_the_second_request_carries_the_comparison(self, client, tmp_path):
        first = post_workflow(client, tmp_path, submission_id="SYN-2026-001").json()
        assert first["memory"]["recalled"] is None and first["memory"]["stored_case_id"] == 1
        second = post_workflow(client, tmp_path, submission_id="SYN-2026-001").json()
        assert second["memory"]["recalled"]["recorded_by"] == "alice"
        assert second["memory"]["comparison"]["same_document"] is True

    def test_a_blank_submission_id_is_refused_with_400(self, client, tmp_path):
        assert post_workflow(client, tmp_path, submission_id="\x1b\x00").status_code == 400

    def test_memory_off_returns_no_memory_block(self, client, tmp_path, monkeypatch):
        monkeypatch.setenv("PROCURECHECK_MEMORY", "off")
        assert post_workflow(client, tmp_path).json()["memory"] is None
