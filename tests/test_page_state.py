"""Offline regression tests for Gate 1A-01. No network, database, or browser."""
import asyncio
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from page_state import PageState, NextAction, classify_page, classify_playwright_page


class PageStateTests(unittest.TestCase):
    def test_first_route_from_run_40904566211(self):
        snapshot = {
            "ready_state": "interactive",
            "has_result_count_label": True,
            "tender_cards": 10,
            "body_text_length": 4089,
            "body_html_length": 310310,
            "form_count": 1,
            "category_control_found": False,
        }
        result = classify_page(snapshot, http_status=200)
        self.assertEqual(result.state, PageState.RESULTS_VIEW)
        self.assertEqual(result.next_action, NextAction.LOCATE_SEARCH_FORM)
        self.assertEqual(result.signals["tender_cards"], 10)

    def test_second_route_from_run_40904566211(self):
        result = classify_page({
            "ready_state": "loading",
            "body_text_length": 0,
            "body_html_length": 0,
            "tender_cards": 0,
            "category_control_found": False,
        }, navigation_timed_out=True)
        self.assertEqual(result.state, PageState.BLANK_OR_LOADING)
        self.assertTrue(result.navigation_timed_out)

    def test_form_ready_requires_category_control(self):
        result = classify_page({"category_control_found": True, "form_count": 1})
        self.assertEqual(result.state, PageState.FORM_READY)
        self.assertEqual(result.next_action, NextAction.APPLY_FILTER_WITH_ATTESTATION)

    def test_generic_form_is_not_search_form(self):
        result = classify_page({"form_count": 1, "body_text_length": 180})
        self.assertEqual(result.state, PageState.UNKNOWN_LAYOUT)

    def test_semantic_category_fallback(self):
        result = classify_page({"semantic_category_control_found": True})
        self.assertEqual(result.state, PageState.FORM_READY)
        self.assertEqual(result.confidence, "MEDIUM")

    def test_cards_without_count(self):
        result = classify_page({"tender_cards": 8})
        self.assertEqual(result.state, PageState.RESULTS_VIEW)
        self.assertEqual(result.confidence, "MEDIUM")

    def test_zero_results_unverified(self):
        result = classify_page({"has_result_count_label": True, "tender_cards": 0})
        self.assertEqual(result.state, PageState.RESULTS_VIEW)
        self.assertEqual(result.reason_code, "RESULT_COUNT_ONLY_UNVERIFIED")
        self.assertNotIn("VERIFIED_COMPLETE", json.dumps(result.as_report()))

    def test_http_200_without_form_is_not_success(self):
        result = classify_page({"body_text_length": 200}, http_status=200)
        self.assertEqual(result.state, PageState.UNKNOWN_LAYOUT)

    def test_403_overrides_stale_cards(self):
        result = classify_page({"tender_cards": 10}, http_status=403)
        self.assertEqual(result.state, PageState.ERROR_PAGE)

    def test_429_does_not_trigger_bypass(self):
        result = classify_page({}, http_status=429)
        self.assertEqual(result.next_action, NextAction.STOP_AND_RECORD_ERROR)

    def test_captcha_is_error(self):
        result = classify_page({"error_signals": {"captcha": True}})
        self.assertEqual(result.state, PageState.ERROR_PAGE)

    def test_service_failure(self):
        result = classify_page({"error_signals": {"service_unavailable": True}})
        self.assertEqual(result.state, PageState.ERROR_PAGE)

    def test_nav_timeout_does_not_hide_real_results(self):
        result = classify_page({"tender_cards": 10, "has_result_count_label": True},
                               navigation_timed_out=True)
        self.assertEqual(result.state, PageState.RESULTS_VIEW)

    def test_empty_document(self):
        result = classify_page({"ready_state": "complete", "body_text_length": 0,
                                "body_html_length": 0})
        self.assertEqual(result.state, PageState.BLANK_OR_LOADING)

    def test_unknown_layout(self):
        result = classify_page({"ready_state": "complete", "body_text_length": 1200})
        self.assertEqual(result.state, PageState.UNKNOWN_LAYOUT)

    def test_bad_counts_cannot_make_results(self):
        result = classify_page({"tender_cards": True, "body_text_length": 1200})
        self.assertEqual(result.state, PageState.UNKNOWN_LAYOUT)

    def test_report_does_not_copy_sensitive_inputs(self):
        result = classify_page({"cookie": "private-value",
                                "pathname": "/private",
                                "body_text_length": 160}, http_status=200)
        report = json.dumps(result.as_report())
        self.assertNotIn("private-value", report)
        self.assertNotIn("/private", report)

    def test_capture_adapter_without_launching_browser(self):
        class StubPage:
            async def evaluate(self, script):
                self.script = script
                return {"ready_state": "interactive",
                        "tender_cards": 10, "has_result_count_label": True}
        page = StubPage()
        result = asyncio.run(classify_playwright_page(page, http_status=200))
        self.assertEqual(result["state"], "RESULTS_VIEW")
        self.assertNotIn("localStorage", page.script)


if __name__ == "__main__":
    unittest.main()
