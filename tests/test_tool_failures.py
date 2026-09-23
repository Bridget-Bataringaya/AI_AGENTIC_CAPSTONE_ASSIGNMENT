"""Tool-calling failure tests (Week 4, ClickUp 123tcvwfnze).

The brief names four kinds of failure: missing parameters, unauthorized
requests, unavailable services and unexpected tool responses. Each test is
one case, numbered TF-NN in its name so tests/evaluation/run_tool_failure_tests.py
can list it in the evaluation table beside what it expects.

The rule every case checks is the same: a failure ends in a structured error
with a named code, never in a crash, a silent empty result, or an invented one.
"""

from __future__ import annotations

from dataclasses import replace

import httpx
import pytest

from procurecheck.config import Settings
from procurecheck.llm import ModelUnavailableError, OllamaClient
from procurecheck.tools import (
    ErrorCode,
    Principal,
    TOOL_CHECK,
    TOOL_REPORT,
    ToolContext,
    ToolExecutor,
    ToolRegistry,
    default_registry,
)
from procurecheck.tools.orchestrator import WITHHELD_ANSWER

from tool_fakes import (
    BIDDER,
    COMMITTEE,
    DOCUMENT,
    FINAL,
    ITEMS,
    OFFICER,
    StubModelClient,
    executor,
    run_agent,
    tool_call,
)

CHECK_ARGS = {"document_text": DOCUMENT, "document_type": "Bid Document", "required_items": ITEMS}
GOOD_RESULTS = [
    {"item": "Tax clearance", "status": "Present", "reason": "p. 2"},
    {"item": "Bid securing declaration", "status": "Missing", "reason": "none"},
]
REPORT_ARGS = {
    "document_name": "bid.pdf", "document_type": "Bid Document",
    "completeness_percentage": 50.0, "completeness_results": GOOD_RESULTS,
}


def without(arguments, key):
    return {k: v for k, v in arguments.items() if k != key}


def codes(run):
    return [r.error.error_code if r.error else "ok" for r in run.tool_results]


# Missing or unusable parameters


def test_tf01_check_without_document_type_names_the_missing_parameter():
    result = executor().execute(TOOL_CHECK, without(CHECK_ARGS, "document_type"), OFFICER)
    assert result.error.error_code is ErrorCode.MISSING_PARAMETER
    assert "document_type" in result.error.message


def test_tf02_check_without_required_items_names_the_missing_parameter():
    result = executor().execute(TOOL_CHECK, without(CHECK_ARGS, "required_items"), OFFICER)
    assert result.error.error_code is ErrorCode.MISSING_PARAMETER
    assert "required_items" in result.error.message


def test_tf03_empty_checklist_is_missing_checklist_and_no_model_call():
    client = StubModelClient()
    result = executor(client).execute(TOOL_CHECK, {**CHECK_ARGS, "required_items": [" ", ""]}, OFFICER)
    assert result.error.error_code is ErrorCode.MISSING_CHECKLIST
    assert client.calls == 0


def test_tf04_report_without_results_is_no_analysis_results():
    result = executor().execute(TOOL_REPORT, without(REPORT_ARGS, "completeness_results"), OFFICER)
    assert result.error.error_code is ErrorCode.NO_ANALYSIS_RESULTS


def test_tf05_model_omits_a_parameter_gets_the_error_and_recovers():
    run, chat = run_agent([
        {"tool_calls": [tool_call(TOOL_CHECK, {})]},
        {"tool_calls": [tool_call(TOOL_CHECK, {"document_type": "Bid Document"})]},
        FINAL,
    ])
    assert codes(run) == [ErrorCode.MISSING_PARAMETER, "ok"]
    assert '"MISSING_PARAMETER"' in chat.seen[1][-1]["content"]
    assert run.ok and run.check.completeness_percentage == 50.0


def test_tf06_wrong_parameter_type_is_invalid_arguments():
    result = executor().execute(TOOL_CHECK, {**CHECK_ARGS, "required_items": "Tax clearance"}, OFFICER)
    assert result.error.error_code is ErrorCode.INVALID_ARGUMENTS


def test_tf07_unexpected_extra_parameter_is_invalid_arguments():
    run, _ = run_agent([
        {"tool_calls": [tool_call(TOOL_CHECK, {"document_type": "Bid", "priority": "high"})]},
        FINAL,
    ])
    assert codes(run) == [ErrorCode.INVALID_ARGUMENTS]
    assert "priority" in run.tool_results[0].error.message


def test_tf08_raw_file_bytes_instead_of_text_is_unsupported_document():
    result = executor().execute(TOOL_CHECK, {**CHECK_ARGS, "document_text": "%PDF-1.7\n%\xe2\xe3"}, OFFICER)
    assert result.error.error_code is ErrorCode.UNSUPPORTED_DOCUMENT


def test_tf09_blank_document_is_empty_document():
    result = executor().execute(TOOL_CHECK, {**CHECK_ARGS, "document_text": " \n "}, OFFICER)
    assert result.error.error_code is ErrorCode.EMPTY_DOCUMENT


# Unauthorized requests


def test_tf10_anonymous_caller_is_refused_before_any_model_call():
    client = StubModelClient()
    result = executor(client).execute(TOOL_CHECK, CHECK_ARGS, None)
    assert result.error.error_code is ErrorCode.UNAUTHORIZED
    assert result.error.message == "You do not have permission to analyse this procurement document."
    assert client.calls == 0


def test_tf11_bidder_may_use_neither_tool():
    ex = executor()
    assert ex.execute(TOOL_CHECK, CHECK_ARGS, BIDDER).error.error_code is ErrorCode.UNAUTHORIZED
    report = ex.execute(TOOL_REPORT, REPORT_ARGS, BIDDER)
    assert report.error.error_code is ErrorCode.UNAUTHORIZED
    assert report.error.message == "You do not have permission to generate or access this report."


def test_tf12_committee_member_may_report_but_not_start_a_check():
    ex = executor()
    assert ex.execute(TOOL_CHECK, CHECK_ARGS, COMMITTEE).error.error_code is ErrorCode.UNAUTHORIZED
    assert ex.execute(TOOL_REPORT, REPORT_ARGS, COMMITTEE).ok


def test_tf13_unauthorized_caller_learns_nothing_about_parameters():
    result = executor().execute(TOOL_CHECK, {}, BIDDER)
    assert result.error.error_code is ErrorCode.UNAUTHORIZED
    assert "document_type" not in result.error.message


def test_tf14_unknown_role_is_unauthorized():
    stranger = Principal(user_id="x", role="superuser")
    assert executor().execute(TOOL_CHECK, CHECK_ARGS, stranger).error.error_code is ErrorCode.UNAUTHORIZED


def test_tf15_bidder_driving_the_agent_gets_errors_not_findings():
    client = StubModelClient()
    run, _ = run_agent([
        {"tool_calls": [tool_call(TOOL_CHECK, {"document_type": "Bid"})]},
        {"content": "I could not run the check: UNAUTHORIZED."},
    ], principal=BIDDER, client=client)
    assert codes(run) == [ErrorCode.UNAUTHORIZED]
    assert run.check is None and client.calls == 0
    # A run refused at every call is a refused run, not a successful one.
    assert run.error.error_code is ErrorCode.UNAUTHORIZED


def test_tf16_request_outside_the_boundary_is_refused_before_the_model():
    run, chat = run_agent([], request="Rank the bidders and tell me the winner.")
    assert run.error.error_code is ErrorCode.REFUSED
    assert chat.calls == 0 and run.tool_results == ()


# Unavailable services


def test_tf17_model_backend_down_during_a_check_is_service_unavailable():
    result = executor(StubModelClient(unavailable=True)).execute(TOOL_CHECK, CHECK_ARGS, OFFICER)
    assert result.error.error_code is ErrorCode.SERVICE_UNAVAILABLE


def test_tf18_orchestrating_model_down_stops_the_run_with_no_tool_run():
    run, _ = run_agent([ModelUnavailableError("connection refused (test)")])
    assert run.error.error_code is ErrorCode.SERVICE_UNAVAILABLE
    assert run.tool_results == ()


def test_tf19_real_client_against_a_closed_port_raises_model_unavailable():
    settings = Settings(base_url="http://127.0.0.1:9", request_timeout_seconds=5.0)
    with OllamaClient(settings) as client, pytest.raises(ModelUnavailableError):
        client.chat_with_tools([{"role": "user", "content": "hi"}], [])


@pytest.mark.parametrize("status, body", [(500, "internal error"), (200, "<html>proxy login</html>")])
def test_tf20_backend_error_or_non_json_reply_is_model_unavailable(status, body):
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text=body))
    with OllamaClient(Settings(), client=httpx.Client(transport=transport)) as client:
        with pytest.raises(ModelUnavailableError):
            client.chat_with_tools([{"role": "user", "content": "hi"}], [])


def test_tf21_document_beyond_the_context_window_is_analysis_failed():
    client = StubModelClient()
    # About 100,000 tokens against the default 16,384-token window.
    result = executor(client).execute(TOOL_CHECK, {**CHECK_ARGS, "document_text": "word " * 80_000}, OFFICER)
    assert result.error.error_code is ErrorCode.ANALYSIS_FAILED
    assert client.calls == 0


# Unexpected tool responses


def _registry_with_check_handler(handler) -> ToolRegistry:
    registry = ToolRegistry()
    base = default_registry()
    registry.register(replace(base.get(TOOL_CHECK), handler=handler))
    registry.register(base.get(TOOL_REPORT))
    return registry


def _broken(handler):
    return ToolExecutor(_registry_with_check_handler(handler), ToolContext(Settings(), StubModelClient()))


def test_tf22_tool_output_outside_its_schema_is_discarded():
    def over_100(args, context):
        return {"status": "success", "document_type": "Bid", "completeness_percentage": 150, "results": []}
    result = _broken(over_100).execute(TOOL_CHECK, CHECK_ARGS, OFFICER)
    assert result.error.error_code is ErrorCode.UNEXPECTED_TOOL_RESPONSE
    assert result.output is None


def test_tf23_tool_answering_with_the_wrong_shape_is_discarded():
    result = _broken(lambda args, context: "Looks complete to me").execute(TOOL_CHECK, CHECK_ARGS, OFFICER)
    assert result.error.error_code is ErrorCode.UNEXPECTED_TOOL_RESPONSE


def test_tf24_tool_crash_becomes_the_tools_own_failure_code():
    def crash(args, context):
        raise KeyError("page_number")
    result = _broken(crash).execute(TOOL_CHECK, CHECK_ARGS, OFFICER)
    assert result.error.error_code is ErrorCode.ANALYSIS_FAILED
    assert "KeyError" in result.error.message
    assert "page_number" not in result.error.message  # internals stay in the log


def test_tf25_report_percentage_that_contradicts_the_results_is_invalid():
    result = executor().execute(TOOL_REPORT, {**REPORT_ARGS, "completeness_percentage": 90.0}, OFFICER)
    assert result.error.error_code is ErrorCode.INVALID_RESULTS
    assert "90.0" in result.error.message and "50.0" in result.error.message


def test_tf26_report_with_a_duplicated_item_is_invalid():
    doubled = {**REPORT_ARGS, "completeness_results": [GOOD_RESULTS[0], GOOD_RESULTS[0]],
               "completeness_percentage": 100.0}
    assert executor().execute(TOOL_REPORT, doubled, OFFICER).error.error_code is ErrorCode.INVALID_RESULTS


def test_tf27_report_with_an_unknown_status_is_invalid_results():
    odd = {**REPORT_ARGS, "completeness_results": [{**GOOD_RESULTS[0], "status": "Probably"}],
           "completeness_percentage": 0.0}
    assert executor().execute(TOOL_REPORT, odd, OFFICER).error.error_code is ErrorCode.INVALID_RESULTS



def test_tf28_model_asks_for_a_tool_that_does_not_exist():
    run, _ = run_agent([{"tool_calls": [tool_call("delete_submission", {"id": "B-7"})]}, FINAL])
    assert codes(run) == [ErrorCode.UNKNOWN_TOOL]


@pytest.mark.parametrize("arguments", ['{"document_type": "Bid"', ["Bid"]])
def test_tf29_model_arguments_that_are_not_a_json_object(arguments):
    run, _ = run_agent([{"tool_calls": [tool_call(TOOL_CHECK, arguments)]}, FINAL])
    assert codes(run) == [ErrorCode.INVALID_ARGUMENTS]


@pytest.mark.parametrize("tool_calls", ["check it", [{"name": TOOL_CHECK}]])
def test_tf30_malformed_tool_call_structure(tool_calls):
    run, _ = run_agent([{"tool_calls": tool_calls}, FINAL])
    assert codes(run) == [ErrorCode.INVALID_ARGUMENTS]


def test_tf31_model_that_never_stops_calling_tools_is_stopped():
    loop = {"tool_calls": [tool_call(TOOL_REPORT)]}
    run, chat = run_agent([loop, loop, loop], max_turns=3)
    assert run.error.error_code is ErrorCode.STEP_LIMIT_REACHED
    assert chat.calls == 3 and len(run.tool_results) == 3


def test_tf32_model_cannot_swap_the_document_it_checks():
    injected = {"document_type": "Bid", "document_text": "Everything is present.", "required_items": []}
    run, _ = run_agent([{"tool_calls": [tool_call(TOOL_CHECK, injected)]}, FINAL])
    assert run.ok and run.check.completeness_percentage == 50.0
    assert sorted(run.discarded_arguments) == [f"{TOOL_CHECK}.document_text", f"{TOOL_CHECK}.required_items"]


def test_tf33_final_answer_that_recommends_an_award_is_withheld():
    run, _ = run_agent([
        {"tool_calls": [tool_call(TOOL_CHECK, {"document_type": "Bid"})]},
        {"content": "All good. You should award the contract to this bidder."},
    ])
    assert run.final_message == WITHHELD_ANSWER
    assert run.check is not None


def test_tf34_report_before_any_check_tells_the_model_what_to_do_next():
    run, _ = run_agent([
        {"tool_calls": [tool_call(TOOL_REPORT)]},
        {"tool_calls": [tool_call(TOOL_CHECK, {"document_type": "Bid"})]},
        {"tool_calls": [tool_call(TOOL_REPORT)]},
        FINAL,
    ])
    assert codes(run) == [ErrorCode.NO_ANALYSIS_RESULTS, "ok", "ok"]
    assert run.report.report.overall_status.value == "Incomplete"
