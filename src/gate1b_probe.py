"""One bounded Gate 1B public filter test; disabled by default.

This uses the verified Gate 1A commit-first navigator and a single explicit
Fournitures search click. No pagination, DCE, login, database or auth bypass.
It never claims complete category coverage from a small sample.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone

from gate1b_attestation import run_gate_1b
from navigation_recovery import Route, recover_search_form

HOST = "https://www.marchespublics.gov.ma"
ROUTES = (
    Route("official_primary", HOST + "/?page=entreprise.EntrepriseAdvancedSearch&AllCons&searchAnnCons"),
    Route("official_secondary", HOST + "/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&EnCours&searchAnnCons"),
)


async def run() -> dict:
    report = {
        "schema": "marches-gate1b-probe/1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "PUBLIC_READONLY_NO_DCE_NO_DB",
        "status": "LIVE_DISABLED",
        "navigation": None,
        "filter": None,
        "filter_attested": False,
        "filter_attestation_scope": "FIRST_PAGE_SAMPLE_ONLY",
        "coverage_claimed": False,
        "pagination_started": False,
        "database_writes": 0,
        "documents_downloaded": 0,
    }
    if os.getenv("ENABLE_LIVE_GATE1B") != "1":
        return report
    from playwright.async_api import async_playwright
    report["status"] = "STARTED_NOT_VERIFIED"
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                context = await browser.new_context(locale="fr-FR", accept_downloads=False)
                page = await context.new_page()
                nav = await recover_search_form(
                    page, ROUTES, navigation_timeout_ms=17000, settle_wait_ms=800
                )
                report["navigation"] = nav.as_report()
                if not nav.form_ready:
                    report["status"] = "NAVIGATION_NOT_CONFIRMED"
                    return report
                filter_report = await run_gate_1b(page, context)
                report["filter"] = filter_report
                report["status"] = filter_report["status"]
                report["filter_attested"] = report["status"] == "SAMPLED_CONFIRMED"
                return report
            finally:
                await browser.close()
    except Exception as exc:
        report["status"] = "PROBE_EXCEPTION"
        report["exception_class"] = type(exc).__name__[:50]
        return report


if __name__ == "__main__":
    result = asyncio.run(run())
    print("BEGIN_GATE1B_JSON")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("END_GATE1B_JSON")
    if result["status"] not in ("LIVE_DISABLED", "SAMPLED_CONFIRMED"):
        raise SystemExit(2)
