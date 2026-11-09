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
from urllib.parse import parse_qs, urlparse, urljoin
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
  const search=document.querySelector('#ctl0_CONTENU_PAGE_AdvancedSearch_lancerRecherche');
  const options=select ? [...select.options].map(o=>(o.textContent||'').trim().toLowerCase()):[];
  return !!select && !!search && !search.disabled &&
    options.some(s=>s==='fournitures');
}"""

HOME_READY_JS = r"""() => !!document.body &&
  ['interactive','complete'].includes(document.readyState)"""

SAFE_DOM_JS = r"""() => {
  const text=(document.body?.innerText || '').trim();
  const links=[...document.querySelectorAll('a')].filter(a=>
    /consultations\s+en\s+cours/i.test((a.textContent||'').trim()));
  const isVisible=e=>!!(e.getClientRects().length) &&
    getComputedStyle(e).visibility!=='hidden';
  return {ready_state:document.readyState,
    body_text_bucket:text.length===0?'ZERO':text.length<100?'SHORT':
                     text.length<1000?'MEDIUM':'LONG',
    annonces_present:!!document.querySelector('#Annoces'),
    consultations_links_dom:Math.min(10,links.length),
    consultations_links_visible:Math.min(10,links.filter(isVisible).length),
    category_present:!!document.querySelector('#ctl0_CONTENU_PAGE_AdvancedSearch_categorie'),
    result_cards:Math.min(100,document.querySelectorAll('.tender_item').length)};
}"""


async def safe_dom_summary(page: Any) -> dict:
    try:
        v=await page.evaluate(SAFE_DOM_JS)
    except Exception:
        v={}
    if not isinstance(v,dict):
        v={}
    def number(key):
        x=v.get(key)
        return min(100,max(0,x)) if type(x) is int else 0
    return {
        "ready_state":v.get("ready_state") if v.get("ready_state") in
            {"loading","interactive","complete"} else "UNKNOWN",
        "body_text_bucket":v.get("body_text_bucket") if v.get("body_text_bucket") in
            {"ZERO","SHORT","MEDIUM","LONG"} else "UNKNOWN",
        "annonces_present":v.get("annonces_present") is True,
        "consultations_links_dom":number("consultations_links_dom"),
        "consultations_links_visible":number("consultations_links_visible"),
        "category_present":v.get("category_present") is True,
        "result_cards":number("result_cards"),
    }



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


def trusted_advanced_link(raw: object, base: str) -> str | None:
    """Use the portal's actual public search href without exporting the URL."""
    if not isinstance(raw, str) or not raw or len(raw) > 1800:
        return None
    try:
        url=urljoin(base,raw)
        parsed=urlparse(url)
        if not official_public_url(url, navigation=True):
            return None
        if classify_destination(url) != "OFFICIAL_ADVANCED_SEARCH_ROUTE":
            return None
        qs=parse_qs(parsed.query, keep_blank_values=True)
        forbidden=("download","dce","document","file","auth","token",
                   "action","logout","captcha","redirect","connexion")
        if any(any(x in k.casefold() for x in forbidden) for k in qs):
            return None
        return url
    except (TypeError, ValueError):
        return None


def trusted_public_menu_link(raw: object, base: str) -> str | None:
    """Accept only safe public consultation/search routes from visible menu."""
    if not isinstance(raw,str) or not raw or len(raw)>1800:
        return None
    try:
        url=urljoin(base,raw)
        p=urlparse(url)
        if not official_public_url(url):
            return None
        if p.path not in ("/","/index.php") or p.fragment:
            return None
        params=parse_qs(p.query,keep_blank_values=True)
        pages=params.get("page")
        if not pages or len(pages)!=1:
            return None
        name=pages[0]
        if not re.fullmatch(r"entreprise\.[A-Za-z][A-Za-z0-9_]{2,85}",name):
            return None
        lower=name.casefold()
        if not any(word in lower for word in ("search","recherche","consultation","annonce")):
            return None
        prohibited=("auth","login","connexion","identif","captcha","download",
                    "dce","document","retrait","detail","soumission","logout",
                    "file","token","redirect","action","refconsultation")
        if any(x in lower for x in prohibited):
            return None
        if any(any(x in k.casefold() for x in prohibited) for k in params):
            return None
        return url
    except (ValueError,TypeError):
        return None


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
        "home_dom_ready": False,
        "menu": {"opened": False, "consultations_clicked": False,
                 "consultations_opened_via_link": False,
                 "link_class": None, "error": None,
                 "destination_after_click": None,
                 "after_menu_dom": None},
        "direct_fallback": None,
        "search_form": {"form_ready": False, "source": None, "reason": None,
                        "last_dom": None},
        "navigation_responses": [],
        "outbound_blocked_requests": 0,
        "outbound_blocked_navigations": 0,
        "home_get_attempts": 0,
        "direct_get_attempts": 0,
        "search_clicks": 0,
        "details_opened": 0,
        "pagination_started": False,
        "category_confirmed": False,
        "database_writes": 0,
        "downloads": 0,
    }


async def look_for_form(page: Any, *, timeout_ms: int = 22000,
                        allow_public_menu_route: bool = False) -> tuple[bool, str]:
    if not 1000 <= timeout_ms <= 30000:
        raise ValueError("INVALID_WAIT")
    if classify_destination(page.url) != "OFFICIAL_ADVANCED_SEARCH_ROUTE":
        if not allow_public_menu_route or trusted_public_menu_link(page.url,page.url) is None:
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
    # commit confirms response headers, not a hydrated menu. Require the
    # parser to finish before interacting with PRADO's navigation widget.
    try:
        await page.wait_for_function(HOME_READY_JS, timeout=18000, polling=200)
        output["home_dom_ready"] = True
    except Exception:
        output["menu"]["error"] = "HOME_DOM_NOT_PARSED"
        output["menu"]["after_menu_dom"] = await safe_dom_summary(page)
        return False, True
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
        output["menu"]["after_menu_dom"] = await safe_dom_summary(page)
    except Exception as exc:
        output["menu"]["error"] = "ANNOCES_MENU_CLICK_" + failure_reason(exc)
        return False, True

    try:
        consultations = page.get_by_role("link", name=re.compile("Consultations en cours", re.I))
        # Wait for a real visible link independently of its full-load event.
        await consultations.wait_for(state="visible", timeout=23000)
        raw_href = await consultations.get_attribute("href")
        direct_menu_url = trusted_advanced_link(raw_href, page.url)
        if direct_menu_url is None:
            direct_menu_url = trusted_public_menu_link(raw_href, page.url)
        if direct_menu_url is not None:
            output["menu"]["link_class"] = (
                "OFFICIAL_ADVANCED_SEARCH_HREF"
                if classify_destination(direct_menu_url)=="OFFICIAL_ADVANCED_SEARCH_ROUTE"
                else "OFFICIAL_OTHER_PUBLIC_SEARCH_HREF"
            )
            # Avoid locator.click waiting for the full load event. This is
            # the official menu's own public GET URL, not a guessed endpoint.
            resp = await page.goto(direct_menu_url, wait_until="commit", timeout=35000)
            output["menu"]["consultations_opened_via_link"] = True
            if resp and resp.status >= 400:
                output["status"] = "MENU_LINK_HTTP_ERROR"
                return False, False
        elif not raw_href or raw_href.lstrip().lower().startswith(("javascript:", "#")):
            output["menu"]["link_class"] = "DYNAMIC_MENU_LINK"
            # Trigger the public anchor's DOM click handler without waiting for
            # full page 'load'. Readiness is verified in look_for_form below.
            # This is one click, not a retry or an auth/CAPTCHA workaround.
            await consultations.evaluate("(element) => element.click()")
            output["menu"]["consultations_clicked"] = True
        else:
            output["menu"]["link_class"] = "UNAPPROVED_MENU_HREF"
            output["status"] = "UNAPPROVED_MENU_LINK"
            return False, False
    except Exception as exc:
        output["menu"]["error"] = "CONSULTATIONS_CLICK_" + failure_reason(exc)
        output["menu"]["destination_after_click"] = classify_destination(getattr(page, "url", ""))
        output["menu"]["after_menu_dom"] = await safe_dom_summary(page)
        # A navigation might have occurred even if the click timed out. Check
        # the current trusted page once without a repeated click.
        if classify_destination(getattr(page, "url", "")) == "OFFICIAL_ADVANCED_SEARCH_ROUTE":
            ready, reason = await look_for_form(page, timeout_ms=9000)
            output["search_form"].update(form_ready=ready, source="home_menu" if ready else None, reason=reason)
            return ready, False if ready else True
        return False, True

    output["menu"]["destination_after_click"] = classify_destination(getattr(page, "url", ""))
    if output["menu"]["destination_after_click"] in BLOCKING_CLASSES and (
            trusted_public_menu_link(page.url,page.url) is None):
        output["status"] = "UNAPPROVED_MENU_DESTINATION"
        return False, False
    ready, reason = await look_for_form(page,allow_public_menu_route=True)
    output["search_form"].update(form_ready=ready, source="home_menu" if ready else None, reason=reason)
    if ready:
        output["status"] = "FORM_READY_CONFIRMED_ONCE"
    # If the menu's actual advanced-search URL was already loaded, do not
    # hit the same public endpoint again through a guessed fallback URL.
    return ready, (not ready and not output["menu"]["consultations_opened_via_link"])


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
    if not ready:
        report["search_form"]["last_dom"] = await safe_dom_summary(page)
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
                    # Successful production bot allows every official HTTPS
                    # first-party resource. A legitimate PRADO intermediate
                    # route must not be blocked before the search can render.
                    # Unapproved destination is still rejected after navigation.
                    if official_public_url(request.url):
                        await route.continue_()
                    else:
                        report["outbound_blocked_requests"] += 1
                        if request.is_navigation_request():
                            report["outbound_blocked_navigations"] += 1
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
                observed["outbound_blocked_navigations"]=report["outbound_blocked_navigations"]
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
