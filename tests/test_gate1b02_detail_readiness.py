"""Offline parsed-document and late PRADO-label readiness regressions."""
import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gate1b02_detail_readiness import (
    CATEGORY_LABEL_JS, PARSED_HTML_JS, DETAIL_TELEMETRY_JS,
    detail_telemetry, wait_detail_readiness,
)


class StubDetail:
    def __init__(self, *, parsed=True, late_label=False, initial_label=False,
                 title="OTHER"):
        self.parsed=parsed
        self.late_label=late_label
        self.label=initial_label
        self.title=title
        self.waits=[]

    async def wait_for_function(self, script, *, timeout):
        self.waits.append((script,timeout))
        if script == PARSED_HTML_JS and not self.parsed:
            raise TimeoutError("url-and-document-secret-should-not-leak")
        if script == CATEGORY_LABEL_JS:
            if not self.late_label:
                raise TimeoutError("detail-title-should-not-leak")
            self.label=True

    async def evaluate(self, script):
        assert script == DETAIL_TELEMETRY_JS
        return {
            "ready_state":"interactive" if self.parsed else "loading",
            "category_label_present":self.label,
            "dom_html_bytes":1513,
            "dom_html_bytes_capped":False,
            "body_text_bucket":"MEDIUM" if self.parsed else "ZERO",
            "title_class":self.title,
            "full_page_title":"DO NOT EXPORT ANY PRIVATE TITLE",
        }


class ReadinessTests(unittest.TestCase):
    def test_late_label_gets_extra_bounded_wait(self):
        page=StubDetail(late_label=True)
        result=asyncio.run(wait_detail_readiness(page,parse_timeout_ms=4000,
                                                 label_timeout_ms=1000))
        self.assertEqual(result["status"],"READY_EXPLICIT_LABEL_VISIBLE")
        self.assertEqual([s for s,t in page.waits],[PARSED_HTML_JS,CATEGORY_LABEL_JS])
        self.assertEqual(result["telemetry"]["dom_html_bytes"],1513)
        self.assertNotIn("DO NOT EXPORT",str(result))

    def test_initial_label_does_not_wait_again(self):
        page=StubDetail(initial_label=True)
        result=asyncio.run(wait_detail_readiness(page))
        self.assertEqual(result["status"],"READY_EXPLICIT_LABEL_VISIBLE")
        self.assertEqual(len(page.waits),1)

    def test_missing_label_does_not_become_confirmed(self):
        page=StubDetail()
        result=asyncio.run(wait_detail_readiness(page,parse_timeout_ms=4000,
                                                 label_timeout_ms=1000))
        self.assertEqual(result["status"],"READY_NO_EXPLICIT_LABEL")
        self.assertFalse(result["telemetry"]["category_label_present"])

    def test_no_parsed_dom_is_distinct(self):
        page=StubDetail(parsed=False)
        result=asyncio.run(wait_detail_readiness(page,parse_timeout_ms=4000,
                                                 label_timeout_ms=1000))
        self.assertEqual(result["status"],"DETAIL_DOCUMENT_NOT_PARSED")
        self.assertEqual(result["telemetry"]["ready_state"],"loading")
        self.assertEqual(len(page.waits),1)
        self.assertNotIn("url-and-document",str(result))

    def test_invalid_wait_bounds(self):
        with self.assertRaisesRegex(ValueError,"UNSAFE_READINESS_TIMEOUT"):
            asyncio.run(wait_detail_readiness(StubDetail(),label_timeout_ms=9000))

    def test_title_enum_not_raw_text(self):
        p=StubDetail(title="LOGIN_LIKE")
        r=asyncio.run(detail_telemetry(p))
        self.assertEqual(r["title_class"],"LOGIN_LIKE")
        self.assertNotIn("PRIVATE TITLE",str(r))

    def test_unknown_title_is_redacted(self):
        p=StubDetail(title="Actual Tender Buyer: Person XYZ")
        r=asyncio.run(detail_telemetry(p))
        self.assertEqual(r["title_class"],"UNKNOWN")
        self.assertNotIn("Person XYZ",str(r))

    def test_html_bytes_are_dom_metadata_not_network_bytes(self):
        p=StubDetail()
        r=asyncio.run(detail_telemetry(p))
        self.assertEqual(r["dom_html_bytes"],1513)
        self.assertNotIn("raw_html",r)

    def test_reject_boolean_html_length(self):
        class P:
            async def evaluate(self,script):
                return {"ready_state":"complete","dom_html_bytes":True,
                        "title_class":"OTHER","category_label_present":False}
        r=asyncio.run(detail_telemetry(P()))
        self.assertIsNone(r["dom_html_bytes"])

    def test_label_wait_optional(self):
        p=StubDetail()
        r=asyncio.run(wait_detail_readiness(p,label_timeout_ms=0))
        self.assertEqual(r["status"],"READY_NO_EXPLICIT_LABEL")
        self.assertEqual(len(p.waits),1)


if __name__=="__main__":
    unittest.main()
