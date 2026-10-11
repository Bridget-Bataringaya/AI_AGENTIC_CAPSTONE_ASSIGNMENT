"""create_review_ticket, implemented to the Third Tool Specification."""

from __future__ import annotations

from datetime import datetime, timezone

from procurecheck.config import Settings
from procurecheck.tools import (
    TOOL_TICKET,
    ReviewQueue,
    ToolCallingAgent,
    ToolContext,
    ToolExecutor,
    default_registry,
)
from procurecheck.tools.contracts import ErrorCode

from tool_fakes import BIDDER, COMMITTEE, OFFICER, SESSION, ScriptedChat, StubModelClient, tool_call

FIXED = datetime(2026, 9, 25, 10, 14, tzinfo=timezone.utc)
ARGS = {
    "submission_id": "MUK-SUPP-2026-0012-BIDDER-A",
    "item_id": "CHK-04",
    "reason": "NSSF clearance certificate present but the expiry date cannot be confirmed.",
    "suggested_status": "AMBIGUOUS",
    "evidence_snippet": "NSSF Compliance Certificate, valid until [illegible]",
    "page_reference": 23,
}


def ticket_executor(queue=None):
    context = ToolContext(Settings(), StubModelClient(), review_queue=queue)
    return ToolExecutor(default_registry(), context)


def test_the_specification_example_opens_a_draft_ticket():
    queue = ReviewQueue(clock=lambda: FIXED)
    result = ticket_executor(queue).execute(TOOL_TICKET, ARGS, OFFICER)
    assert result.ok
    assert result.payload() == {
        "ticket_id": "RVW-000001",
        "status": "draft_created",
        "submission_id": ARGS["submission_id"],
        "item_id": "CHK-04",
        "created_at": "2026-09-25T10:14:00Z",
        "resolved": False,
    }
    (request, _ticket), = queue.entries()
    assert request.reason == ARGS["reason"]


def test_a_repeated_call_returns_the_open_ticket_instead_of_a_second_one():
    queue = ReviewQueue()
    executor = ticket_executor(queue)
    first = executor.execute(TOOL_TICKET, ARGS, OFFICER).payload()
    second = executor.execute(TOOL_TICKET, ARGS, OFFICER).payload()
    assert first == second and len(queue.entries()) == 1


def test_tickets_for_different_items_are_numbered_in_order():
    executor = ticket_executor(ReviewQueue())
    ids = [executor.execute(TOOL_TICKET, {**ARGS, "item_id": f"CHK-0{n}"}, OFFICER).payload()["ticket_id"]
           for n in (1, 2)]
    assert ids == ["RVW-000001", "RVW-000002"]


def test_without_a_session_queue_the_call_fails_openly():
    result = ticket_executor(None).execute(TOOL_TICKET, ARGS, OFFICER)
    assert result.error.error_code is ErrorCode.SERVICE_UNAVAILABLE
    assert "by hand" in result.error.message


def test_only_a_procurement_officer_may_open_tickets():
    for principal in (COMMITTEE, BIDDER, None):
        result = ticket_executor(ReviewQueue()).execute(TOOL_TICKET, ARGS, principal)
        assert result.error.error_code is ErrorCode.UNAUTHORIZED


def test_suggested_status_is_limited_to_the_two_the_specification_names():
    result = ticket_executor(ReviewQueue()).execute(TOOL_TICKET, {**ARGS, "suggested_status": "PRESENT"}, OFFICER)
    assert result.error.error_code is ErrorCode.INVALID_ARGUMENTS


def test_a_missing_reason_is_a_missing_parameter():
    arguments = {k: v for k, v in ARGS.items() if k != "reason"}
    result = ticket_executor(ReviewQueue()).execute(TOOL_TICKET, arguments, OFFICER)
    assert result.error.error_code is ErrorCode.MISSING_PARAMETER


def test_the_queue_offers_no_way_to_resolve_a_ticket():
    public = {name for name in dir(ReviewQueue) if not name.startswith("_")}
    assert public == {"create", "entries"}


def test_the_model_cannot_call_the_ticket_tool_even_by_name():
    queue = ReviewQueue()
    chat = ScriptedChat([{"tool_calls": [tool_call(TOOL_TICKET, ARGS)]}, {"content": "Done."}])
    agent = ToolCallingAgent(chat, ticket_executor(queue))
    run = agent.run("Open a ticket.", OFFICER, SESSION)
    assert run.tool_results[0].error.error_code is ErrorCode.UNKNOWN_TOOL
    assert queue.entries() == ()
    assert TOOL_TICKET not in [d["function"]["name"] for d in chat.tools_offered]


def test_an_undeclared_field_such_as_resolved_is_rejected():
    result = ticket_executor(ReviewQueue()).execute(TOOL_TICKET, {**ARGS, "resolved": True}, OFFICER)
    assert result.error.error_code is ErrorCode.INVALID_ARGUMENTS
