"""Offline Gate 1A-02 independent filter evidence tests."""
import asyncio
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from filter_attestation import Proof, attest_filter, can_start_collection, select_fournitures_and_observe


def assess(**kwargs):
    base = dict(selected_label="Fournitures", retained_label="Fournitures",
                result_categories=["Fournitures"] * 5, official_total=100,
                trusted_category_source=True)
    base.update(kwargs)
    return attest_filter(**base)


class Tests(unittest.TestCase):
    def test_trusted_source_labelled_sample_passes(self):
        e = assess()
        self.assertTrue(e.effect_confirmed)
        self.assertTrue(can_start_collection(e))
        self.assertEqual(e.verified_categories, 5)

    def test_selected_only_is_not_proof(self):
        e = assess(result_categories=None)
        self.assertEqual(e.effect, Proof.UNCONFIRMED)
        self.assertFalse(can_start_collection(e))

    def test_untrusted_categories_are_not_proof(self):
        e = assess(trusted_category_source=False)
        self.assertFalse(e.effect_confirmed)

    def test_changed_total_does_not_prove_filter(self):
        e = assess(result_categories=None, official_total=12)
        self.assertFalse(e.effect_confirmed)

    def test_category_missing_from_result(self):
        e = assess(result_categories=["Fournitures"]*4 + [None])
        self.assertEqual(e.reason_code, "SOME_RESULT_CATEGORIES_MISSING")

    def test_wrong_category_observed(self):
        e = assess(result_categories=["Fournitures"]*4 + ["Travaux"])
        self.assertEqual(e.effect, Proof.CONTRADICTED)

    def test_post_search_selection_lost(self):
        e = assess(retained_label="Travaux")
        self.assertEqual(e.reason_code, "CATEGORY_NOT_RETAINED_AFTER_SEARCH")

    def test_post_search_selection_not_visible(self):
        e = assess(retained_label=None)
        self.assertFalse(e.effect_confirmed)

    def test_initial_selection_not_confirmed(self):
        e = assess(selected_label="Services")
        self.assertFalse(e.effect_confirmed)

    def test_small_official_total_all_rows_match(self):
        e = assess(result_categories=["Fournitures"]*3, official_total=3)
        self.assertTrue(e.effect_confirmed)

    def test_insufficient_sample(self):
        e = assess(result_categories=["Fournitures"]*3, official_total=10)
        self.assertEqual(e.reason_code, "INSUFFICIENT_CATEGORY_SAMPLE")

    def test_empty_official_total_not_proven(self):
        e = assess(result_categories=[], official_total=0)
        self.assertFalse(e.effect_confirmed)

    def test_official_total_must_be_int(self):
        e = assess(official_total=None)
        self.assertFalse(e.effect_confirmed)

    def test_accents_and_whitespace_normalized(self):
        e = assess(selected_label="  Fournitures  ", retained_label="FOURNITURES", result_categories=["FOURNITURES"]*5)
        self.assertTrue(e.effect_confirmed)

    def test_cannot_pass_invalid_minimum(self):
        with self.assertRaises(ValueError): assess(minimum_observed=0)

    def test_report_contains_no_source_text_or_urls(self):
        s = json.dumps(assess().as_report())
        self.assertNotIn("http", s)
        self.assertIn('"effect_confirmed": true', s)

    def test_unverified_postback_returns_unconfirmed(self):
        class Selected:
            async def inner_text(self): return "Fournitures"
        class Category:
            async def count(self): return 1
            async def select_option(self, **kwargs): return None
            def locator(self, selector): return Selected()
        class Search:
            async def click(self, **kwargs): return None
        class Count:
            @property
            def first(self): return self
            async def wait_for(self, **kwargs): return None
        class Page:
            def locator(self, selector):
                if "AdvancedSearch_categorie" in selector: return Category()
                if "lancerRecherche" in selector: return Search()
                return Count()
        result = asyncio.run(select_fournitures_and_observe(Page()))
        self.assertFalse(result["effect_confirmed"])
        self.assertEqual(result["reason_code"], "NO_INDEPENDENT_RESULT_CATEGORY_EVIDENCE")


if __name__ == "__main__": unittest.main()


class ResultLabelExtractionTests(unittest.TestCase):
    def test_labels_are_extracted_only_from_result_cards(self):
        from filter_attestation import observe_categories_in_cards
        class FakePage:
            async def evaluate(self, js, selector):
                self.js, self.selector = js, selector
                return ["Fournitures", None, "Travaux"]
        page = FakePage()
        categories = asyncio.run(observe_categories_in_cards(page, selector_within_card=".category-label"))
        self.assertEqual(categories, ["Fournitures", None, "Travaux"])
        self.assertIn(".tender_item", page.js)
        self.assertEqual(page.selector, ".category-label")

    def test_empty_selector_rejected(self):
        from filter_attestation import observe_categories_in_cards
        with self.assertRaises(ValueError):
            asyncio.run(observe_categories_in_cards(object(), selector_within_card=""))
