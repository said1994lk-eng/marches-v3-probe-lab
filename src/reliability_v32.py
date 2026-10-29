"""V3.2 public read-only reliability/coverage probe.

Does not submit DCE forms, solve CAPTCHA, store documents, access a DB, or
publish record content. The official site's transient failures are recorded
rather than interpreted as "zero results" or proven WAF blocking.
"""
import asyncio
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from full_coverage import SEARCH, PAGE_SIZE, NEXT, PREV, official_count, get_cards, change_page, wait_card_count

OUT = Path("artifacts")
OUT.mkdir(exist_ok=True)
MAX_PAGES = max(1, min(20, int(os.environ.get("MAX_PAGES", "20"))))
REPORT = {
    "schema": "marches-v3-source-reliability-v3.2",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "mode": "READ_ONLY_PUBLIC_NO_DCE_NO_SECRETS",
    "runner": "github-actions" if os.getenv("GITHUB_ACTIONS") else "local",
    "commit": os.getenv("GITHUB_SHA", "")[:12] or None,
    "system_state": "NOT_STARTED",
    "preflight_probe": {
        "passed": False, "attempts_used": 0, "http_status": None,
        "last_latency_ms": None, "attempts": [], "circuit_breaker_tripped": False
    },
    "browser": {
        "started": False, "navigation_mode": "official_advanced_search",
        "resource_blocker_enabled": False, "blocked_resource_types": ["image", "font", "media"],
        "resources_blocked": 0
    },
    "filter_attestation": {
        "unfiltered_total_seen": None, "fournitures_selected_confirmed": False,
        "fournitures_still_selected_after_search": None,
        "filtered_official_total": None, "server_filter_effect_independently_proven": False
    },
    "page_size_attestation": {
        "requested_per_page": 100, "actual_rows_on_page_1": 0,
        "hundred_per_page_effective": False, "available_sizes": []
    },
    "coverage_metrics": {
        "max_pages_guard": MAX_PAGES, "pages_traversed": 0,
        "unique_consultations": 0, "duplicates_seen": 0,
        "missing_vs_official": None, "verified_complete": False,
        "pages": []
    },
    "gate4_policy": "SKIPPED_READ_ONLY_MODE",
    "database_writes": 0, "documents_downloaded": 0
}

def preflight():
    """Two bounded simple GETs; absence of response is not proof of WAF block."""
    result = REPORT["preflight_probe"]
    for attempt in range(1, 3):
        started = time.monotonic()
        status = None
        error = None
        try:
            # Do not spoof a browser or follow redirects to non-official hosts.
            req = urllib.request.Request(
                SEARCH,
                method="GET",
                headers={"Accept": "text/html", "Accept-Language": "fr-FR,fr;q=0.9"},
            )
            with urllib.request.urlopen(req, timeout=6) as response:
                status = response.status
                # Headers + tiny body sample confirm a delivered response,
                # not portal search functionality.
                response.read(64)
        except urllib.error.HTTPError as exc:
            status = exc.code
            error = "HTTP_ERROR"
        except Exception as exc:
            error = type(exc).__name__
        latency = round((time.monotonic() - started)*1000)
        result["attempts"].append({
            "attempt": attempt, "status": status,
            "latency_ms": latency, "error_type": error
        })
        result["attempts_used"] = attempt
        result["http_status"] = status
        result["last_latency_ms"] = latency
        if status == 200:
            result["passed"] = True
            break
        if attempt == 1:
            time.sleep(1)
    result["circuit_breaker_tripped"] = not result["passed"]
    return result["passed"]

async def soft_count(page):
    try:
        body = await page.locator("body").inner_text(timeout=5000)
        m = re.search(r"Nombre de résultats\s*:\s*(\d[\d \u00a0]*)", body, re.I)
        return int(re.sub(r"\D", "", m.group(1))) if m else None
    except Exception:
        return None

async def browser_probe():
    health = REPORT["browser"]
    fa = REPORT["filter_attestation"]
    sa = REPORT["page_size_attestation"]
    co = REPORT["coverage_metrics"]
    started = time.monotonic()
    REPORT["stage"] = "browser_start"
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        health["started"] = True
        context = await browser.new_context(locale="fr-FR", accept_downloads=False)
        async def resource_guard(route):
            if route.request.resource_type in ("image", "font", "media"):
                health["resources_blocked"] += 1
                await route.abort()
            else:
                await route.continue_()
        await context.route("**/*", resource_guard)
        health["resource_blocker_enabled"] = True
        page = await context.new_page()
        page.set_default_timeout(18000)
        try:
            REPORT["stage"] = "navigate"
            for attempt in range(1, 3):
                health["navigation_attempts"] = attempt
                try:
                    r = await page.goto(SEARCH, wait_until="commit", timeout=24000)
                    health["search_http_status"] = r.status if r else None
                    if r and r.status == 200:
                        break
                    if attempt == 2:
                        raise ValueError("SEARCH_NOT_200")
                except PlaywrightTimeoutError:
                    if attempt == 2:
                        raise ValueError("BROWSER_NAV_TIMEOUT")
                await page.wait_for_timeout(1000)
            category = page.locator("#ctl0_CONTENU_PAGE_AdvancedSearch_categorie")
            await category.wait_for(state="attached", timeout=22000)
            REPORT["stage"] = "filter"
            fa["unfiltered_total_seen"] = await soft_count(page)
            await category.select_option(label="Fournitures", timeout=12000)
            fa["fournitures_selected_confirmed"] = (
                (await category.locator("option:checked").inner_text()).strip() == "Fournitures"
            )
            if not fa["fournitures_selected_confirmed"]:
                raise ValueError("FOURNITURES_SELECTION_MISMATCH")
            await page.locator("#ctl0_CONTENU_PAGE_AdvancedSearch_lancerRecherche").click(timeout=12000)
            await page.get_by_text(re.compile("Nombre de résultats", re.I)).first.wait_for(
                state="visible", timeout=25000
            )
            filtered = await official_count(page)
            fa["filtered_official_total"] = filtered
            category_post = page.locator("#ctl0_CONTENU_PAGE_AdvancedSearch_categorie")
            if await category_post.count():
                fa["fournitures_still_selected_after_search"] = (
                    (await category_post.locator("option:checked").inner_text()).strip() == "Fournitures"
                )
            if fa["unfiltered_total_seen"] is not None:
                fa["server_filter_effect_independently_proven"] = (
                    filtered < fa["unfiltered_total_seen"]
                )
            # A selected category is a client-side observation; neither a
            # changed count nor a 100-row page is guaranteed.
            if filtered == 0:
                REPORT["system_state"] = "PARTIAL_COVERAGE"
                REPORT["reason_code"] = "ZERO_RESULTS_REQUIRES_SEPARATE_VERIFICATION"
                co["missing_vs_official"] = 0
                return
            REPORT["stage"] = "page_size"
            select = page.locator(PAGE_SIZE)
            if await select.count() == 0:
                raise ValueError("PAGE_SIZE_DROPDOWN_ABSENT")
            sizes = [x.strip() for x in await select.locator("option").all_inner_texts()]
            sa["available_sizes"] = [x for x in sizes if x.isdigit()]
            if "100" not in sizes:
                raise ValueError("PAGE_SIZE_100_UNAVAILABLE")
            await select.select_option(label="100", timeout=12000)
            await page.wait_for_timeout(1000)
            wanted = min(100, filtered)
            count = await page.locator(".tender_item").count()
            if count != wanted:
                # PRADO sometimes applies the new size only after next/back.
                if filtered <= 100:
                    raise ValueError("PAGE_SIZE_100_NOT_APPLIED")
                old = await page.locator(".tender_item a[href*='EntrepriseDetailsConsultation']").first.get_attribute("href")
                REPORT["stage"] = "apply_page_size_next"
                await change_page(page, NEXT, 2, old, retries=1)
                old = await page.locator(".tender_item a[href*='EntrepriseDetailsConsultation']").first.get_attribute("href")
                REPORT["stage"] = "apply_page_size_previous"
                await change_page(page, PREV, 1, old, retries=1)
                await wait_card_count(page, wanted, 35)
            sa["actual_rows_on_page_1"] = await page.locator(".tender_item").count()
            sa["hundred_per_page_effective"] = sa["actual_rows_on_page_1"] == wanted
            if not sa["hundred_per_page_effective"]:
                raise ValueError("PAGE_SIZE_ATTESTATION_FAILED")
            pages_needed = (filtered + 99)//100
            co["expected_pages"] = pages_needed
            if pages_needed > MAX_PAGES:
                raise ValueError("MAX_PAGES_GUARD_INSUFFICIENT")
            seen = set()
            signatures = set()
            for n in range(1, pages_needed+1):
                REPORT["stage"] = f"read_page_{n}"
                expected = min(100, filtered-100*(n-1))
                await wait_card_count(page, expected, 35)
                ids = await get_cards(page)
                current_set = set(ids)
                dupes = len(ids)-len(current_set) + len(current_set & seen)
                if dupes:
                    co["duplicates_seen"] += dupes
                    raise ValueError("DUPLICATE_NOTICE")
                signature = "|".join(sorted(ids))
                if signature in signatures:
                    raise ValueError("REPEATED_PAGE")
                signatures.add(signature)
                seen.update(current_set)
                current_total = await official_count(page)
                if current_total != filtered:
                    raise ValueError("OFFICIAL_TOTAL_CHANGED")
                co["pages"].append({"page":n,"count":len(ids),"cumulative":len(seen)})
                co["pages_traversed"] = n
                co["unique_consultations"] = len(seen)
                co["missing_vs_official"] = max(0, filtered-len(seen))
                if n < pages_needed:
                    previous = await page.locator(".tender_item a[href*='EntrepriseDetailsConsultation']").first.get_attribute("href")
                    REPORT["stage"] = f"paginate_{n+1}"
                    await change_page(page, NEXT, n+1, previous, retries=1)
                    await page.wait_for_timeout(400)
            co["verified_complete"] = (
                co["unique_consultations"] == filtered and
                co["duplicates_seen"] == 0 and co["pages_traversed"] == pages_needed and
                sa["hundred_per_page_effective"] and fa["fournitures_selected_confirmed"]
            )
            REPORT["system_state"] = "VERIFIED_COMPLETE" if co["verified_complete"] else "PARTIAL_COVERAGE"
            REPORT["stage"] = "complete"
        finally:
            health["browser_duration_ms"] = round((time.monotonic()-started)*1000)
            await browser.close()

async def main():
    try:
        REPORT["stage"] = "preflight"
        if not preflight():
            REPORT["system_state"] = "SOURCE_UNAVAILABLE"
            REPORT["reason_code"] = "PREFLIGHT_FAILED_BROWSER_NOT_ATTEMPTED"
            return
        REPORT["system_state"] = "PARTIAL_COVERAGE"
        await browser_probe()
    except Exception as exc:
        kind = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        REPORT["reason_code"] = kind[:90]
        stage = REPORT.get("stage", "unknown")
        REPORT["error_stage"] = stage
        if stage.startswith("filter"):
            REPORT["system_state"] = "FILTER_NOT_APPLIED"
        elif stage in ("navigate", "browser_start"):
            REPORT["system_state"] = "SOURCE_UNAVAILABLE"
        else:
            REPORT["system_state"] = "PARTIAL_COVERAGE"
    finally:
        REPORT["finished_at"] = datetime.now(timezone.utc).isoformat()
        (OUT/"reliability-coverage-report.json").write_text(
            json.dumps(REPORT, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print("BEGIN_RELIABILITY_JSON")
        print(json.dumps(REPORT, indent=2, ensure_ascii=False))
        print("END_RELIABILITY_JSON")
    if REPORT["system_state"] != "VERIFIED_COMPLETE":
        raise SystemExit(2)

if __name__ == "__main__":
    asyncio.run(main())
