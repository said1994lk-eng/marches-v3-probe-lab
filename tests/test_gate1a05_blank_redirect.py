"""Gate 1A-05: offline regression tests for Chromium blank-document timeouts.

No real portal requests, downloads, credentials, or database.
"""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from navigation_destination import classify_destination, is_benign_official_redirect
from navigation_recovery import Route, recover_search_form

BASE = "https://www.marchespublics.gov.ma"
A = Route("primary", BASE + "/?page=entreprise.EntrepriseAdvancedSearch&AllCons&searchAnnCons")
B = Route("secondary", BASE + "/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&EnCours&searchAnnCons")


class BlankRedirectTests(unittest.TestCase):
    def test_about_blank_is_not_external_host(self):
        self.assertEqual(classify_destination("about:blank"), "BROWSER_BLANK_DOCUMENT")
        self.assertFalse(is_benign_official_redirect("BROWSER_BLANK_DOCUMENT"))

    def test_chromium_error_page_is_not_approved(self):
        self.assertEqual(classify_destination("chrome-error://chromewebdata/"), "BROWSER_ERROR_DOCUMENT")
        self.assertFalse(is_benign_official_redirect("BROWSER_ERROR_DOCUMENT"))

    def test_timeout_before_commit_tries_only_remaining_allowed_route(self):
        class Response:
            status = 200

        class FakePage:
            def __init__(self):
                self.url = "about:blank"
                self.calls = []

            async def goto(self, url, *, wait_until, timeout):
                self.calls.append(url)
                if len(self.calls) == 1:
                    self.url = "about:blank"
                    raise TimeoutError()
                self.url = url
                return Response()

            async def evaluate(self, js):
                return {"category_control_found": True, "ready_state": "complete"}

            async def wait_for_timeout(self, ms):
                pass

        page = FakePage()
        result = asyncio.run(recover_search_form(page, [A, B]))
        self.assertTrue(result.form_ready)
        self.assertEqual(result.route_id, "secondary")
        self.assertEqual(result.observations[0]["reason_code"], "NAVIGATION_TIMEOUT_BEFORE_DOCUMENT")
        self.assertEqual(result.observations[0]["destination_class"], "BROWSER_BLANK_DOCUMENT")
        self.assertTrue(result.observations[0]["timed_out"])
        self.assertEqual(len(page.calls), 2)

    def test_about_blank_without_timeout_stops(self):
        class Response:
            status = 200

        class FakePage:
            url = "about:blank"

            def __init__(self):
                self.calls = []

            async def goto(self, url, *, wait_until, timeout):
                self.calls.append(url)
                return Response()

            async def evaluate(self, js):
                raise AssertionError("blank document is not evidence of a search form")

        page = FakePage()
        result = asyncio.run(recover_search_form(page, [A, B]))
        self.assertFalse(result.form_ready)
        self.assertEqual(result.observations[0]["destination_class"], "BROWSER_BLANK_DOCUMENT")
        self.assertFalse(result.observations[0]["timed_out"])
        self.assertEqual(len(page.calls), 1)

    def test_external_destination_still_stops_and_does_not_log_url(self):
        class Response:
            status = 200

        class FakePage:
            url = "https://other.example/?secret=do-not-log"

            def __init__(self):
                self.calls = []

            async def goto(self, url, *, wait_until, timeout):
                self.calls.append(url)
                return Response()

            async def evaluate(self, js):
                raise AssertionError("external document must not be inspected")

        page = FakePage()
        result = asyncio.run(recover_search_form(page, [A, B]))
        self.assertFalse(result.form_ready)
        self.assertEqual(len(page.calls), 1)
        self.assertNotIn("do-not-log", str(result.as_report()))
        self.assertEqual(result.observations[0]["destination_class"], "UNTRUSTED_DESTINATION")


if __name__ == "__main__":
    unittest.main()
