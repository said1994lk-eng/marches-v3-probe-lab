"""Offline Gate 1A-07 regression tests; no live network or Playwright import."""
import asyncio
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import connectivity_gate1a07 as gate


class ClassifierTests(unittest.TestCase):
    def test_dns_exception(self):
        import socket
        self.assertEqual(gate.failure_code(socket.gaierror(-2, "hidden")), "DNS_FAILURE")

    def test_tcp_timeout(self):
        self.assertEqual(gate.failure_code(TimeoutError("site info")), "TIMEOUT")

    def test_ssl_verification(self):
        import ssl
        self.assertEqual(gate.failure_code(
            ssl.SSLCertVerificationError("sensitive")), "TLS_CERT_VERIFICATION_FAILURE")

    def test_ordinary_network_error(self):
        self.assertEqual(gate.failure_code(OSError("secret.host")), "NETWORK_IO_ERROR")

    def test_browser_error_sanitized(self):
        text = "Page.goto: net::ERR_CONNECTION_TIMED_OUT at https://private.example/?token=123"
        result = gate.sanitized_browser_failure(text)
        self.assertEqual(result, "ERR_CONNECTION_TIMED_OUT")
        self.assertNotIn("private", result)
        self.assertNotIn("token", result)

    def test_unrecognized_browser_error_safe(self):
        self.assertEqual(gate.sanitized_browser_failure(
            "Page.goto: personal@example.com"), "UNCLASSIFIED")

    def test_cannot_probe_arbitrary_host(self):
        with self.assertRaisesRegex(ValueError, "HOST_NOT_APPROVED"):
            gate.probe_host("private.example", "/")

    def test_cannot_probe_arbitrary_path(self):
        with self.assertRaisesRegex(ValueError, "SEARCH_PATH_NOT_APPROVED"):
            gate.probe_host(gate.PORTAL, "/secret")

    def test_no_unbounded_timeout(self):
        with self.assertRaisesRegex(ValueError, "TIMEOUT_OUT_OF_BOUNDS"):
            gate.probe_host(gate.PORTAL, gate.SEARCH_PATH, timeout=600)

    def test_result_cards_not_form_success(self):
        portal = {"dns": "RESOLVED", "tcp_tls": "VERIFIED", "http": "RESPONSE_RECEIVED"}
        control = {"tcp_tls": "VERIFIED"}
        browser = {"status": "FORM_NOT_CONFIRMED", "routes": [{"page_state": "RESULTS_VIEW"}]}
        self.assertEqual(gate.determine_outcome(portal, control, browser),
                         "HTTP_REACHABLE_BROWSER_FORM_UNCONFIRMED")

    def test_form_ready_once_is_not_stability_claim(self):
        self.assertEqual(gate.determine_outcome({}, {}, {"status": "FORM_READY_CONFIRMED"}),
                         "SEARCH_FORM_REACHABLE_ONCE")

    def test_portal_dns_failure_is_distinct(self):
        self.assertEqual(gate.determine_outcome(
            {"dns": "FAILED", "tcp_tls": "NOT_RUN"}, {"tcp_tls": "VERIFIED"},
            {"status": "FORM_NOT_CONFIRMED"}), "PORTAL_DNS_NOT_RELIABLE")

    def test_portal_tls_failure_is_distinct(self):
        self.assertEqual(gate.determine_outcome(
            {"dns": "RESOLVED", "tcp_tls": "FAILED"}, {"tcp_tls": "VERIFIED"},
            {"status": "FORM_NOT_CONFIRMED"}), "PORTAL_TLS_OR_TCP_UNAVAILABLE")

    def test_runner_control_failure_is_distinct(self):
        self.assertEqual(gate.determine_outcome(
            {"dns": "RESOLVED", "tcp_tls": "VERIFIED"}, {"tcp_tls": "FAILED"},
            {"status": "FORM_NOT_CONFIRMED"}), "RUNNER_NETWORK_BASELINE_UNAVAILABLE")

    def test_403_browser_always_blocks_success(self):
        self.assertEqual(gate.determine_outcome(
            {"dns": "RESOLVED", "tcp_tls": "VERIFIED"},
            {"tcp_tls": "VERIFIED"}, {"status": "ACCESS_DENIED_OR_RATE_LIMITED"}),
            "ACCESS_DENIED_OR_RATE_LIMITED")

    def test_no_network_without_explicit_opt_in(self):
        previous = os.environ.pop("ENABLE_LIVE_CONNECTIVITY_DIAGNOSTICS", None)
        try:
            result = asyncio.run(gate.run())
        finally:
            if previous is not None:
                os.environ["ENABLE_LIVE_CONNECTIVITY_DIAGNOSTICS"] = previous
        self.assertEqual(result["status"], "LIVE_DIAGNOSTICS_DISABLED")
        self.assertIsNone(result["portal"])
        self.assertIsNone(result["browser"])
        self.assertEqual(result["database_writes"], 0)
        self.assertFalse(result["filter_attested"])

    def test_two_search_routes_only(self):
        self.assertEqual(len(gate.ROUTES), 2)
        self.assertTrue(all("www.marchespublics.gov.ma" in url for url in gate.ROUTES))


if __name__ == "__main__":
    unittest.main()
