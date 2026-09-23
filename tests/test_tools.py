"""The two tools and the executor, on the paths that are meant to succeed.

The failure paths the Week 4 brief names (missing parameters, unauthorized
requests, unavailable services, unexpected tool responses) are in
test_tool_failures.py, one test per case, so they can be listed in the
evaluation table by ID.
"""

from __future__ import annotations

import pytest

from procurecheck.tools import TOOL_CHECK, TOOL_REPORT, default_registry
from procurecheck.tools.authorization import (
    ApiKeyError,
    PERMISSION_ANALYSE,
    PERMISSION_REPORT,
    Principal,
    load_api_keys,
    principal_for_key,
)
from procurecheck.tools.completeness import _to_submission, percentage
from procurecheck.tools.contracts import ItemPresence, ItemResult

from tool_fakes import COMMITTEE, DOCUMENT, ITEMS, OFFICER, executor


def check(ex=None, **overrides):
    arguments = {"document_text": DOCUMENT, "document_type": "Bid Document", "required_items": ITEMS}
    arguments.update(overrides)
    return (ex or executor()).execute(TOOL_CHECK, arguments, OFFICER)


def report_args(results, pct=None, **overrides):
    arguments = {
        "document_name": "bid.pdf",
        "document_type": "Bid Document",
        "completeness_percentage": percentage(results) if pct is None else pct,
        "completeness_results": [r.model_dump(mode="json") for r in results],
    }
    arguments.update(overrides)
    return arguments


def result(item, status):
    return ItemResult(item=item, status=status, reason="test")


class TestCheckDocumentCompleteness:
    def test_matches_the_specification_output_schema(self):
        outcome = check()
        payload = outcome.payload()
        assert outcome.ok
        assert set(payload) == {"status", "document_type", "completeness_percentage", "results"}
        assert payload["status"] == "success"
        assert set(payload["results"][0]) == {"item", "status", "reason"}

    def test_maps_engine_verdicts_to_present_and_missing(self):
        results = check().output.results
        assert [(r.item, r.status) for r in results] == [
            ("Valid tax clearance certificate", ItemPresence.PRESENT),
            ("Bid securing declaration", ItemPresence.MISSING),
        ]

    def test_present_reason_carries_the_page_and_quotation(self):
        present = check().output.results[0]
        assert "Page 2" in present.reason and "TCC/2026/00417" in present.reason

    def test_percentage_counts_only_present_items(self):
        assert check().output.completeness_percentage == 50.0

    def test_blank_checklist_entries_are_ignored(self):
        outcome = check(required_items=["  ", *ITEMS, ""])
        assert [r.item for r in outcome.output.results] == ITEMS

    def test_page_markers_rebuild_pages(self):
        pages = _to_submission(DOCUMENT).pages
        assert [p.number for p in pages] == [1, 2]

    def test_text_without_markers_is_one_page(self):
        assert [p.number for p in _to_submission("plain text").pages] == [1]


class TestGenerateCompletenessReport:
    def run(self, results, **overrides):
        return executor().execute(TOOL_REPORT, report_args(results, **overrides), OFFICER)

    def test_missing_item_makes_the_report_incomplete(self):
        body = self.run([
            result("Tax clearance", ItemPresence.PRESENT),
            result("Bid securing declaration", ItemPresence.MISSING),
        ]).output.report
        assert body.overall_status.value == "Incomplete"
        assert body.missing_items == ["Bid securing declaration"]
        assert "Bid securing declaration" in body.recommendations[0]

    def test_unclear_without_missing_needs_review(self):
        body = self.run([
            result("Tax clearance", ItemPresence.PRESENT),
            result("Insurance", ItemPresence.UNCLEAR),
        ]).output.report
        assert body.overall_status.value == "Needs Review"
        assert body.unclear_items == ["Insurance"]

    def test_all_present_is_complete_and_says_it_is_not_an_evaluation(self):
        body = self.run([result("Tax clearance", ItemPresence.PRESENT)]).output.report
        assert body.overall_status.value == "Complete"
        assert body.completeness_percentage == 100.0
        assert "not an evaluation" in body.recommendations[0]

    def test_recommendations_never_give_a_verdict_on_the_bid(self):
        body = self.run([
            result("Tax clearance", ItemPresence.MISSING),
            result("Insurance", ItemPresence.UNCLEAR),
        ]).output.report
        text = " ".join(body.recommendations).lower()
        for word in ("award", "reject", "disqualif", "score", "rank"):
            assert word not in text

    def test_rounded_percentage_within_tolerance_is_accepted(self):
        results = [result(f"Item {i}", ItemPresence.PRESENT if i else ItemPresence.MISSING) for i in range(3)]
        assert self.run(results, pct=67).ok

    def test_committee_member_may_generate_a_report(self):
        results = [result("Tax clearance", ItemPresence.PRESENT)]
        assert executor().execute(TOOL_REPORT, report_args(results), COMMITTEE).ok


class TestRegistry:
    def test_both_specified_tools_are_registered(self):
        assert default_registry().names() == [TOOL_CHECK, TOOL_REPORT]

    def test_model_never_sees_the_document_or_checklist_fields(self):
        definition = default_registry().get(TOOL_CHECK).definition()
        properties = definition["function"]["parameters"]["properties"]
        assert set(properties) == {"document_type"}

    def test_report_tool_takes_no_model_arguments(self):
        parameters = default_registry().get(TOOL_REPORT).definition()["function"]["parameters"]
        assert parameters["properties"] == {} and parameters["required"] == []

    def test_describe_keeps_the_full_contract(self):
        described = default_registry().get(TOOL_CHECK).describe()
        assert "document_text" in described["input_schema"]["properties"]
        assert described["permission"] == PERMISSION_ANALYSE

    def test_duplicate_registration_is_rejected(self):
        registry = default_registry()
        with pytest.raises(ValueError):
            registry.register(registry.get(TOOL_CHECK))

    def test_trace_abbreviates_long_arguments(self):
        trace = check(document_text=DOCUMENT * 20).to_trace()
        assert "characters)" in trace["arguments"]["document_text"]


class TestAuthorization:
    def test_roles_grant_the_documented_permissions(self):
        assert OFFICER.may(PERMISSION_ANALYSE) and OFFICER.may(PERMISSION_REPORT)
        assert COMMITTEE.may(PERMISSION_REPORT) and not COMMITTEE.may(PERMISSION_ANALYSE)

    def test_api_keys_parse_from_the_environment_format(self):
        keys = load_api_keys("k1:procurement_officer:alice, k2:bidder:bob")
        assert principal_for_key("k1", keys) == Principal("alice", "procurement_officer")
        assert principal_for_key("k2", keys).role == "bidder"

    def test_unset_keys_mean_no_one_is_authenticated(self):
        assert load_api_keys("") == {}
        assert principal_for_key("anything", {}) is None

    def test_unknown_key_or_missing_key_is_anonymous(self):
        keys = load_api_keys("k1:procurement_officer:alice")
        assert principal_for_key("wrong", keys) is None
        assert principal_for_key(None, keys) is None

    @pytest.mark.parametrize("raw", ["k1:procurement_officer", "k1:superuser:alice", "::"])
    def test_malformed_key_config_fails_loudly(self, raw):
        with pytest.raises(ApiKeyError):
            load_api_keys(raw)

    def test_config_error_never_quotes_the_key(self):
        with pytest.raises(ApiKeyError) as raised:
            load_api_keys("ok:bidder:bob, sk-live-secret:procurement_officer")
        assert "sk-live-secret" not in str(raised.value)
        assert "entry 2" in str(raised.value)
