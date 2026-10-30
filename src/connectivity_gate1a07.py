"""Gate 1A-07: conservative connection diagnostics for the public portal.

No proxy rotation, CAPTCHA, login, credentials, DCE, database, POST, or bulk
collection. One DNS/TLS/HTTP check each for the official portal and a control,
followed by at most two approved browser navigation attempts.
Raw URLs, query values, IPs, headers, cookies and HTML never enter reports.
"""
from __future__ import annotations

import asyncio
import http.client
import json
import os
import re
import socket
import ssl
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from navigation_destination import classify_destination
from page_state import classify_playwright_page

PORTAL = "www.marchespublics.gov.ma"
CONTROL = "github.com"
SEARCH_PATH = "/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&EnCours&searchAnnCons"
ROUTES = (
    "https://www.marchespublics.gov.ma/?page=entreprise.EntrepriseAdvancedSearch&AllCons&searchAnnCons",
    "https://www.marchespublics.gov.ma" + SEARCH_PATH,
)
NET_ERRORS = (
    "ERR_NAME_NOT_RESOLVED", "ERR_DNS_TIMED_OUT", "ERR_CONNECTION_TIMED_OUT",
    "ERR_CONNECTION_RESET", "ERR_CONNECTION_REFUSED", "ERR_TUNNEL_CONNECTION_FAILED",
    "ERR_PROXY_CONNECTION_FAILED", "ERR_CERT_AUTHORITY_INVALID",
    "ERR_CERT_COMMON_NAME_INVALID", "ERR_SSL_PROTOCOL_ERROR", "ERR_EMPTY_RESPONSE",
    "ERR_HTTP_RESPONSE_CODE_FAILURE", "ERR_TIMED_OUT", "ERR_NETWORK_CHANGED",
)


def failure_code(error: object) -> str:
    """Classify an exception without exporting exception text/URLs."""
    if isinstance(error, socket.gaierror):
        return "DNS_FAILURE"
    if isinstance(error, ssl.SSLCertVerificationError):
        return "TLS_CERT_VERIFICATION_FAILURE"
    if isinstance(error, ssl.SSLError):
        return "TLS_FAILURE"
    if isinstance(error, (TimeoutError, socket.timeout)):
        return "TIMEOUT"
    if isinstance(error, ConnectionRefusedError):
        return "TCP_REFUSED"
    if isinstance(error, ConnectionResetError):
        return "CONNECTION_RESET"
    if isinstance(error, OSError):
        return "NETWORK_IO_ERROR"
    name = type(error).__name__
    if name in {"TimeoutError", "PlaywrightTimeoutError"}:
        return "TIMEOUT"
    return "UNCLASSIFIED_EXCEPTION"


def sanitized_browser_failure(value: object) -> str:
    """Return a finite error code, not a Playwright message containing a URL."""
    if not isinstance(value, str):
        return "UNCLASSIFIED"
    upper = value.upper()
    for code in NET_ERRORS:
        if code in upper:
            return code
    if "TIMEOUT" in upper or "TIMED OUT" in upper:
        return "TIMEOUT"
    return "UNCLASSIFIED"


def probe_host(host: str, path: str, *, timeout: float = 5.0) -> dict:
    """One DNS lookup, one verified TLS handshake and one GET (no redirects).

    Both hosts are constants controlled by the caller. Never use untrusted
    external hostnames as probes. All HTTP response bodies are discarded.
    A 403 from Python's HTTP client does NOT prove browser unavailability.
    """
    if host not in (PORTAL, CONTROL):
        raise ValueError("HOST_NOT_APPROVED")
    if host == PORTAL and path != SEARCH_PATH:
        raise ValueError("SEARCH_PATH_NOT_APPROVED")
    if host == CONTROL and path != "/":
        raise ValueError("CONTROL_PATH_NOT_APPROVED")
    if not 1.0 <= timeout <= 10.0:
        raise ValueError("TIMEOUT_OUT_OF_BOUNDS")
    result = {
        "dns": "NOT_RUN", "tcp_tls": "NOT_RUN", "http": "NOT_RUN",
        "http_status": None, "error": None,
    }
    try:
        found = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        if not found:
            result["dns"] = "NO_ADDRESS"
            return result
        result["dns"] = "RESOLVED"
    except Exception as exc:
        result["dns"] = "FAILED"
        result["error"] = failure_code(exc)
        return result
    try:
        with socket.create_connection((host, 443), timeout=timeout) as sock:
            with ssl.create_default_context().wrap_socket(sock, server_hostname=host):
                result["tcp_tls"] = "VERIFIED"
    except Exception as exc:
        result["tcp_tls"] = "FAILED"
        result["error"] = failure_code(exc)
        return result
    conn = http.client.HTTPSConnection(host, timeout=timeout, context=ssl.create_default_context())
    try:
        conn.request("GET", path, headers={
            "User-Agent": "MarchesIntelligence-Connectivity-Diagnostic/1.0",
            "Accept": "text/html",
        })
        response = conn.getresponse()
        result["http_status"] = response.status
        result["http"] = "RESPONSE_RECEIVED"
        # Do not consume or publish HTML, headers, redirect Location, or IDs.
    except Exception as exc:
        result["http"] = "FAILED"
        result["error"] = failure_code(exc)
    finally:
        conn.close()
    return result


async def browser_probe() -> dict:
    """Try the two already-approved public URLs once each using early commit."""
    from playwright.async_api import async_playwright
    output = {"status": "NOT_STARTED", "routes": [], "request_failures": []}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            context = await browser.new_context(locale="fr-FR", accept_downloads=False)
            page = await context.new_page()

            def failed(req):
                try:
                    if req.is_navigation_request() and len(output["request_failures"]) < 4:
                        output["request_failures"].append(
                            sanitized_browser_failure(req.failure)
                        )
                except Exception:
                    pass

            page.on("requestfailed", failed)
            for index, url in enumerate(ROUTES, start=1):
                attempt = {
                    "route": "primary" if index == 1 else "secondary",
                    "goto": "NOT_STARTED", "elapsed_ms": None,
                    "http_status": None, "destination_class": "UNKNOWN_DESTINATION",
                    "page_state": "NOT_INSPECTED", "page_reason": None,
                }
                output["routes"].append(attempt)
                started = time.monotonic()
                response = None
                try:
                    # 'commit' returns on first document response, avoiding the
                    # unrelated DOMContentLoaded wait that blocked earlier runs.
                    response = await page.goto(url, wait_until="commit", timeout=17000)
                    attempt["goto"] = "DOCUMENT_COMMITTED"
                    attempt["http_status"] = response.status if response else None
                except Exception as exc:
                    attempt["goto"] = failure_code(exc)
                    attempt["browser_error"] = sanitized_browser_failure(str(exc))
                attempt["elapsed_ms"] = round((time.monotonic() - started) * 1000)
                landed = classify_destination(page.url)
                attempt["destination_class"] = landed

                if attempt["http_status"] in (401, 403, 429):
                    output["status"] = "ACCESS_DENIED_OR_RATE_LIMITED"
                    break
                if landed in {"UNTRUSTED_DESTINATION", "OFFICIAL_AUTH_WALL",
                              "UNRECOGNIZED_OFFICIAL_PATH", "UNRECOGNIZED_OFFICIAL_PAGE",
                              "UNRECOGNIZED_OFFICIAL_QUERY"}:
                    output["status"] = "UNAPPROVED_DESTINATION"
                    break
                if attempt["goto"] != "DOCUMENT_COMMITTED":
                    continue
                if landed != "OFFICIAL_ADVANCED_SEARCH_ROUTE":
                    continue
                try:
                    await page.wait_for_function("""() =>
                        !!document.querySelector('#ctl0_CONTENU_PAGE_AdvancedSearch_categorie')
                        || !!document.querySelector('.tender_item')
                        || /Nombre de r[eé]sultats/i.test(document.body?.innerText || '')
                    """, timeout=9000)
                except Exception:
                    pass
                try:
                    observed = await classify_playwright_page(page, http_status=attempt["http_status"])
                    attempt["page_state"] = observed["state"]
                    attempt["page_reason"] = observed["reason_code"]
                    if observed["state"] == "FORM_READY":
                        output["status"] = "FORM_READY_CONFIRMED"
                        break
                    if observed["state"] == "ERROR_PAGE":
                        output["status"] = "PUBLIC_PAGE_ERROR"
                        break
                except Exception:
                    attempt["page_state"] = "UNREADABLE"
            else:
                output["status"] = "FORM_NOT_CONFIRMED"
            if output["status"] == "NOT_STARTED":
                output["status"] = "FORM_NOT_CONFIRMED"
        finally:
            await browser.close()
    return output


def determine_outcome(portal: dict, control: dict, browser: dict) -> str:
    """Do not equate HTTP 200 or a browser results page to usable search."""
    if browser.get("status") == "FORM_READY_CONFIRMED":
        return "SEARCH_FORM_REACHABLE_ONCE"
    if browser.get("status") in {"ACCESS_DENIED_OR_RATE_LIMITED", "UNAPPROVED_DESTINATION"}:
        return browser["status"]
    if portal.get("dns") != "RESOLVED":
        return "PORTAL_DNS_NOT_RELIABLE"
    if portal.get("tcp_tls") != "VERIFIED":
        return "PORTAL_TLS_OR_TCP_UNAVAILABLE"
    if control.get("tcp_tls") != "VERIFIED":
        return "RUNNER_NETWORK_BASELINE_UNAVAILABLE"
    if portal.get("http") == "RESPONSE_RECEIVED":
        return "HTTP_REACHABLE_BROWSER_FORM_UNCONFIRMED"
    return "PORTAL_HTTP_AND_BROWSER_UNCONFIRMED"


async def run() -> dict:
    report = {
        "schema": "marches-source-connectivity-gate1a07/1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "PUBLIC_READONLY_NO_DCE_NO_DB",
        "status": "LIVE_DIAGNOSTICS_DISABLED",
        "portal": None, "control": None, "browser": None,
        "filter_attested": False, "coverage_claimed": False,
        "database_writes": 0, "documents_downloaded": 0,
    }
    if os.environ.get("ENABLE_LIVE_CONNECTIVITY_DIAGNOSTICS") != "1":
        return report
    report["portal"] = await asyncio.to_thread(probe_host, PORTAL, SEARCH_PATH)
    report["control"] = await asyncio.to_thread(probe_host, CONTROL, "/")
    try:
        report["browser"] = await browser_probe()
    except Exception as exc:
        report["browser"] = {"status": "BROWSER_PROBE_EXCEPTION", "error": failure_code(exc)}
    report["status"] = determine_outcome(report["portal"], report["control"], report["browser"])
    return report


if __name__ == "__main__":
    result = asyncio.run(run())
    print("BEGIN_GATE1A07_JSON")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("END_GATE1A07_JSON")
    # Reachability of the form is a diagnosis, not a claim of stability.
    if result["status"] not in {"LIVE_DIAGNOSTICS_DISABLED", "SEARCH_FORM_REACHABLE_ONCE"}:
        raise SystemExit(2)
