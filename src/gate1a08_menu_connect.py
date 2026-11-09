"""Gate 1A-08 — official home -> Annoces -> Consultations entry canary.

The same public menu route was observed succeeding in the separate
maroc-fournitures-bot repo on 2026-11-09. This is NOT a category or coverage
attestation. Exactly one home GET, up to two public menu clicks, and at most
one direct official advanced-search fallback GET. No form submission.

Sanitized enum/number diagnostics only: no raw URLs, HTML, page titles,
cookies, IDs, PRADO state, screenshots, credentials, or request bodies.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
from typing import Any

from navigation_destination import classify_destination
from page_state import classify_playwright_page

HOST = "www.marchespublics.gov.ma"
HOME = "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseHome"
ADVANCED = "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&EnCours&searchAnnCons"
SEARCH_PAGE = "entreprise.EntrepriseAdvancedSearch"
HOME_PAGE = "entreprise.EntrepriseHome"
ALLOWED_NAVIGATION_PAGES = {HOME_PAGE, SEARCH_PAGE}
NAV_STATES = {"OFFICIAL_HOME_OR_LANDING", "OFFICIAL_ADVANCED_SEARCH_ROUTE"}
BLOCKING_CLASSES = {"UNTRUSTED_DESTINATION", "OFFICIAL_AUTH_WALL",
                    "UNRECOGNIZED_OFFICIAL_PATH", "UNRECOGNIZED_OFFICIAL_QUERY",
                    "UNRECOGNIZED_OFFICIAL_PAGE", "BROWSER_ERROR_DOCUMENT"}
CATEGORY_DOM_JS = r"""() => {
  const select=document.querySelector('#ctl0_CONTENU_PAGE_AdvancedSearch_categorie');
  const options=select ? [...select.options].map(o=>(o.textContent||'').trim().toLowerCase()):[];
  return !!select && options.some(s=>s==='fournitures');
}"""


def official_public_url(url: str, *, navigation: bool = False) -> bool:
    try:
        parsed = urlparse(url)
        if (parsed.scheme != "https" or parsed.hostname != HOST or
            parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.fragment):
            return False
        if not navigation:
            return True
        if parsed.path not in ("/", "/index.php"):
            return False
        params = parse_qs(parsed.query)
        pages = params.get("page")
        return (pages == [SEARCH_PAGE] or pages == [HOME_PAGE] or
                (not params and parsed.path in ("/", "/index.php")))
    except (ValueError, TypeError):
        return False


def failure_reason(exc: Exception) -> str:
    name = type(exc).__name__
    if name in {"TimeoutError", "PlaywrightTimeoutError"}:
        return "TIMEOUT"
    if "Closed" in name:
        return "PAGE_CLOSED"
    return "PLAYWRIGHT_ERROR"


def blank_report() -> dict:
    return {
        "schema": "marches-v3-official-home-navigation-gate1a08/1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "LIVE_DISABLED",
        "mode": "PUBLIC_READONLY_NO_FILTER_NO_DCE_NO_DB",
        "home_navigation": None,
        "menu": {"opened": False, "consultations_clicked": False, "error": None},
        "direct_fallback": None,
        "search_form": {"form_ready": False, "source": None, "reason": None},
        "navigation_responses": [],
        "outbound_blocked_requests": 0,
        "home_get_attempts": 0,
        "direct_get_attempts": 0,
        "search_clicks": 0,
        "details_opened": 0,
        "pagination_started": False,
        "category_confirmed": False,
        "database_writes": 0,
        "downloads": 0,
    }


async def look_for_form(page: Any, *, timeout_ms: int = 22000) -> tuple[bool, str]:
    if not 1000 <= timeout_ms <= 30000:
        raise ValueError("INVALID_WAIT")
    if classify_destination(page.url) != "OFFICIAL_ADVANCED_SEARCH_ROUTE":
        return False, "NOT_ADVANCED_SEARCH_ROUTE"
    try:
        await page.wait_for_function(CATEGORY_DOM_JS, timeout=timeout_ms, polling=250)
    except Exception:
        return False, "CATEGORY_CONTROL_NOT_READY"
    try:
        state = await classify_playwright_page(page, http_status=None)
    except Exception:
        return False, "DOM_CLASSIFICATION_UNAVAILABLE"
    return (state.get("state") == "FORM_READY" and
            state.get("reason_code") == "CATEGORY_CONTROL_PRESENT",
            state.get("reason_code", "UNKNOWN_STATE"))


async def open_home_menu(page: Any, output: dict) -> tuple[bool, bool]:
    """Return (form_ready, allow_fallback); never click a second time."""
    output["home_get_attempts"] = 1
    info = {"http_status": None, "destination_class": "UNKNOWN_DESTINATION",
            "goto": "NOT_STARTED", "elapsed_ms": None}
    output["home_navigation"] = info
    started = time.monotonic()
    try:
        response = await page.goto(HOME, wait_until="commit", timeout=45000)
        info["http_status"] = response.status if response else None
        info["goto"] = "DOCUMENT_COMMITTED"
    except Exception as exc:
        info["goto"] = failure_reason(exc)
    info["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    info["destination_class"] = classify_destination(getattr(page, "url", ""))
    if info["http_status"] in (401,403,429) or (
        info["http_status"] is not None and info["http_status"] >= 400):
        output["status"] = "HOME_HTTP_ERROR"
        return False, False
    if info["destination_class"] in BLOCKING_CLASSES:
        output["status"] = "UNAPPROVED_HOME_DESTINATION"
        return False, False
    if info["goto"] != "DOCUMENT_COMMITTED":
        output["status"] = "HOME_NAVIGATION_NOT_COMMITTED"
        return False, True
    if info["destination_class"] not in NAV_STATES:
        output["status"] = "HOME_NOT_PUBLIC_PORTAL_ROUTE"
        return False, False
    try:
        await page.wait_for_selector("#Annoces", state="visible", timeout=18000)
    except Exception:
        output["menu"]["error"] = "ANNOCES_MENU_NOT_VISIBLE"
        return False, True
    try:
        # Same known public UI as the successful production bot. Never bypass
        # navigation controls, and do not use expect_navigation for PRADO AJAX.
        await page.locator("#Annoces").click(timeout=15000)
        output["menu"]["opened"] = True
    except Exception as exc:
        output["menu"]["error"] = "ANNOCES_MENU_CLICK_" + failure_reason(exc)
        return False, True

    try:
        consultations = page.get_by_role("link", name=re.compile("Consultations en cours", re.I))
        await consultations.click(timeout=23000)
        output["menu"]["consultations_clicked"] = True
    except Exception as exc:
        output["menu"]["error"] = "CONSULTATIONS_CLICK_" + failure_reason(exc)
        # A navigation might have occurred even if the click timed out. Check
        # the current trusted page once without a repeated click.
        if classify_destination(getattr(page, "url", "")) == "OFFICIAL_ADVANCED_SEARCH_ROUTE":
            ready, reason = await look_for_form(page, timeout_ms=9000)
            output["search_form"].update(form_ready=ready, source="home_menu" if ready else None, reason=reason)
            return ready, False if ready else True
        return False, True

    if classify_destination(getattr(page, "url", "")) in BLOCKING_CLASSES:
        output["status"] = "UNAPPROVED_MENU_DESTINATION"
        return False, False
    ready, reason = await look_for_form(page)
    output["search_form"].update(form_ready=ready, source="home_menu" if ready else None, reason=reason)
    if ready:
        output["status"] = "FORM_READY_CONFIRMED_ONCE"
    return ready, not ready


async def run_with_page(page: Any, *, allow_fallback: bool = True) -> dict:
    report = blank_report()
    report["status"] = "RUNNING"
    ready, fallback_safe = await open_home_menu(page, report)
    if ready:
        report["status"] = "FORM_READY_CONFIRMED_ONCE"
        return report
    if not fallback_safe or not allow_fallback:
        if report["status"] == "RUNNING":
            report["status"] = "HOME_FORM_NOT_CONFIRMED"
        return report

    # A single pre-approved direct fallback only when the public menu failed
    # without security or access signals. Never retry the menu or the same GET.
    report["direct_get_attempts"] = 1
    direct = {"goto": "NOT_STARTED", "http_status": None,
              "destination_class": "UNKNOWN_DESTINATION", "elapsed_ms": None}
    report["direct_fallback"] = direct
    started = time.monotonic()
    try:
        response = await page.goto(ADVANCED, wait_until="commit", timeout=35000)
        direct["http_status"] = response.status if response else None
        direct["goto"] = "DOCUMENT_COMMITTED"
    except Exception as exc:
        direct["goto"] = failure_reason(exc)
    direct["elapsed_ms"] = round((time.monotonic() - started)*1000)
    direct["destination_class"] = classify_destination(getattr(page, "url", ""))
    if direct["http_status"] in (401,403,429) or (
        direct["http_status"] is not None and direct["http_status"] >= 400):
        report["status"] = "DIRECT_HTTP_ERROR"
        return report
    if direct["destination_class"] in BLOCKING_CLASSES:
        report["status"] = "UNAPPROVED_DIRECT_DESTINATION"
        return report
    if direct["goto"] != "DOCUMENT_COMMITTED":
        report["status"] = "DIRECT_NAVIGATION_NOT_COMMITTED"
        return report
    ready, reason = await look_for_form(page)
    report["search_form"].update(form_ready=ready, source="direct_fallback" if ready else None, reason=reason)
    report["status"] = "FORM_READY_CONFIRMED_ONCE" if ready else "FORM_NOT_CONFIRMED"
    return report


async def run() -> dict:
    report=blank_report()
    if os.getenv("ENABLE_LIVE_GATE1A08") != "1":
        return report
    from playwright.async_api import async_playwright
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                context = await browser.new_context(locale="fr-FR", accept_downloads=False)
                page = await context.new_page()
                # Keep the public portal's first-party JS/CSS working, but never
                # leave the official HTTPS origin. This mirrors the validated
                # maroc-fournitures-bot browser connection.
                async def only_official(route: Any) -> None:
                    request=route.request
                    if (official_public_url(request.url) and
                        (not request.is_navigation_request() or
                         official_public_url(request.url, navigation=True))):
                        await route.continue_()
                    else:
                        report["outbound_blocked_requests"] += 1
                        await route.abort()
                await context.route("**/*",only_official)
                def on_response(response: Any) -> None:
                    try:
                        if response.request.is_navigation_request() and len(report["navigation_responses"])<6:
                            report["navigation_responses"].append({
                                "http_status":response.status,
                                "destination_class":classify_destination(response.url),
                                "method":response.request.method if response.request.method in ("GET","POST") else "OTHER",
                            })
                    except Exception:
                        pass
                page.on("response",on_response)
                observed=await run_with_page(page)
                observed["navigation_responses"]=report["navigation_responses"]
                observed["outbound_blocked_requests"]=report["outbound_blocked_requests"]
                return observed
            finally:
                await browser.close()
    except Exception as exc:
        report["status"]="BROWSER_EXCEPTION"
        report["error_class"]=type(exc).__name__[:40]
        return report


if __name__ == "__main__":
    result=asyncio.run(run())
    print("BEGIN_GATE1A08_JSON")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print("END_GATE1A08_JSON")
    if result["status"] not in ("LIVE_DISABLED","FORM_READY_CONFIRMED_ONCE"):
        raise SystemExit(2)
