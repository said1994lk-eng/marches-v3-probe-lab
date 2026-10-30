"""Single bounded live check of the actual navigation_recovery module.

OFF unless ENABLE_LIVE_NAVIGATION_CANARY=1. Two official GET routes maximum.
No search submission, DCE, login, category claim, pagination or database.
"""
import asyncio
import json
import os
from datetime import datetime, timezone

from navigation_recovery import Route, recover_search_form

HOST = "https://www.marchespublics.gov.ma"
ROUTES = (
    Route("primary", HOST + "/?page=entreprise.EntrepriseAdvancedSearch&AllCons&searchAnnCons"),
    Route("secondary", HOST + "/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&EnCours&searchAnnCons"),
)


async def run():
    report = {
        "schema": "marches-gate1a07-navigation-canary/1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "PUBLIC_READONLY_NO_DCE_NO_DB",
        "status": "LIVE_DISABLED",
        "navigation": None,
        "form_reachable_once": False,
        "fournitures_filter_confirmed": False,
        "coverage_claimed": False,
        "documents_downloaded": 0,
        "database_writes": 0,
    }
    if os.getenv("ENABLE_LIVE_NAVIGATION_CANARY") != "1":
        return report

    from playwright.async_api import async_playwright
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(locale="fr-FR", accept_downloads=False)
                page = await context.new_page()
                navigation = await recover_search_form(
                    page, ROUTES, navigation_timeout_ms=17000, settle_wait_ms=800
                )
                report["navigation"] = navigation.as_report()
                report["form_reachable_once"] = navigation.form_ready
                report["status"] = (
                    "FORM_READY_CONFIRMED_ONCE" if navigation.form_ready
                    else "NAVIGATION_NOT_CONFIRMED"
                )
            finally:
                await browser.close()
    except Exception as exc:
        report["status"] = "CANARY_EXCEPTION"
        report["exception_class"] = type(exc).__name__
    return report


if __name__ == "__main__":
    result = asyncio.run(run())
    print("BEGIN_GATE1A07_NAV_JSON")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("END_GATE1A07_NAV_JSON")
    if result["status"] not in ("LIVE_DISABLED", "FORM_READY_CONFIRMED_ONCE"):
        raise SystemExit(2)
