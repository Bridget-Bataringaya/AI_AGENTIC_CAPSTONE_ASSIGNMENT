"""The `memory` command: see what is remembered, and delete it.

    python run.py memory list
    python run.py memory show --submission-id ID
    python run.py memory forget --submission-id ID [--yes]
    python run.py memory purge

As with `workflow`, the command line is a local, trusted entry point and the
role comes from --role. Reading needs case_history:read and deleting needs
case_history:delete, which only a procurement officer holds.

`forget` cannot be undone, so it asks the operator to type the submission id.
`--yes` skips the question for a script.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from typing import Callable

from ..config import Settings
from ..tools.authorization import (
    PERMISSION_HISTORY_DELETE,
    PERMISSION_HISTORY_READ,
    ROLE_PERMISSIONS,
    ROLE_PROCUREMENT_OFFICER,
    Principal,
)
from .store import CaseHistoryStore, MemoryUnavailableError, resolve_store_path, validate_submission_id

EXIT_OK = 0
EXIT_USER_ERROR = 1
EXIT_STORE_ERROR = 2

TIME_FORMAT = "%Y-%m-%d %H:%M UTC"


def add_parsers(subparsers: argparse._SubParsersAction) -> None:
    memory = subparsers.add_parser("memory", help="See or delete the remembered case history")
    actions = memory.add_subparsers(dest="memory_action", required=True)

    def action(name: str, text: str) -> argparse.ArgumentParser:
        parser = actions.add_parser(name, help=text)
        parser.add_argument(
            "--role", default=ROLE_PROCUREMENT_OFFICER, choices=sorted(ROLE_PERMISSIONS),
            help="The caller's role, which decides what may be read or deleted",
        )
        return parser

    action("list", "List the submissions that have a remembered check")
    show = action("show", "Show every remembered check of one submission")
    show.add_argument("--submission-id", required=True)
    forget = action("forget", "Delete every remembered check of one submission")
    forget.add_argument("--submission-id", required=True)
    forget.add_argument("--yes", action="store_true", help="Delete without asking for confirmation")
    action("purge", "Delete the checks that are past the retention period now")


def open_store(settings: Settings) -> CaseHistoryStore:
    return CaseHistoryStore(resolve_store_path(settings.memory_dir), settings.memory_retention_days)


def _list(store: CaseHistoryStore, _args: argparse.Namespace, _principal: Principal) -> int:
    summaries = store.submissions()
    if not summaries:
        print("Nothing is remembered. A check is remembered when a workflow run reaches a report.")
        return EXIT_OK
    for summary in summaries:
        print(
            f"{summary.submission_id}: {summary.checks} check(s), last on "
            f"{summary.last_checked.strftime(TIME_FORMAT)}, {summary.last_status}"
        )
    print(f"Each check is kept for {store.retention_days} days. Stored at {store.path}")
    return EXIT_OK


def _show(store: CaseHistoryStore, args: argparse.Namespace, _principal: Principal) -> int:
    cases = store.history(args.submission_id)
    if not cases:
        print(f"No check of {args.submission_id} is remembered.")
        return EXIT_USER_ERROR
    for case in cases:
        print(
            f"Case {case.case_id}: {case.recorded_at.strftime(TIME_FORMAT)} by {case.recorded_by}, "
            f"{case.document_name}, {case.overall_status}, {case.completeness_percentage}% present "
            f"(ProcureCheck {case.app_version}, ended as {case.stop_reason})"
        )
        print(f"  Document fingerprint: {case.document_sha256}")
        for item in case.items:
            print(f"  - {item.status.value}: {item.item}")
    return EXIT_OK


def _confirmed(submission_id: str, count: int) -> bool:
    if not sys.stdin.isatty():
        print("Not deleted: no one is at the terminal to confirm. Pass --yes to delete from a script.",
              file=sys.stderr)
        return False
    try:
        typed = input(f"Type {submission_id} to delete its {count} remembered check(s): ")
    except EOFError:
        typed = ""
    if typed.strip() != submission_id:
        print("Not deleted: the submission id typed did not match.", file=sys.stderr)
        return False
    return True


def _forget(store: CaseHistoryStore, args: argparse.Namespace, principal: Principal) -> int:
    count = len(store.history(args.submission_id))
    if count == 0:
        print(f"No check of {args.submission_id} is remembered. Nothing was deleted.")
        return EXIT_USER_ERROR
    if not args.yes and not _confirmed(args.submission_id, count):
        return EXIT_USER_ERROR
    removed = store.forget(args.submission_id, deleted_by=principal.user_id)
    print(f"Deleted {removed} remembered check(s) of {args.submission_id}.")
    return EXIT_OK


def _purge(store: CaseHistoryStore, _args: argparse.Namespace, _principal: Principal) -> int:
    removed = store.purge_expired()
    print(f"Deleted {removed} check(s) older than {store.retention_days} days.")
    return EXIT_OK


_ACTIONS = {
    "list": (PERMISSION_HISTORY_READ, _list),
    "show": (PERMISSION_HISTORY_READ, _show),
    "forget": (PERMISSION_HISTORY_DELETE, _forget),
    "purge": (PERMISSION_HISTORY_DELETE, _purge),
}


def run_memory(args: argparse.Namespace, settings: Settings) -> int:
    permission, handler = _ACTIONS[args.memory_action]
    handler: Callable[[CaseHistoryStore, argparse.Namespace, Principal], int]
    principal = Principal(user_id=getpass.getuser(), role=args.role)
    if getattr(args, "submission_id", None) is not None:
        try:
            # The same cleaning the store applies, so the id typed to confirm
            # a deletion is compared with the id as it is stored.
            args.submission_id = validate_submission_id(args.submission_id)
        except ValueError as exc:
            print(f"Input error: {exc}", file=sys.stderr)
            return EXIT_USER_ERROR
    if not principal.may(permission):
        print(f"Refused: the role {args.role} may not {args.memory_action} case history.", file=sys.stderr)
        return EXIT_USER_ERROR
    try:
        return handler(open_store(settings), args, principal)
    except MemoryUnavailableError as exc:
        print(f"Case history unavailable: {exc}", file=sys.stderr)
        return EXIT_STORE_ERROR
