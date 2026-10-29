"""Optional bounded Gate 1A-02 live probe: OFF unless explicitly enabled.

This script NEVER downloads DCE or connects to a database. No GitHub workflow
invokes it. Use only with a separate decision to perform a bounded live check.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone

from navigation_recovery import Route, recover_search_form
from filter_attestation import select_fournitures_and_observe

OFFICIAL = "https://www.marchespublics.gov.ma"
ROUTES = (
    Route("official_primary", OFFICIAL + "/?page=entreprise.EntrepriseAdvancedSearch&AllCons&searchAnnCons"),
    Route("official_secondary", OFFICIAL + "/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&EnCours&searchAnnCons"),
)


def report_skeleton() -> dict:
    return {
        "schema": "marches-gate1a02/1",
        "mode": "READ_ONLY_PUBLIC_NO_DCE_NO_DB_NO_SECRETS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "LIVE_TEST_DISABLED",
        "navigation": None,
        "filter_attestation": None,
        "database_writes": 0,
        "documents_downloaded": 0,
        "pagination_started": False,
        "coverage_claimed": False,
    }


async def run() -> dict:
    report = report_skeleton()
    if os.getenv("ENABLE_LIVE_GATE1A02") != "1":
        return report
    from playwright.async_api import async_playwright  # loaded only with explicit opt-in
    report["status"] = "STARTED_NOT_VERIFIED"
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                context = await browser.new_context(locale="fr-FR", accept_downloads=False)
                page = await context.new_page()
                nav = await recover_search_form(page, ROUTES)
                report["navigation"] = nav.as_report()
                if not nav.form_ready:
                    report["status"] = nav.reason_code
                    return report
                # Selecting the category is not independent evidence. This
                # returns UNCONFIRMED until a vetted result-category extractor
                # is separately integrated and tested on a public DOM fixture.
                proof = await select_fournitures_and_observe(page)
                report["filter_attestation"] = proof
                report["status"] = "FILTER_CONFIRMED" if proof["effect_confirmed"] else "FILTER_EFFECT_UNCONFIRMED"
                return report
            finally:
                await browser.close()
    except Exception as exc:
        report["status"] = "PROBE_EXCEPTION"
        report["error_type"] = type(exc).__name__
        return report


def main() -> None:
    report = asyncio.run(run())
    print("BEGIN_GATE1A02_JSON")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("END_GATE1A02_JSON")
    if report["status"] not in ("LIVE_TEST_DISABLED", "FILTER_CONFIRMED"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
