"""Gate 1A-04 must not touch network when no explicit opt-in is present."""
import asyncio
import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import gate1a04_probe

class SafeMode(unittest.TestCase):
    def test_off_by_default(self):
        old=os.environ.pop('ENABLE_LIVE_GATE1A04',None)
        try:r=asyncio.run(gate1a04_probe.run())
        finally:
            if old is not None:os.environ['ENABLE_LIVE_GATE1A04']=old
        self.assertEqual(r['status'],'LIVE_DISABLED')
        self.assertEqual(r['db_writes'],0)
        self.assertEqual(r['downloads'],0)
        self.assertFalse(r['pagination_started'])
        self.assertFalse(r['coverage_claimed'])
    def test_no_playwright_import_needed_for_offline(self):
        self.assertNotIn('playwright.async_api',sys.modules)
if __name__=='__main__':unittest.main()