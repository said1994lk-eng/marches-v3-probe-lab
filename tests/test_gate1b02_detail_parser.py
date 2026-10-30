"""Pure safety and schema checks for the strict detail label parser."""
import asyncio
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from gate1b02_detail_parser import DETAIL_CATEGORY_JS, strict_detail_category


class ParserSafetyTests(unittest.TestCase):
    def test_whitelist_explicit_category(self):
        class Page:
            async def evaluate(self,script):
                return {"status":"EXPLICIT","category":"fournitures",
                        "source":"explicit_label_pair","context":"BODY_FALLBACK",
                        "explicit_label_nodes":1,"body_text_bucket":"LONG",
                        "ready_state":"complete","raw_secret":"never_export"}
        data=asyncio.run(strict_detail_category(Page()))
        self.assertEqual(data["category"],"fournitures")
        self.assertNotIn("raw_secret",str(data))
        self.assertEqual(data["context"],"BODY_FALLBACK")

    def test_unknown_category_rejected(self):
        class Page:
            async def evaluate(self,script):
                return {"status":"EXPLICIT","category":"other","source":"explicit_label_pair"}
        data=asyncio.run(strict_detail_category(Page()))
        self.assertEqual(data["status"],"MISSING")
        self.assertIsNone(data["category"])

    def test_attribute_source_rejected(self):
        class Page:
            async def evaluate(self,script):
                return {"status":"EXPLICIT","category":"fournitures","source":"image_alt"}
        data=asyncio.run(strict_detail_category(Page()))
        self.assertEqual(data["status"],"MISSING")

    def test_page_text_does_not_leave_browser(self):
        self.assertNotIn("outerHTML",DETAIL_CATEGORY_JS)
        self.assertNotIn("PRADO_PAGESTATE",DETAIL_CATEGORY_JS)
        self.assertNotIn("cookie",DETAIL_CATEGORY_JS)

    def test_no_raw_detail_strings_in_report(self):
        class Page:
            async def evaluate(self,script):
                return {"status":"MISSING","category":None,"source":None,
                        "context":"BODY_FALLBACK","body_text_bucket":"LONG",
                        "full_html":"private-value"}
        data=asyncio.run(strict_detail_category(Page()))
        self.assertNotIn("private-value",str(data))


if __name__=="__main__":
    unittest.main()
