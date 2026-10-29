"""Bounded read-only full-coverage Fournitures probe (no DCE forms, no secrets).

Fails closed unless official count equals the number of unique verified notice
detail links obtained through sequential PRADO pages with 100 cards/page.
Only aggregate statistics and non-reversible page fingerprints go to public logs.
"""
import asyncio
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

HOME = "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseHome"
SEARCH = "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&EnCours&searchAnnCons"
OUT = Path("artifacts")
OUT.mkdir(exist_ok=True)
PAGER_INPUT = "#ctl0_CONTENU_PAGE_resultSearch_numPageTop"
PAGE_SIZE = "#ctl0_CONTENU_PAGE_resultSearch_listePageSizeTop"
NEXT = "a#ctl0_CONTENU_PAGE_resultSearch_PagerTop_ctl2"
PREV = "a#ctl0_CONTENU_PAGE_resultSearch_PagerTop_ctl1"

REPORT = {
    "schema": "marches-v3-full-coverage-v1",
    "mode": "PUBLIC_READ_ONLY_FOURNITURES",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "runner": "github-actions" if os.getenv("GITHUB_ACTIONS") else "local",
    "commit_sha": os.getenv("GITHUB_SHA", "")[:12] or None,
    "gate2": {
        "status": "NOT_STARTED",
        "filter": "Fournitures",
        "filter_selected": False,
        "page_size_requested": 100,
        "page_size_verified": False,
        "official_total_at_start": None,
        "official_total_at_end": None,
        "pages_traversed": 0,
        "unique_records": 0,
        "duplicates_detected": 0,
        "missing_count": None,
        "pages": [],
        "full_coverage_verified": False
    },
    "gate4": {"status": "NOT_ATTEMPTED", "reason": "Separate authorized DCE test; no credential handling in public lab"},
    "database_writes": 0,
    "documents_downloaded": 0
}

def safe_link(link):
    u = urlparse(link)
    return u.scheme == "https" and u.hostname == "www.marchespublics.gov.ma" and u.port in (None, 443) and not u.username and not u.password

async def official_count(page):
    content = await page.locator("body").inner_text(timeout=15000)
    m = re.search(r"Nombre de résultats\s*:\s*(\d[\d \u00a0]*)", content, re.I)
    if not m:
        raise ValueError("OFFICIAL_TOTAL_UNREADABLE")
    return int(re.sub(r"\D", "", m.group(1)))

async def get_cards(page):
    raw = await page.evaluate("""() => [...document.querySelectorAll('.tender_item')].map(card => {
        const link = card.querySelector("a[href*='EntrepriseDetailsConsultation']");
        const title = card.querySelector(".p-objet");
        const buyer = [...card.querySelectorAll('strong')].find(x => /Acheteur public/i.test(x.innerText || ''));
        const sidebar = card.querySelector('.leftColumn');
        return {href:link?.getAttribute('href') || '', title:title?.innerText || '',
                buyer:buyer?.parentElement?.innerText || '', sidebar:sidebar?.innerText || ''};
    })""")
    result = []
    for item in raw:
        link = urljoin(page.url, item["href"])
        if not item["href"] or not safe_link(link):
            raise ValueError("UNTRUSTED_OR_MISSING_DETAIL_LINK")
        if not item["title"].strip() or not item["buyer"].strip() or not re.search(r"DATE LIMITE", item["sidebar"], re.I):
            raise ValueError("REQUIRED_CARD_FIELDS_MISSING")
        result.append(hashlib.sha256(link.encode("utf-8")).hexdigest())
    if not result:
        raise ValueError("NO_CARDS_WHEN_OFFICIAL_RESULTS_PRESENT")
    return result

async def change_page(page, selector, target, previous_first, retries=2):
    for attempt in range(retries+1):
        try:
            await page.locator(selector).click(timeout=12000)
            await page.wait_for_function("""args => {
                const p = document.querySelector('#ctl0_CONTENU_PAGE_resultSearch_numPageTop');
                const anchors = [...document.querySelectorAll(".tender_item a[href*='EntrepriseDetailsConsultation']")];
                if (p?.value !== String(args.target) || anchors.length===0 ||
                    anchors[0].getAttribute('href')===args.previous) return false;
                const fingerprint = anchors.length + '|' + anchors.slice(0,6)
                  .map(a => a.getAttribute('href')).join('|');
                const old = window.__fullProbeStable;
                if (!old || old.fingerprint !== fingerprint) {
                    window.__fullProbeStable={fingerprint, at:performance.now()};
                    return false;
                }
                return performance.now()-old.at >= 700;
            }""", arg={"target":target, "previous":previous_first}, timeout=25000)
            return
        except PlaywrightTimeoutError:
            if attempt == retries:
                raise ValueError("PAGINATION_TIMEOUT")
            await page.wait_for_timeout(1600)
    raise ValueError("PAGINATION_UNCONFIRMED")

async def wait_card_count(page, expected, seconds=35):
    await page.wait_for_function(
        "(n) => document.querySelectorAll('.tender_item').length === n",
        arg=expected, timeout=seconds*1000
    )

async def run():
    gate=REPORT["gate2"]
    gate["status"]="FAILED"
    gate["stage"]="startup"
    maximum_pages=max(1,min(25,int(os.getenv("MAX_PAGES","20"))))
    gate["max_pages_guard"]=maximum_pages
    start=time.monotonic()
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(locale="fr-FR", accept_downloads=False)
        page = await context.new_page()
        page.set_default_timeout(20000)
        try:
            gate["stage"]="open_search_direct"
            # Direct public entry reduces the number of portal requests in a fragile
            # GitHub datacenter network. Only a successful real search form counts.
            sr=None
            for attempt in range(1,3):
                gate["search_attempts"]=attempt
                try:
                    sr=await page.goto(SEARCH,wait_until="domcontentloaded",timeout=28000)
                    if sr and sr.status < 400:
                        break
                except PlaywrightTimeoutError:
                    if attempt==2:
                        raise ValueError("DIRECT_SEARCH_TIMEOUT")
                await page.wait_for_timeout(1600)
            gate["navigation_mode"]="direct_official_advanced_search"
            gate["search_http_status"]=sr.status if sr else None
            if not sr or sr.status>=400:
                raise ValueError("DIRECT_SEARCH_HTTP_FAILED")
            category_probe=page.locator("#ctl0_CONTENU_PAGE_AdvancedSearch_categorie")
            await category_probe.wait_for(state="attached",timeout=16000)
            gate["stage"]="filter_fournitures"
            category=page.locator("#ctl0_CONTENU_PAGE_AdvancedSearch_categorie")
            await category.select_option(label="Fournitures")
            gate["filter_selected"]=await category.locator("option:checked").inner_text() == "Fournitures"
            if not gate["filter_selected"]:
                raise ValueError("FOURNITURES_FILTER_NOT_VERIFIED")
            await page.locator("#ctl0_CONTENU_PAGE_AdvancedSearch_lancerRecherche").click()
            await page.get_by_text(re.compile("Nombre de résultats",re.I)).first.wait_for(state="visible",timeout=25000)
            initial_count=await official_count(page)
            gate["official_total_at_start"]=initial_count
            if initial_count == 0:
                gate.update(status="VERIFIED_COMPLETE", missing_count=0, official_total_at_end=0, full_coverage_verified=True)
                return
            gate["stage"]="page_size_100"
            select=page.locator(PAGE_SIZE)
            if not await select.count():
                raise ValueError("PAGE_SIZE_SELECTOR_MISSING")
            choices=await select.locator("option").all_inner_texts()
            gate["page_size_available"] = [x.strip() for x in choices if x.strip().isdigit()]
            if "100" not in [x.strip() for x in choices]:
                raise ValueError("PAGE_SIZE_100_UNAVAILABLE")
            await select.select_option(label="100")
            await page.wait_for_timeout(1200)
            current_cards=await page.locator(".tender_item").count()
            if current_cards != min(100,initial_count):
                # PRADO applies the page size when navigating; inspect both turns.
                if initial_count<=100:
                    raise ValueError("PAGE_SIZE_NOT_APPLIED")
                first=await page.locator(".tender_item a[href*='EntrepriseDetailsConsultation']").first.get_attribute("href")
                gate["stage"]="apply_page_size_next"
                await change_page(page,NEXT,2,first)
                second=await page.locator(".tender_item a[href*='EntrepriseDetailsConsultation']").first.get_attribute("href")
                gate["stage"]="return_to_first_page"
                await change_page(page,PREV,1,second)
                await wait_card_count(page,min(100,initial_count),40)
            gate["page_size_verified"]=True
            seen=set()
            signatures=set()
            pages_needed=(initial_count+99)//100
            gate["expected_pages"]=pages_needed
            if pages_needed>maximum_pages:
                raise ValueError("MAX_PAGES_GUARD_INSUFFICIENT")
            for n in range(1,pages_needed+1):
                gate["stage"]=f"read_page_{n}"
                expected=min(100,initial_count-100*(n-1))
                await wait_card_count(page,expected,40)
                page_links=await get_cards(page)
                if len(page_links)!=expected:
                    raise ValueError("PAGE_CARD_COUNT_MISMATCH")
                if len(set(page_links)) != len(page_links):
                    gate["duplicates_detected"]+=len(page_links)-len(set(page_links))
                    raise ValueError("DUPLICATE_WITHIN_PAGE")
                overlap=len(set(page_links)&seen)
                if overlap:
                    gate["duplicates_detected"]+=overlap
                    raise ValueError("DUPLICATE_ACROSS_PAGES")
                sig=hashlib.sha256("|".join(sorted(page_links)).encode()).hexdigest()[:16]
                if sig in signatures:
                    raise ValueError("REPEATED_PAGE")
                signatures.add(sig)
                seen.update(page_links)
                same_count=await official_count(page)
                if same_count!=initial_count:
                    raise ValueError("OFFICIAL_COUNT_CHANGED_DURING_SCAN")
                gate["pages"].append({"page":n,"count":len(page_links),"cumulative":len(seen),"fingerprint":sig})
                gate["pages_traversed"]=n
                gate["unique_records"]=len(seen)
                gate["missing_count"]=initial_count-len(seen)
                if n<pages_needed:
                    previous=await page.locator(".tender_item a[href*='EntrepriseDetailsConsultation']").first.get_attribute("href")
                    gate["stage"]=f"navigate_to_{n+1}"
                    await change_page(page,NEXT,n+1,previous)
                    await page.wait_for_timeout(350)
            gate["official_total_at_end"]=await official_count(page)
            gate["full_coverage_verified"]=(len(seen)==initial_count and gate["official_total_at_end"]==initial_count and gate["pages_traversed"]==pages_needed and gate["duplicates_detected"]==0)
            gate["status"]="VERIFIED_COMPLETE" if gate["full_coverage_verified"] else "PARTIAL_STOP"
            gate["stage"]="complete"
        except Exception as exc:
            gate["status"]="PARTIAL_STOP" if gate["pages_traversed"] else "FAILED"
            gate["error_code"]=str(exc)[:90] if isinstance(exc,ValueError) else type(exc).__name__
            gate["error_stage"]=gate.get("stage")
            gate["reason"]="Coverage cannot be claimed; inspect source selectors and public run diagnostics"
        finally:
            gate["duration_ms"]=round((time.monotonic()-start)*1000)
            await browser.close()

async def main():
    try:
        await run()
    except Exception as exc:
        REPORT["fatal_error_type"]=type(exc).__name__
        REPORT["gate2"]["status"]="FAILED"
    finally:
        REPORT["finished_at"]=datetime.now(timezone.utc).isoformat()
        (OUT/"full-coverage-report.json").write_text(json.dumps(REPORT,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print("BEGIN_FULL_COVERAGE_JSON")
        print(json.dumps(REPORT,indent=2,ensure_ascii=False))
        print("END_FULL_COVERAGE_JSON")
    if not REPORT["gate2"]["full_coverage_verified"]:
        raise SystemExit(1)

if __name__=="__main__":
    asyncio.run(main())
