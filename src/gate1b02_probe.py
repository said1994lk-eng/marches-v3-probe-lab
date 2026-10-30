"""Gate 1B-02: one-shot PRADO search + at most ONE public detail GET.

Live-disabled by default. Never claims full-portal category verification, full
coverage, page-size readiness, or permissions not observed in source evidence.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone

from gate1b_attestation import run_gate_1b
from gate1b02_dom_evidence import (
    inspect_card_structure, inspect_one_public_detail, one_detail_link,
    decide_detail_proof,
)
from navigation_recovery import Route, recover_search_form

OFFICIAL = "https://www.marchespublics.gov.ma"
ROUTES = (
    Route("official_primary", OFFICIAL + "/?page=entreprise.EntrepriseAdvancedSearch&AllCons&searchAnnCons"),
    Route("official_secondary", OFFICIAL + "/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&EnCours&searchAnnCons"),
)


def blank_report() -> dict:
    return {
        "schema": "marches-gate1b02/1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "LIVE_DISABLED",
        "scope": "FIRST_PAGE_UP_TO_FIVE_CARDS_ONE_DETAIL_ONLY",
        "navigation": None, "postback": None,
        "card_dom_structure": None, "detail": None,
        "direct_spot_check": None,
        "source_labelled_sample_confirmed": False,
        "all_results_verified": False,
        "differential_proof_claimed": False,
        "pagination_started": False, "page_size_100_verified": False,
        "search_clicks": 0, "detail_get_attempts": 0,
        "database_writes": 0, "documents_downloaded": 0,
    }


async def run() -> dict:
    report = blank_report()
    if os.environ.get("ENABLE_LIVE_GATE1B02") != "1":
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

                # No implicit detail GETs: reusable Gate 1B does its one click
                # and source-labelled card check, not detail navigation.
                post = await run_gate_1b(page, context, max_detail_pages=0)
                report["postback"] = post
                report["search_clicks"] = post["search_clicks"]
                if post["status"] == "CONTRADICTED_SAMPLE":
                    report["status"] = "CONTRADICTED_SAMPLE"
                    return report
                if post["postback_state"] != "APPLIED":
                    report["status"] = "POSTBACK_NOT_ATTESTED"
                    return report

                try:
                    report["card_dom_structure"] = await inspect_card_structure(page)
                except Exception as exc:
                    report["card_dom_structure"] = {
                        "status": "STRUCTURE_INSPECTION_UNAVAILABLE",
                        "error_class": type(exc).__name__[:35],
                    }

                # A first-page card with source-labelled category could satisfy
                # the sample gate independently, but one detail can still be
                # checked for consistency. Never mark all 1,377 records proven.
                report["source_labelled_sample_confirmed"] = (
                    post["status"] == "SAMPLED_CONFIRMED"
                )
                link = await one_detail_link(page)
                if link is not None:
                    report["detail_get_attempts"] = 1
                detail = await inspect_one_public_detail(context, link)
                report["detail"] = detail

                observed = None
                if detail["status"] == "DETAIL_INSPECTED":
                    value = detail.get("detail_field", {})
                    observed = {
                        "status": value.get("status"),
                        "category": value.get("official_category"),
                        "source": value.get("source"),
                    }
                spot = decide_detail_proof(True, observed)
                report["direct_spot_check"] = spot.report()
                if spot.status == "CONTRADICTED_SPOT_CHECK":
                    report["status"] = "CONTRADICTED_SPOT_CHECK"
                elif report["source_labelled_sample_confirmed"]:
                    report["status"] = "SAMPLED_CONFIRMED"
                elif spot.status == "DIRECT_SPOT_CHECK_ONLY":
                    report["status"] = "DIRECT_SPOT_CHECK_ONLY"
                else:
                    report["status"] = "CATEGORY_SOURCE_NOT_FOUND"
                return report
            finally:
                await browser.close()
    except Exception as exc:
        report["status"] = "PROBE_EXCEPTION"
        report["error_class"] = type(exc).__name__[:35]
        return report


def main() -> None:
    result = asyncio.run(run())
    print("BEGIN_GATE1B02_JSON")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("END_GATE1B02_JSON")
    # DIRECT_SPOT_CHECK_ONLY is not proof that all results are Fournitures.
    if result["status"] not in ("LIVE_DISABLED", "SAMPLED_CONFIRMED", "DIRECT_SPOT_CHECK_ONLY"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
