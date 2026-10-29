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
        "status": "SKIPPED_BROWSER_FIRST",
        "reason": "curl 403 does not determine Chromium reachability"
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

async def safe_dom_snapshot(page):
    """Public control metadata only: no cookies, hidden-field data or typed values."""
    return await page.evaluate("""() => {
      const u = new URL(location.href);
      return {
        page_query_parameter: u.searchParams.get('page'),
        pathname: u.pathname,
        ready_state: document.readyState,
        has_result_count_label: /Nombre de résultats/i.test(document.body?.innerText || ''),
        tender_cards: document.querySelectorAll('.tender_item').length,
        body_text_length: (document.body?.innerText || '').length,
        body_html_length: (document.body?.innerHTML || '').length,
        script_count: document.querySelectorAll('script').length,
        form_count: document.querySelectorAll('form').length,
        category_control_found: !!document.querySelector('#ctl0_CONTENU_PAGE_AdvancedSearch_categorie'),
        select_controls: [...document.querySelectorAll('select')].slice(0,20).map(s => ({
          id: s.id.slice(0,120),
          name: (s.getAttribute('name') || '').slice(0,120),
          options_count: s.options.length,
          sample_options: [...s.options].slice(0,6).map(o => ({
            value: String(o.value).slice(0,60),
            text: (o.textContent || '').trim().slice(0,80)
          }))
        }))
      };
    }""")

async def soft_count(page):
    try:
        body = await page.locator("body").inner_text(timeout=5000)
        m = re.search(r"Nombre de résultats\s*:\s*(\d[\d \u00a0]*)", body, re.I)
        return int(re.sub(r"\D", "", m.group(1))) if m else None
    except Exception:
        return None

async def pager_state(page, previous_first):
    """Only non-sensitive pager metadata; URLs are never placed in public reports."""
    return await page.evaluate("""prev => {
        const marker = document.querySelector('#ctl0_CONTENU_PAGE_resultSearch_numPageTop');
        const cards = [...document.querySelectorAll(".tender_item")];
        const anchors = cards.map(c => c.querySelector("a[href*='EntrepriseDetailsConsultation']")).filter(Boolean);
        const next = document.querySelector('a#ctl0_CONTENU_PAGE_resultSearch_PagerTop_ctl2');
        const href = anchors[0]?.getAttribute("href") || "";
        return {
            marker: (marker?.value || "").slice(0,12),
            rows: cards.length,
            links: anchors.length,
            all_detail_anchors: document.querySelectorAll(".tender_item a[href*='EntrepriseDetailsConsultation']").length,
            first_changed: href !== "" && href !== prev,
            next_exists: !!next,
            next_disabled: !!(next?.hasAttribute("disabled") || next?.getAttribute("aria-disabled")==="true"),
            ready_state: document.readyState
        };
    }""", previous_first)


async def advance_page_verified(page, target, expected_rows, report, inflight):
    """One click + DOM transition. Retry only if old page and no AJAX is active.

    PRADO callbacks can arrive late: never blind double-click, and never treat
    a row count alone as proof that the requested target page loaded.
    """
    previous = await page.locator(
        ".tender_item a[href*='EntrepriseDetailsConsultation']"
    ).first.get_attribute("href")
    if not previous:
        raise ValueError("PAGER_PREVIOUS_ANCHOR_MISSING")
    old_state = await pager_state(page, previous)
    diagnostic = {
        "target_page": target,
        "previous_marker": old_state["marker"],
        "attempts": 0,
        "pending_request_counts": [],
        "final_state": None
    }
    report.setdefault("pagination_diagnostics", []).append(diagnostic)
    if old_state["marker"] and old_state["marker"] != str(target-1):
        diagnostic["error_code"] = "SOURCE_PAGER_MARKER_MISMATCH"
        raise ValueError("SOURCE_PAGER_MARKER_MISMATCH")

    async def observe_transition(timeout):
        await page.wait_for_function("""args => {
            const marker = document.querySelector('#ctl0_CONTENU_PAGE_resultSearch_numPageTop');
            const cards = [...document.querySelectorAll(".tender_item")];
            const links = cards.map(c => c.querySelector("a[href*='EntrepriseDetailsConsultation']")).filter(Boolean);
            const n = cards.length;
            const first = links[0]?.getAttribute('href') || '';
            const last = links[links.length-1]?.getAttribute('href') || '';
            const mark = marker?.value || '';
            const valid = first && first !== args.previous && n === args.expected &&
                          links.length === args.expected &&
                          (!mark || mark === String(args.target));
            if (!valid) { window.__v33PagerStable = null; return false; }
            const fingerprint = String(n) + '|' + first + '|' + last + '|' + mark;
            const p = window.__v33PagerStable;
            if (!p || p.fingerprint !== fingerprint) {
                window.__v33PagerStable = {fingerprint, since: performance.now()};
                return false;
            }
            return performance.now() - p.since >= 900;
        }""", arg={"previous":previous,"expected":expected_rows,"target":target},
        timeout=timeout, polling=250)

    for attempt in (1, 2):
        diagnostic["attempts"] = attempt
        current = await pager_state(page, previous)
        diagnostic["pre_click_state"] = current
        # The previous click may have completed while the await timed out.
        if current["first_changed"] and current["marker"] == str(target) and current["rows"] == expected_rows:
            await observe_transition(6000)
            diagnostic["final_state"] = await pager_state(page, previous)
            diagnostic["outcome"] = "LATE_RESPONSE_ACCEPTED"
            return
        if attempt == 2:
            # A second click is allowed only if the old page is provably still
            # active and the request tracker has no outstanding document/XHR.
            await page.wait_for_timeout(2500)
            current = await pager_state(page, previous)
            diagnostic["pending_request_counts"].append(len(inflight))
            diagnostic["state_before_retry"] = current
            if (current["first_changed"] or
                current["marker"] != str(target-1) or
                len(inflight) != 0 or current["next_disabled"] or not current["next_exists"]):
                diagnostic["error_code"] = "UNSAFE_TO_RECLICK"
                diagnostic["final_state"] = current
                raise ValueError("PAGINATION_UNCONFIRMED_NO_BLIND_RECLICK")
        try:
            # no_wait_after avoids waiting for a page navigation after the click;
            # PRADO might use AJAX without any new DOMContentLoaded event.
            await page.locator(NEXT).click(timeout=14000, no_wait_after=True)
        except PlaywrightTimeoutError:
            diagnostic["click_timeout_at_attempt"] = attempt
        try:
            await observe_transition(19000 if attempt == 1 else 22000)
            diagnostic["final_state"] = await pager_state(page, previous)
            diagnostic["outcome"] = "CONFIRMED"
            return
        except PlaywrightTimeoutError:
            diagnostic["post_wait_state"] = await pager_state(page, previous)
            diagnostic["pending_request_counts"].append(len(inflight))
            if attempt == 2:
                diagnostic["error_code"] = "PAGER_STABLE_TRANSITION_TIMEOUT"
                diagnostic["final_state"] = diagnostic["post_wait_state"]
                raise ValueError("PAGINATION_TIMEOUT")
    raise ValueError("PAGINATION_UNCONFIRMED")


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
        # Track only whether browser navigation / PRADO AJAX is still in-flight,
        # not request paths, URLs, cookies or content.
        inflight = set()
        def on_request(req):
            if req.resource_type in ("xhr", "fetch", "document"):
                inflight.add(req)
        def on_done(req):
            inflight.discard(req)
        page.on("request", on_request)
        page.on("requestfinished", on_done)
        page.on("requestfailed", on_done)
        try:
            REPORT["stage"] = "navigate"
            # The URL /?page=EntrepriseAdvancedSearch legitimately has pathname "/".
            # Check its query and the DOM; never treat pathname "/" alone as a redirect.
            route_urls = [
                SEARCH,
                "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&EnCours&searchAnnCons",
            ]
            category = page.locator("#ctl0_CONTENU_PAGE_AdvancedSearch_categorie")
            for navigation_index, target_url in enumerate(route_urls, start=1):
                health["navigation_attempts"] = navigation_index
                health["navigation_mode"] = "user_supplied_url" if navigation_index == 1 else "previously_successful_official_url"
                try:
                    r = await page.goto(target_url, wait_until="domcontentloaded", timeout=28000)
                    health["search_http_status"] = r.status if r else None
                    if not r or r.status != 200:
                        raise ValueError("SEARCH_HTTP_NOT_200")
                except PlaywrightTimeoutError:
                    health["navigation_timeout_" + str(navigation_index)] = True
                    # Inspect only public DOM structure; incomplete loading is not
                    # considered a redirect, nor is an empty select list conclusive.
                    try:
                        health["dom_after_navigation_" + str(navigation_index)] = await safe_dom_snapshot(page)
                    except Exception:
                        health["dom_after_navigation_" + str(navigation_index)] = {"status":"UNREADABLE"}
                    if navigation_index == len(route_urls):
                        raise ValueError("BOTH_OFFICIAL_ROUTES_DOMCONTENTLOADED_TIMEOUT")
                    await page.wait_for_timeout(1500)
                    continue
                # PRADO controls may render asynchronously after DOMContentLoaded.
                # A timeout means "not observed", never "no results" or "WAF proven".
                try:
                    await page.wait_for_function("""() =>
                      !!document.querySelector('#ctl0_CONTENU_PAGE_AdvancedSearch_categorie')
                      || !!document.querySelector('.tender_item')
                      || /Nombre de résultats/i.test(document.body?.innerText || '')
                    """, timeout=12000)
                    health["public_content_ready_" + str(navigation_index)] = True
                except PlaywrightTimeoutError:
                    health["public_content_ready_" + str(navigation_index)] = False
                # Avoid recording complete URLs, cookies, form field values or HTML.
                health["dom_after_navigation_" + str(navigation_index)] = await safe_dom_snapshot(page)
                if await category.count():
                    break
                # Some routes land directly on a results view, without a filter form.
                # Keep evidence and try the older official route once, not indefinitely.
                health["category_missing_after_navigation_" + str(navigation_index)] = True
            REPORT["stage"] = "await_search_form"
            if not await category.count():
                raise ValueError("CATEGORY_SELECTOR_ABSENT_AFTER_BOTH_OFFICIAL_ROUTES")
            await category.wait_for(state="attached", timeout=10000)
            health["select_diagnostics_before_filter"] = await safe_dom_snapshot(page)
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
                    await advance_page_verified(
                        page, n+1, min(100, filtered-100*n), co, inflight
                    )
                    await page.wait_for_timeout(500)
            co["verified_complete"] = (
                co["unique_consultations"] == filtered and
                co["duplicates_seen"] == 0 and co["pages_traversed"] == pages_needed and
                sa["hundred_per_page_effective"] and fa["fournitures_selected_confirmed"]
            )
            REPORT["system_state"] = "VERIFIED_COMPLETE" if co["verified_complete"] else "PARTIAL_COVERAGE"
            REPORT["stage"] = "complete"
        finally:
            # Compact public DOM evidence, no form values, cookies, URLs or secrets.
            try:
                health["dom_diagnostics"] = await asyncio.wait_for(safe_dom_snapshot(page), timeout=5)
            except Exception:
                health["dom_diagnostics"] = {"status":"UNAVAILABLE"}
            health["browser_duration_ms"] = round((time.monotonic()-started)*1000)
            await browser.close()

async def main():
    try:
        REPORT["stage"] = "browser_first"
        REPORT["system_state"] = "PARTIAL_COVERAGE"
        await browser_probe()
    except Exception as exc:
        kind = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        REPORT["reason_code"] = kind[:90]
        stage = REPORT.get("stage", "unknown")
        REPORT["error_stage"] = stage
        if stage.startswith("filter"):
            REPORT["system_state"] = "FILTER_NOT_APPLIED"
        elif stage in ("navigate", "browser_start", "browser_first"):
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
# Read-only V3.2 single-run verification marker (2026-10-29; no logic changes).
