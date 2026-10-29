"""Assure default standalone probe cannot accidentally contact the portal."""
import asyncio
import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import gate1a02_probe


class ProbeSafetyTests(unittest.TestCase):
    def test_live_disabled_by_default(self):
        before = os.environ.pop("ENABLE_LIVE_GATE1A02", None)
        try:
            r = asyncio.run(gate1a02_probe.run())
        finally:
            if before is not None:
                os.environ["ENABLE_LIVE_GATE1A02"] = before
        self.assertEqual(r["status"], "LIVE_TEST_DISABLED")
        self.assertEqual(r["database_writes"], 0)
        self.assertEqual(r["documents_downloaded"], 0)
        self.assertFalse(r["coverage_claimed"])
        self.assertFalse(r["pagination_started"])

    def test_no_unnecessary_live_import(self):
        self.assertFalse("playwright.async_api" in sys.modules)


if __name__ == "__main__": unittest.main()
