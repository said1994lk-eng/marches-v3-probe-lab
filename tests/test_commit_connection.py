"""Offline regression: commit navigation and public DOM readiness separation."""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from navigation_recovery import Route, recover_search_form

SEARCH = "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&EnCours&searchAnnCons"
ROUTE = Route("primary", SEARCH)


class Response:
    status = 200


class SimulatedCommitPage:
    def __init__(self, ready_after_wait=True):
        self.url = "about:blank"
        self.ready_after_wait = ready_after_wait
        self.markers_visible = False
        self.wait_mode = None
        self.calls = 0
        self.public_wait_calls = 0

    async def goto(self, url, *, wait_until, timeout):
        self.url = url
        self.wait_mode = wait_until
        self.calls += 1
        # The document committed but the app has not rendered its controls.
        return Response()

    async def wait_for_function(self, script, *, timeout):
        self.public_wait_calls += 1
        if not (0 < timeout <= 10000):
            raise AssertionError("unbounded wait")
        if self.ready_after_wait:
            self.markers_visible = True
        else:
            raise TimeoutError("hidden details must not appear in report")

    async def evaluate(self, script):
        if self.markers_visible:
            return {
                "category_control_found": True,
                "ready_state": "interactive",
                "tender_cards": 0,
            }
        return {
            "category_control_found": False,
            "ready_state": "loading",
            "body_text_length": 0,
            "body_html_length": 0,
        }

    async def wait_for_timeout(self, ms):
        pass


class CommitConnectionTests(unittest.TestCase):
    def test_commit_followed_by_public_dom_success(self):
        page = SimulatedCommitPage(True)
        result = asyncio.run(recover_search_form(page, [ROUTE]))
        self.assertTrue(result.form_ready)
        self.assertEqual(page.wait_mode, "commit")
        self.assertEqual(page.public_wait_calls, 1)
        self.assertEqual(page.calls, 1)

    def test_commit_without_dom_does_not_pass(self):
        page = SimulatedCommitPage(False)
        result = asyncio.run(recover_search_form(page, [ROUTE]))
        self.assertFalse(result.form_ready)
        self.assertEqual(result.reason_code, "NAVIGATION_INCOMPLETE")
        self.assertEqual(page.calls, 1)

    def test_no_filter_claim_from_navigation(self):
        page = SimulatedCommitPage(True)
        result = asyncio.run(recover_search_form(page, [ROUTE]))
        self.assertFalse(result.as_report()["filter_attested"])


if __name__ == "__main__":
    unittest.main()
