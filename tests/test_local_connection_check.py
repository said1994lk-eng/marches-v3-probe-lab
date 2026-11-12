"""No-network safety regression tests for the user-operated Windows launcher."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from local_connection_check import (
    CATEGORY_FLAG, CONNECTION_FLAG, compact_safe_output,
    execute_once, save_report,
)


class LocalConnectionCheckTests(unittest.TestCase):
    def test_category_requires_explicit_flag_without_network(self):
        report = asyncio.run(execute_once("category"))
        self.assertEqual(report["status"], "EXPLICIT_CONFIRMATION_REQUIRED")
        self.assertFalse(report["filter_attested"])

    def test_invalid_mode_is_fail_closed(self):
        report = asyncio.run(execute_once("something_else"))
        self.assertEqual(report["status"], "EXPLICIT_CONFIRMATION_REQUIRED")

    def test_redacts_url_and_raw_html_values(self):
        data = {
            "status": "FORM_READY_CONFIRMED_ONCE",
            "navigation": {
                "form_ready": True,
                "observations": [{"route_id": "official_menu_exact",
                                  "http_status": 200, "state": "FORM_READY"}],
                "redirect_url": "https://site.example/?token=hidden",
                "raw_html": "<html>secret</html>",
            },
            "secret_key": {"cookie": "one@private.example"},
        }
        safe = compact_safe_output(data)
        self.assertEqual(safe["navigation"]["redirect_url"], "REDACTED")
        self.assertEqual(safe["navigation"]["raw_html"], "REDACTED")
        self.assertEqual(safe["secret_key"]["cookie"], "REDACTED")
        self.assertTrue(safe["navigation"]["form_ready"])
        self.assertEqual(safe["navigation"]["observations"][0]["http_status"], 200)

    def test_reports_are_local_only(self):
        with tempfile.TemporaryDirectory() as temp:
            target = save_report({"status": "FORM_READY_CONFIRMED_ONCE"},
                                 "connection", Path(temp))
            data = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "FORM_READY_CONFIRMED_ONCE")
            self.assertEqual(target.parent, Path(temp))
            self.assertTrue(target.name.startswith("local_connection_"))

    def test_launcher_does_not_embed_credentials_or_proxies(self):
        for file in ("01-Test-Connexion-Windows.cmd",
                     "02-Fournitures-Une-Fiche-Windows.cmd"):
            s = (ROOT / "scripts" / file).read_text(encoding="utf-8").lower()
            self.assertNotIn("password=", s)
            self.assertNotIn("http_proxy=", s)
            self.assertNotIn("https_proxy=", s)
            self.assertNotIn("captcha", s)
            self.assertNotIn("workflow_dispatch", s)

    def test_manual_category_mode_has_explicit_ack(self):
        content = (ROOT / "scripts" /
                   "02-Fournitures-Une-Fiche-Windows.cmd").read_text(encoding="utf-8")
        self.assertIn("--ack-one-post-one-detail", content)
        self.assertIn("choice /C ON", content)

    def test_no_retry_or_download_in_wrapper(self):
        content = (ROOT / "scripts" /
                   "local_connection_check.py").read_text(encoding="utf-8")
        self.assertNotIn("page.reload(", content)
        self.assertNotIn("goto(", content)
        self.assertNotIn("download(", content)
        self.assertIn("gate1a09_exact_public_search", content)
        self.assertIn("gate1b02_probe", content)

    def test_public_mode_flags_are_disjoint(self):
        self.assertNotEqual(CONNECTION_FLAG, CATEGORY_FLAG)


if __name__ == "__main__":
    unittest.main()
