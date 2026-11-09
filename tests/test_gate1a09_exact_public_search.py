"""Gate 1A-09 exact official public entry: offline safety and route tests."""
import asyncio
import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))

from gate1a09_exact_public_search import (
    PUBLIC_MENU_URL, SECONDARY, ROUTES, blank_report, run
)
from navigation_recovery import is_allowed_search_url
from navigation_destination import classify_destination


class ExactLinkTests(unittest.TestCase):
    def test_public_home_link_has_exact_source_query(self):
        self.assertTrue(PUBLIC_MENU_URL.endswith(
            "/index.php?page=entreprise.EntrepriseAdvancedSearch&searchAnnCons="))
        self.assertNotIn("AllCons",PUBLIC_MENU_URL)

    def test_public_menu_link_is_official_and_approved(self):
        self.assertTrue(is_allowed_search_url(PUBLIC_MENU_URL))
        self.assertEqual(classify_destination(PUBLIC_MENU_URL),
                         "OFFICIAL_ADVANCED_SEARCH_ROUTE")

    def test_legacy_fallback_still_approved(self):
        self.assertTrue(is_allowed_search_url(SECONDARY))

    def test_only_two_direct_routes_with_unique_ids(self):
        self.assertEqual(len(ROUTES),2)
        self.assertEqual({r.id for r in ROUTES},
                         {"official_menu_exact","legacy_secondary"})
        self.assertEqual([r.url for r in ROUTES],[PUBLIC_MENU_URL,SECONDARY])

    def test_no_portal_scan_claim(self):
        result=blank_report()
        self.assertFalse(result["filter_attested"])
        self.assertFalse(result["form_reachable"])
        self.assertFalse(result["pagination_started"])
        self.assertEqual(result["database_writes"],0)
        self.assertEqual(result["dce_downloads"],0)

    def test_disabled_by_default_no_network(self):
        original=os.environ.pop("ENABLE_LIVE_GATE1A09",None)
        try: r=asyncio.run(run())
        finally:
            if original is not None:
                os.environ["ENABLE_LIVE_GATE1A09"]=original
        self.assertEqual(r["status"],"LIVE_DISABLED")
        self.assertIsNone(r["navigation"])


if __name__=="__main__":
    unittest.main()
