"""Offline Gate 1A-02 navigation policy tests: no network or portal calls."""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from navigation_recovery import Route, is_allowed_search_url, navigation_decision, recover_search_form

ROOT = "https://www.marchespublics.gov.ma"
A = Route("official_primary", ROOT + "/?page=entreprise.EntrepriseAdvancedSearch&AllCons&searchAnnCons")
B = Route("official_secondary", ROOT + "/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&EnCours&searchAnnCons")


class FakeResponse:
    def __init__(self, status=200): self.status = status


class FakePage:
    def __init__(self, transitions):
        # List of (status | exception, list of DOM signals) per navigation.
        self.transitions = transitions
        self.url = ""
        self.calls = []
        self.snapshots = []
        self.sleep_count = 0

    async def goto(self, url, *, wait_until, timeout):
        self.calls.append(url)
        self.url = url
        response, states = self.transitions.pop(0)
        self.snapshots = list(states)
        if isinstance(response, BaseException): raise response
        return FakeResponse(response)

    async def evaluate(self, script):
        if len(self.snapshots) > 1: return self.snapshots.pop(0)
        return self.snapshots[0]

    async def wait_for_timeout(self, ms): self.sleep_count += 1


FORM = {"category_control_found": True, "form_count": 1, "ready_state": "complete"}
RESULTS = {"tender_cards": 10, "has_result_count_label": True, "ready_state": "interactive", "body_text_length": 4089}
LOADING = {"ready_state": "loading", "tender_cards": 0, "body_text_length": 0, "body_html_length": 0}
UNKNOWN = {"ready_state": "complete", "body_text_length": 250}
ERROR = {"error_signals": {"captcha": True}}


class Tests(unittest.TestCase):
    def run_case(self, transitions, routes=(A, B)):
        page = FakePage(transitions)
        result = asyncio.run(recover_search_form(page, routes))
        return page, result

    def test_real_run_route_a_results_route_b_timeout(self):
        page, outcome = self.run_case([(200, [RESULTS]), (TimeoutError(), [LOADING])])
        self.assertFalse(outcome.form_ready)
        self.assertEqual(outcome.reason_code, "SEARCH_FORM_NOT_OBSERVED")
        self.assertEqual([o["state"] for o in outcome.observations], ["RESULTS_VIEW", "BLANK_OR_LOADING"])
        self.assertEqual(page.sleep_count, 1)

    def test_second_route_form(self):
        page, outcome = self.run_case([(200, [RESULTS]), (200, [FORM])])
        self.assertTrue(outcome.form_ready)
        self.assertEqual(outcome.route_id, "official_secondary")
        self.assertEqual(len(page.calls), 2)
        self.assertFalse(outcome.as_report()["filter_attested"])

    def test_primary_form_never_tries_other_route(self):
        page, outcome = self.run_case([(200, [FORM])])
        self.assertTrue(outcome.form_ready)
        self.assertEqual(len(page.calls), 1)

    def test_timeout_but_rendered_form_can_succeed(self):
        page, outcome = self.run_case([(TimeoutError(), [FORM])])
        self.assertTrue(outcome.form_ready)
        self.assertTrue(outcome.observations[0]["timed_out"])

    def test_loading_passive_recheck_then_form(self):
        page, outcome = self.run_case([(200, [LOADING, FORM])])
        self.assertTrue(outcome.form_ready)
        self.assertEqual(page.sleep_count, 1)
        self.assertEqual(len(page.calls), 1)

    def test_error_stops_further_navigation(self):
        page, outcome = self.run_case([(403, [FORM])])
        self.assertEqual(outcome.reason_code, "ACCESS_OR_PORTAL_ERROR")
        self.assertEqual(len(page.calls), 1)

    def test_captcha_never_bypassed(self):
        page, outcome = self.run_case([(200, [ERROR])])
        self.assertEqual(outcome.reason_code, "ACCESS_OR_PORTAL_ERROR")
        self.assertEqual(len(page.calls), 1)

    def test_unknown_layout_stops(self):
        page, outcome = self.run_case([(200, [UNKNOWN])])
        self.assertEqual(outcome.reason_code, "UNKNOWN_SEARCH_LAYOUT")
        self.assertEqual(len(page.calls), 1)

    def test_both_blank_reports_incomplete(self):
        page, outcome = self.run_case([(200, [LOADING]), (TimeoutError(), [LOADING])])
        self.assertEqual(outcome.reason_code, "NAVIGATION_INCOMPLETE")
        self.assertEqual(page.sleep_count, 2)

    def test_unexpected_exception_stops(self):
        page, outcome = self.run_case([(RuntimeError("bad"), [RESULTS])])
        self.assertEqual(outcome.reason_code, "NAVIGATION_EXCEPTION")
        self.assertEqual(len(page.calls), 1)

    def test_no_routes(self):
        with self.assertRaises(ValueError):
            asyncio.run(recover_search_form(FakePage([]), []))

    def test_more_than_two_routes(self):
        with self.assertRaises(ValueError):
            asyncio.run(recover_search_form(FakePage([]), [A, B, Route("third", A.url)]))

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            asyncio.run(recover_search_form(FakePage([]), [A, Route(A.id, B.url)]))

    def test_unsafe_waits_rejected(self):
        with self.assertRaises(ValueError):
            asyncio.run(recover_search_form(FakePage([]), [A], settle_wait_ms=10000))

    def test_allowlist(self):
        self.assertTrue(is_allowed_search_url(A.url))
        self.assertTrue(is_allowed_search_url(B.url))
        self.assertFalse(is_allowed_search_url("http://" + A.url.split("//")[1]))
        self.assertFalse(is_allowed_search_url("https://attacker.example/index.php?page=entreprise.EntrepriseAdvancedSearch"))
        self.assertFalse(is_allowed_search_url(ROOT + "/?page=entreprise.EntrepriseDetailsConsultation"))
        self.assertFalse(is_allowed_search_url(ROOT + "/?page=entreprise.EntrepriseAdvancedSearch#x"))

    def test_decision_is_not_an_instruction_to_filter_results_view(self):
        self.assertEqual(navigation_decision("RESULTS_VIEW", routes_remaining=True), "TRY_NEXT_OFFICIAL_ROUTE")
        self.assertEqual(navigation_decision("RESULTS_VIEW", routes_remaining=False), "SEARCH_FORM_NOT_OBSERVED")
        self.assertEqual(navigation_decision("FORM_READY", routes_remaining=True), "FORM_READY")


if __name__ == "__main__": unittest.main()


class StaleNavigationTests(unittest.TestCase):
    def test_timeout_cannot_reuse_previous_form(self):
        class StalePage(FakePage):
            async def goto(self, url, *, wait_until, timeout):
                # Simulates a timing failure before a target navigation begins.
                self.calls.append(url)
                if not self.url:
                    self.url = B.url
                self.snapshots = [FORM]
                raise TimeoutError()
        p = StalePage([])
        outcome = asyncio.run(recover_search_form(p, [A]))
        self.assertFalse(outcome.form_ready)
        self.assertEqual(outcome.observations[0]["reason_code"], "STALE_DOCUMENT_AFTER_TIMEOUT")
