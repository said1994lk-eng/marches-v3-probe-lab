"""Gate 1A-09: official observed 'Consultations en cours' URL exact canary.

The official public home page links to:
  /index.php?page=entreprise.EntrepriseAdvancedSearch&searchAnnCons=
This differs from previously guessed direct URLs. One official exact GET;
only one preapproved fallback if the genuine public form is not observed.
No filter submission, login, downloads, DCE, scraping, or DB.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone

from navigation_recovery import Route, is_allowed_search_url, recover_search_form

BASE = "https://www.marchespublics.gov.ma"
PUBLIC_MENU_URL = BASE + "/index.php?page=entreprise.EntrepriseAdvancedSearch&searchAnnCons="
SECONDARY = BASE + "/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&EnCours&searchAnnCons"
ROUTES = (
    Route("official_menu_exact", PUBLIC_MENU_URL),
    Route("legacy_secondary", SECONDARY),
)


def blank_report() -> dict:
    return {
        "schema": "marches-v3-gate1a09-exact-public-menu-link/1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "LIVE_DISABLED",
        "mode": "PUBLIC_READONLY_FORM_ONLY",
        "form_reachable": False,
        "public_link_form_reachable": False,
        "navigation": None,
        "filter_attested": False,
        "pagination_started": False,
        "database_writes": 0,
        "dce_downloads": 0,
        "total_public_get_routes_max": 2,
    }


async def run() -> dict:
    result = blank_report()
    if os.getenv("ENABLE_LIVE_GATE1A09") != "1":
        return result
    if not all(is_allowed_search_url(route.url) for route in ROUTES):
        result["status"] = "UNSAFE_CONFIG"
        return result
    from playwright.async_api import async_playwright
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                context = await browser.new_context(locale="fr-FR", accept_downloads=False)
                page = await context.new_page()
                page.set_default_timeout(30000)
                navigation = await recover_search_form(
                    page, ROUTES, navigation_timeout_ms=35000, settle_wait_ms=1200
                )
                result["navigation"] = navigation.as_report()
                result["form_reachable"] = navigation.form_ready
                result["public_link_form_reachable"] = (
                    navigation.form_ready and navigation.route_id == "official_menu_exact"
                )
                result["status"] = (
                    "FORM_READY_CONFIRMED_ONCE" if navigation.form_ready
                    else "FORM_NOT_CONFIRMED"
                )
            finally:
                await browser.close()
    except Exception as exc:
        result["status"] = "BROWSER_EXCEPTION"
        result["error_class"] = type(exc).__name__[:40]
    return result


if __name__ == "__main__":
    report = asyncio.run(run())
    print("BEGIN_GATE1A09_JSON")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("END_GATE1A09_JSON")
    if report["status"] not in ("LIVE_DISABLED", "FORM_READY_CONFIRMED_ONCE"):
        raise SystemExit(2)
