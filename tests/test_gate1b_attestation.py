"""Offline decision and protocol regressions for Gate 1B.

Tests contain no network, login, DCE or live Playwright imports.
"""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from category_evidence import aggregate_samples
from gate1b_attestation import (
    _approved_response, _public_snapshot_ok, _settle_prado,
    assess_gate, run_gate_1b,
)


def sample(values):
    return aggregate_samples([
        {"status": "EXPLICIT", "category": value, "source": "explicit_label_pair"}
        if value else {"status": "MISSING", "category": None, "source": None}
        for value in values
    ])


def decide(values=None, **overrides):
    base = dict(selected=True, settled=True, post_status=200,
                results_ready=True, pagestate_changed=True,
                result_transition=False, official_total=100,
                sample=sample(values if values is not None else ["fournitures"] * 5))
    base.update(overrides)
    return assess_gate(**base)


class DecisionTests(unittest.TestCase):
    def test_source_labelled_five_is_only_sample_confirmed(self):
        d = decide()
        self.assertEqual(d.status, "SAMPLED_CONFIRMED")
        self.assertTrue(d.sampled_only)
        self.assertEqual(d.results_verification_state, "CONFIRMED_BY_RESULTS_SAMPLE")
        self.assertEqual(d.fournitures_rows_matched, 5)

    def test_original_dropdown_only_not_confirmation(self):
        d = decide(values=[None] * 5)
        self.assertEqual(d.status, "UNCONFIRMED")
        self.assertEqual(d.reason_code, "SOURCE_CATEGORY_SAMPLE_INCOMPLETE")

    def test_title_with_fournitures_does_not_count(self):
        rows = [{"status": "MISSING", "category": None, "source": None,
                 "title": "Fournitures de bureau"} for _ in range(5)]
        d = decide(sample=aggregate_samples(rows))
        self.assertEqual(d.fournitures_rows_matched, 0)
        self.assertEqual(d.status, "UNCONFIRMED")

    def test_travaux_in_explicit_category_contradicts_sample(self):
        d = decide(values=["fournitures"] * 4 + ["travaux"])
        self.assertEqual(d.status, "CONTRADICTED_SAMPLE")
        self.assertEqual(d.contaminating_rows_found, 1)
        self.assertEqual(d.results_verification_state, "CONTRADICTED_BY_RESULTS_SAMPLE")

    def test_services_in_explicit_category_contradicts(self):
        self.assertEqual(decide(values=["services"] + ["fournitures"] * 4).status,
                         "CONTRADICTED_SAMPLE")

    def test_services_in_title_without_category_is_not_contamination(self):
        values = [None, "fournitures", "fournitures", "fournitures", "fournitures"]
        d = decide(values=values)
        self.assertEqual(d.contaminating_rows_found, 0)
        self.assertEqual(d.unclassified_rows, 1)
        self.assertEqual(d.status, "UNCONFIRMED")

    def test_not_selected_never_succeeds(self):
        d = decide(selected=False)
        self.assertEqual(d.status, "UNCONFIRMED")
        self.assertEqual(d.selection_state, "NOT_SELECTED")

    def test_callback_pending_prevents_submission_proof(self):
        d = decide(settled=False)
        self.assertEqual(d.status, "UNCONFIRMED")
        self.assertEqual(d.reason_code, "PRADO_CALLBACK_NOT_SETTLED")

    def test_post_200_alone_not_applied(self):
        d = decide(pagestate_changed=False, result_transition=False)
        self.assertEqual(d.status, "UNCONFIRMED")
        self.assertEqual(d.postback_state, "POST_200_UNVERIFIED")
        self.assertEqual(d.reason_code, "POSTBACK_EFFECT_NOT_OBSERVED")

    def test_result_change_without_pagestate_is_valid_supporting_evidence(self):
        d = decide(pagestate_changed=False, result_transition=True)
        self.assertEqual(d.status, "SAMPLED_CONFIRMED")
        self.assertEqual(d.postback_state, "APPLIED")

    def test_post_non_200_fails_closed(self):
        d = decide(post_status=500)
        self.assertEqual(d.status, "UNCONFIRMED")
        self.assertEqual(d.postback_state, "NOT_APPLIED")

    def test_no_postback_is_not_claimed_server_timeout(self):
        d = decide(post_status=None)
        self.assertEqual(d.reason_code, "SEARCH_POST_RESPONSE_NOT_200")
        self.assertEqual(d.status, "UNCONFIRMED")

    def test_results_not_ready(self):
        d = decide(results_ready=False)
        self.assertEqual(d.reason_code, "RESULTS_DOM_NOT_READY")

    def test_zero_results_not_proof(self):
        d = decide(official_total=0)
        self.assertEqual(d.reason_code, "OFFICIAL_TOTAL_UNVERIFIED")

    def test_bad_total_not_proof(self):
        d = decide(official_total=True)
        self.assertEqual(d.status, "UNCONFIRMED")

    def test_sample_size_smaller_than_total_not_enough(self):
        d = decide(values=["fournitures"] * 3, official_total=60)
        self.assertEqual(d.status, "UNCONFIRMED")

    def test_entire_small_sample_is_enough_for_only_sample_gate(self):
        d = decide(values=["fournitures"] * 3, official_total=3)
        self.assertEqual(d.status, "SAMPLED_CONFIRMED")

    def test_invalid_minimum_sample(self):
        with self.assertRaises(ValueError):
            decide(minimum_sample=11)

    def test_proof_object_does_not_leak_text(self):
        d = decide()
        out = str(d.report())
        self.assertNotIn("https:", out)
        self.assertNotIn("PRADO_PAGESTATE", out)


class HttpEvidenceTests(unittest.TestCase):
    class Request:
        method = "POST"
        resource_type = "xhr"

    class Response:
        request = HttpEvidenceTests if False else None

        def __init__(self, url, method="POST", kind="xhr", status=200):
            self.url = url
            self.status = status
            self.request = type("Request", (), {"method": method, "resource_type": kind})()

    def test_ajax_post_from_portal(self):
        r = self.Response("https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch")
        self.assertTrue(_approved_response(r))

    def test_document_post_from_portal(self):
        r = self.Response("https://www.marchespublics.gov.ma/", kind="document")
        self.assertTrue(_approved_response(r))

    def test_get_is_not_post_ack(self):
        self.assertFalse(_approved_response(self.Response(
            "https://www.marchespublics.gov.ma/", method="GET")))

    def test_external_post_not_ack(self):
        self.assertFalse(_approved_response(self.Response("https://example.org/")))

    def test_no_results_count_label(self):
        self.assertFalse(_public_snapshot_ok({"cards": 5, "count_label": False}))

    def test_no_cards(self):
        self.assertFalse(_public_snapshot_ok({"cards": 0, "count_label": True}))

    def test_boolean_card_count_not_valid(self):
        self.assertFalse(_public_snapshot_ok({"cards": True, "count_label": True}))

    def test_valid_public_result_snapshot(self):
        self.assertTrue(_public_snapshot_ok({"cards": 5, "count_label": True}))


class StabilityTests(unittest.TestCase):
    def test_selected_and_stable_pagestate(self):
        class Page:
            async def evaluate(self, script):
                return dict(selected_label="Fournitures", category=True, button=True,
                            pagestate=True, pagestate_value="safe-but-not-exported-" * 4)
        r = asyncio.run(_settle_prado(Page(), set(), timeout_ms=1200, stable_ms=160))
        self.assertTrue(r[0])
        self.assertTrue(r[1])
        self.assertGreater(len(r[2]), 20)

    def test_missing_pagestate_no_success(self):
        class Page:
            async def evaluate(self, script):
                return dict(selected_label="Fournitures", category=True, button=True,
                            pagestate=False, pagestate_value="")
        r = asyncio.run(_settle_prado(Page(), set(), timeout_ms=300, stable_ms=100))
        self.assertFalse(r[0])
        self.assertIsNone(r[2])

    def test_pending_ajax_request_never_counts_settled(self):
        class Page:
            async def evaluate(self, script):
                return dict(selected_label="Fournitures", category=True, button=True,
                            pagestate=True, pagestate_value="hello" * 10)
        r = asyncio.run(_settle_prado(Page(), {8}, timeout_ms=300, stable_ms=100))
        self.assertFalse(r[0])

    def test_prado_token_is_not_exported_when_page_untrusted(self):
        class Page:
            url = "https://other.example/?token=secret"
            def __init__(self):
                self.events = {}
            def on(self, event, callback):
                self.events[event] = callback
            def remove_listener(self, event, callback):
                self.events.pop(event, None)
        p = Page()
        result = asyncio.run(run_gate_1b(p, None))
        self.assertEqual(result["status"], "UNCONFIRMED")
        self.assertEqual(result["search_clicks"], 0)
        self.assertNotIn("secret", str(result))


if __name__ == "__main__":
    unittest.main()
