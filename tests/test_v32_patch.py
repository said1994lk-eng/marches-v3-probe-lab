"""Offline safety checks for optional V3.2 diagnostic-preview helper."""
import ast
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "apply_v32_integration.py"
spec = importlib.util.spec_from_file_location("preview_patch", SCRIPT)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)


def source_example():
    return '''from full_coverage import SEARCH, PAGE_SIZE, NEXT, PREV, official_count, get_cards, change_page, wait_card_count

async def soft_count(page):
    return 0

async def run(page, health, navigation_index, route_urls, r, category):
    if True:
        if True:
            if True:
                if True:
                    if navigation_index == len(route_urls):
                        raise ValueError("BOTH_OFFICIAL_ROUTES_DOMCONTENTLOADED_TIMEOUT")
    if True:
        if True:
            if True:
                health["dom_after_navigation_" + str(navigation_index)] = await safe_dom_snapshot(page)
                if await category.count():
                    return
'''


class PatchTests(unittest.TestCase):
    def test_preview_is_syntactically_valid_and_once_only(self):
        output = patch.patch_source(source_example())
        ast.parse(output)
        self.assertEqual(output.count('from page_state import classify_playwright_page'), 1)
        self.assertEqual(output.count('health["page_classification_" + str(navigation_index)]'), 2)
        with self.assertRaisesRegex(ValueError, "ALREADY_PATCHED"):
            patch.patch_source(output)

    def test_unexpected_old_script_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNEXPECTED_SOURCE_STRUCTURE"):
            patch.patch_source('print("unexpected")')


if __name__ == "__main__":
    unittest.main()
