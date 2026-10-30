"""One-click PRADO integration simulation; no Playwright/browser/network needed."""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gate1b_attestation import FORM_JS, RESULT_JS, run_gate_1b
from category_evidence import CATEGORY_FIELDS_JS

HOST = "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch"


class FakeRequest:
    method = "POST"
    resource_type = "xhr"


class FakeResponse:
    url = HOST
    request = FakeRequest()
    status = 200


class FakeCategory:
    def __init__(self, page):
        self.page = page

    async def count(self):
        return 1

    async def select_option(self, *, label, timeout):
        assert label == "Fournitures"
        self.page.selected = True
        self.page.token = "post-category-callback-token-" * 3


class FakeButton:
    def __init__(self, page):
        self.page = page

    async def count(self):
        return 1

    async def click(self, *, timeout, no_wait_after):
        assert no_wait_after is True
        self.page.clicks += 1
        self.page.after = True
        self.page.token = "post-search-response-token-" * 3
        for cb in self.page.listeners.get("response", ()):
            cb(FakeResponse())


class FakePage:
    url = HOST

    def __init__(self, *, hydrated=True):
        self.listeners = {}
        self.hydrated = hydrated
        self.selected = False
        self.after = False
        self.clicks = 0
        self.token = "initial-prado-form-state-token-" * 3

    def locator(self, selector):
        if "AdvancedSearch_categorie" in selector:
            return FakeCategory(self)
        if "lancerRecherche" in selector:
            return FakeButton(self)
        raise AssertionError("Unexpected selector in offline stub")

    def on(self, event, callback):
        self.listeners.setdefault(event, []).append(callback)

    def remove_listener(self, event, callback):
        self.listeners[event].remove(callback)

    async def wait_for_function(self, script, **kwargs):
        if not self.hydrated:
            raise TimeoutError()
        return None

    async def evaluate(self, script, arg=None):
        if script == FORM_JS:
            return dict(category=True, button=True, pagestate=self.hydrated,
                        pagestate_value=self.token if self.hydrated else "",
                        selected_label="Fournitures" if self.selected else "Toutes",
                        ready="complete")
        if script == RESULT_JS:
            return dict(total=100 if self.after else None,
                        count_label=self.after,
                        cards=5 if self.after else 0,
                        first="detail-1" if self.after else "",
                        last="detail-5" if self.after else "")
        if script == CATEGORY_FIELDS_JS:
            assert arg["scope"] == "cards"
            return [dict(status="EXPLICIT", category="fournitures",
                         source="explicit_label_pair") for _ in range(5)]
        raise AssertionError("Unexpected page.evaluate called")


class IntegrationTests(unittest.TestCase):
    def test_ajax_post_happy_path_one_click_only(self):
        page = FakePage()
        result = asyncio.run(run_gate_1b(page, None))
        self.assertEqual(result["status"], "SAMPLED_CONFIRMED", msg=str(result))
        self.assertEqual(result["postback_kind"], "AJAX_POST")
        self.assertEqual(result["postback_http_status"], 200)
        self.assertEqual(result["postback_state"], "APPLIED")
        self.assertEqual(result["results_verification_state"], "CONFIRMED_BY_RESULTS_SAMPLE")
        self.assertEqual(result["sample_rows_checked"], 5)
        self.assertTrue(result["pagestate_changed"])
        self.assertEqual(result["search_clicks"], 1)
        self.assertNotIn("post-category-callback-token", str(result))
        self.assertEqual(len(page.listeners["request"]), 0)
        self.assertEqual(len(page.listeners["response"]), 0)

    def test_form_not_hydrated_never_clicks(self):
        page = FakePage(hydrated=False)
        result = asyncio.run(run_gate_1b(page, None))
        self.assertEqual(result["status"], "UNCONFIRMED")
        self.assertEqual(result["reason_code"], "FORM_HYDRATION_NOT_PROVEN")
        self.assertFalse(result["form_hydrated"])
        self.assertEqual(result["search_clicks"], 0)


if __name__ == "__main__":
    unittest.main()
