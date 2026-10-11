"""The orchestration loop on its normal path: check, report, answer."""

from __future__ import annotations

import json

import pytest

from procurecheck.tools import TOOL_CHECK, TOOL_REPORT, ToolCallingAgent

from tool_fakes import FINAL, ScriptedChat, executor, run_agent, tool_call

HAPPY = [
    {"tool_calls": [tool_call(TOOL_CHECK, {"document_type": "Bid Document"})]},
    {"tool_calls": [tool_call(TOOL_REPORT)]},
    FINAL,
]


def test_check_then_report_then_answer():
    run, chat = run_agent(HAPPY)
    assert run.ok and run.model_turns == 3
    assert [r.tool for r in run.tool_results] == [TOOL_CHECK, TOOL_REPORT]
    assert run.report.report.missing_items == ["Bid securing declaration"]
    assert run.final_message == FINAL["content"]


def test_report_receives_the_check_results_from_the_session():
    run, _ = run_agent(HAPPY)
    bound = run.tool_results[1].arguments
    assert bound["completeness_percentage"] == 50.0
    assert bound["document_name"] == "bid.pdf"
    assert len(bound["completeness_results"]) == 2


def test_model_is_offered_both_tools_and_never_sees_the_document():
    _, chat = run_agent(HAPPY)
    offered = [t["function"]["name"] for t in chat.tools_offered]
    assert offered == [TOOL_CHECK, TOOL_REPORT]
    conversation = json.dumps(chat.seen[0])
    assert "[PAGE 2]" not in conversation


def test_tool_results_go_back_to_the_model_as_tool_messages():
    _, chat = run_agent(HAPPY)
    tool_message = chat.seen[1][-1]
    assert tool_message["role"] == "tool" and tool_message["tool_name"] == TOOL_CHECK
    assert json.loads(tool_message["content"])["completeness_percentage"] == 50.0
    # The evidence travels with the result, so the summary can cite it.
    assert "TCC/2026/00417" in tool_message["content"]


def test_trace_records_each_call_without_repeating_the_document():
    run, _ = run_agent(HAPPY)
    trace = run.to_trace()
    assert trace["status"] == "success" and len(trace["tool_calls"]) == 2
    assert trace["principal"] == {"user_id": "officer-1", "role": "procurement_officer"}
    assert trace["prompt_version"] == "orchestrator-v1.0"
    json.dumps(trace)  # serialisable as written


def test_a_run_needs_at_least_one_turn():
    with pytest.raises(ValueError):
        ToolCallingAgent(ScriptedChat([]), executor(), max_turns=0)


def test_a_direct_answer_with_no_tool_call_is_returned_as_is():
    run, _ = run_agent([{"content": "Which document should I check?"}])
    assert run.ok and run.tool_results == () and run.final_message.startswith("Which")
