"""Read-only official AO/Fournitures and DCE access probe.

No credentials, no CAPTCHA bypass, no registration forms, no persistence, no
production changes. Public GitHub Actions diagnostic artifacts contain only
sanitized status summaries and public-page screenshots on failures.
"""
import asyncio
import hashlib
import json
import os
import re
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.async_api import async_playwright

HOME = "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseHome"
ART = Path("artifacts")
ART.mkdir(exist_ok=True)
RESULT = {
    "schema": "marches-v3-gates-2026-10-28",
    "mode": "READ_ONLY_NO_FORMS",
    "runner": "github-actions" if os.getenv("GITHUB_ACTIONS") else "local",
    "commit": os.getenv("GITHUB_SHA", "")[:12] or None,
    "started_at": datetime.now(timezone.utc).isoformat(),
    "gate1": {"status": "NOT_EXECUTED"},
    "gate4": {"status": "NOT_EXECUTED", "download_verified": False},
    "documents_persisted": 0,
    "database_writes": 0,
}

def allowed(url):
    try:
        u = urlparse(url)
        return u.scheme == "https" and u.hostname == "www.marchespublics.gov.ma" and u.port in (None, 443) and not u.username and not u.password
    except ValueError:
        return False

def err_type(exc):
    if "Timeout" in type(exc).__name__:
        return "TIMEOUT"
    return type(exc).__name__

async def screenshot(page, filename):
    try:
        await page.screenshot(path=str(ART / filename), full_page=False, timeout=7000)
    except Exception:
        pass

def verify_file(filepath):
    size = filepath.stat().st_size
    if not 100 <= size <= 25 * 1024 * 1024:
        raise ValueError("FILE_SIZE_OUTSIDE_SAFE_LIMIT")
    sha = hashlib.sha256()
    with filepath.open("rb") as f:
        head = f.read(512)
        f.seek(0)
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(chunk)
    data = {"bytes": size, "sha256": sha.hexdigest(), "format": "UNKNOWN"}
    if head.lstrip().lower().startswith((b"<!doctype html", b"<html")):
        raise ValueError("HTML_IS_NOT_A_DOCUMENT")
    if head.startswith(b"%PDF-"):
        with filepath.open("rb") as f:
            f.seek(max(0, size - 4096))
            if b"%%EOF" not in f.read():
                raise ValueError("PDF_EOF_MISSING")
        data.update(format="PDF", integrity="BASIC_HEADER_EOF_ONLY")
    elif head.startswith(b"PK\\x03\\x04".replace(b"\\x03", bytes([3])).replace(b"\\x04", bytes([4]))):
        with zipfile.ZipFile(filepath) as z:
            members = z.infolist()
            if not 1 <= len(members) <= 200:
                raise ValueError("ZIP_ENTRY_COUNT_LIMIT")
            total = 0
            names = []
            for m in members:
                name = m.filename
                if name.startswith("/") or "\\\\" in name or ".." in name.split("/") or "\\x00" in name or re.match(r"^[a-zA-Z]:", name):
                    raise ValueError("ZIP_UNSAFE_PATH")
                if m.file_size > 100*1024*1024:
                    raise ValueError("ZIP_SINGLE_FILE_TOO_LARGE")
                if m.file_size > 1024*1024 and m.file_size > max(1, m.compress_size)*100:
                    raise ValueError("ZIP_EXPANSION_RATIO")
                total += m.file_size
                if total > 200*1024*1024:
                    raise ValueError("ZIP_EXPANSION_TOTAL")
                if not m.is_dir():
                    names.append(name[:150])
            if z.testzip() is not None:
                raise ValueError("ZIP_CRC_FAILURE")
        data.update(format="ZIP", integrity="ZIP_CRC_TESTED", entries=len(names), filenames=names[:60])
    else:
        raise ValueError("UNSUPPORTED_FILE_SIGNATURE")
    return data

async def next_page(page, expected, previous):
    next_button = page.locator("a#ctl0_CONTENU_PAGE_resultSearch_PagerTop_ctl2")
    if await next_button.count() == 0:
        raise ValueError("NEXT_PAGE_LINK_MISSING")
    await next_button.click(timeout=15000)
    await page.wait_for_function("""state => {
      const num = document.querySelector('#ctl0_CONTENU_PAGE_resultSearch_numPageTop');
      const links = [...document.querySelectorAll(".tender_item a[href*='EntrepriseDetailsConsultation']")];
      if (num?.value !== String(state.number) || !links.length || links[0].getAttribute('href') === state.previous) return false;
      const sig = links.length + '|' + links.slice(0,6).map(a=>a.getAttribute('href')).join('|');
      let prior = window.__v3Stable;
      if (!prior || prior.sig !== sig) { window.__v3Stable = {sig,at:performance.now()}; return false; }
      return performance.now() - prior.at > 700;
    }""", arg={"number": expected, "previous": previous}, timeout=27000)

async def gate1(page):
    r = {"status": "FAILED", "stage": "home", "http_status": None, "pages": [], "official_total": None, "pagination_verified": False, "full_coverage_verified": False}
    RESULT["gate1"] = r
    try:
        start = time.monotonic()
        response = await page.goto(HOME, wait_until="commit", timeout=45000)
        r["http_status"] = response.status if response else None
        r["response_ms"] = int((time.monotonic() - start)*1000)
        if response is None or response.status >= 400:
            raise ValueError("PORTAL_HTTP_ERROR")
        r["stage"] = "open_search"
        # Prefer the visible official navigation label; old PRADO deployments used #Annoces.
        # A stable public AdvancedSearch route is a fallback, not proof that search worked.
        opened = False
        for menu in [
            page.get_by_text(re.compile("CONSULTATIONS ET ANNONCES", re.I)).first,
            page.locator("#Annoces"),
        ]:
            try:
                if await menu.count() and await menu.is_visible():
                    await menu.click(timeout=6000)
                    opened = True
                    break
            except Exception:
                continue
        r["menu_opened"] = opened
        consult = page.get_by_role("link", name=re.compile("Consultations en cours", re.I))
        if await consult.count() and await consult.first.is_visible():
            await consult.first.click(timeout=12000)
            r["navigation_mode"] = "menu"
        else:
            # URL observed in earlier public portal trials. Use only the official HTTPS host.
            fallback = "https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&EnCours&searchAnnCons"
            response2 = await page.goto(fallback, wait_until="domcontentloaded", timeout=45000)
            r["navigation_mode"] = "official_search_url"
            r["search_http_status"] = response2.status if response2 else None
        r["stage"] = "search_fournitures"
        await page.locator("#ctl0_CONTENU_PAGE_AdvancedSearch_categorie").select_option(label="Fournitures", timeout=15000)
        await page.locator("#ctl0_CONTENU_PAGE_AdvancedSearch_lancerRecherche").click(timeout=15000)
        r["stage"] = "result_count"
        await page.get_by_text(re.compile("Nombre de résultats", re.I)).first.wait_for(state="visible", timeout=25000)
        text = await page.locator("body").inner_text()
        m = re.search(r"Nombre de résultats\\s*:\\s*([0-9 \\u00a0]+)", text, re.I)
        if not m:
            raise ValueError("OFFICIAL_COUNT_UNREADABLE")
        r["official_total"] = int(re.sub(r"\\D", "", m.group(1)))
        if r["official_total"] == 0:
            r.update(status="PASS", full_coverage_verified=True, reason="Official source explicitly shows zero results")
            return []
        all_ids, samples, signatures = set(), [], set()
        for page_number in (1,2):
            r["stage"] = f"parse_page_{page_number}"
            cards = page.locator(".tender_item")
            count = await cards.count()
            if count == 0:
                raise ValueError("RESULT_CARDS_NOT_FOUND")
            current = []
            for i in range(count):
                card = cards.nth(i)
                anchor = card.locator("a[href*='EntrepriseDetailsConsultation']").first
                title_box = card.locator(".p-objet").first
                buyer_box = card.locator("strong").filter(has_text=re.compile("Acheteur public",re.I)).first
                sidebar = card.locator(".leftColumn").first
                if not all([await anchor.count(),await title_box.count(),await buyer_box.count(),await sidebar.count()]):
                    raise ValueError("REQUIRED_CARD_FIELD_MISSING")
                url = urljoin(page.url, await anchor.get_attribute("href") or "")
                if not allowed(url):
                    raise ValueError("UNTRUSTED_DETAIL_LINK")
                title = (await title_box.inner_text()).strip()
                buyer = (await buyer_box.inner_text()).strip()
                side = await sidebar.inner_text()
                if not title or not buyer or "DATE LIMITE" not in side.upper():
                    raise ValueError("INVALID_CARD")
                hid = hashlib.sha256(url.encode()).hexdigest()[:16]
                if hid in all_ids:
                    raise ValueError("REPEATED_NOTICE_IN_PAGINATION")
                all_ids.add(hid)
                current.append({"id":hid, "url":url})
            sig = hashlib.sha256("|".join(sorted(i["id"] for i in current)).encode()).hexdigest()
            if sig in signatures:
                raise ValueError("REPEATED_RESULT_PAGE")
            signatures.add(sig)
            samples.extend(current)
            r["pages"].append({"number":page_number,"cards":len(current),"cumulative":len(samples)})
            if len(samples) == r["official_total"]:
                r["full_coverage_verified"] = True
                break
            if page_number == 1:
                previous = await page.locator(".tender_item a[href*='EntrepriseDetailsConsultation']").first.get_attribute("href")
                r["stage"] = "navigate_page_2"
                await next_page(page,2,previous)
        r["unique_records"] = len(samples)
        r["pagination_verified"] = len(r["pages"]) == 2
        r["status"] = "PASS_SAMPLE" if r["pagination_verified"] else ("PASS" if r["full_coverage_verified"] else "PARTIAL")
        r["reason"] = "Two distinct pages verified; full coverage not claimed" if r["pagination_verified"] else "Only first page verified"
        return samples
    except Exception as exc:
        r.update(status="FAILED",error_type=err_type(exc),reason="Live source access, parsing or pagination failed; not zero results")
        try:
            r["observed_navigation"] = await page.evaluate("""() => ({
              title: document.title.slice(0,100),
              menuLabels:[...document.querySelectorAll('a,button')].map(e=>(e.innerText||'').trim()).filter(x=>/consult|annonce|recherche/i.test(x)).slice(0,12),
              hasCategorySelector:!!document.querySelector('#ctl0_CONTENU_PAGE_AdvancedSearch_categorie')
            })""")
        except Exception:
            pass
        await screenshot(page,"gate1-failure.png")
        return []

async def gate4(context, samples):
    r = {"status":"NOT_TESTED","download_verified":False}
    RESULT["gate4"] = r
    if not samples:
        r.update(status="SKIPPED",reason="No verified listing to inspect")
        return
    page = await context.new_page()
    try:
        r["status"] = "FAILED"
        response = await page.goto(samples[0]["url"],wait_until="domcontentloaded",timeout=45000)
        r["detail_http_status"] = response.status if response else None
        if not response or response.status >= 400:
            raise ValueError("DETAIL_PAGE_HTTP_ERROR")
        captcha = await page.locator('iframe[src*="recaptcha"],iframe[src*="hcaptcha"],.g-recaptcha,.h-captcha,input[name*="captcha"],img[src*="captcha"]').count()
        fields = await page.locator('input,select,textarea').evaluate_all("""els => els.slice(0,60).map(e=>({tag:e.tagName,type:e.type||'',name:String(e.name||'').slice(0,60)}))""")
        r["form_field_types"] = [{"tag":e["tag"],"type":e["type"]} for e in fields]
        r["captcha_markup_detected"] = captcha > 0
        actions = page.get_by_role("link",name=re.compile("DCE|dossier de consultation|Télécharger",re.I))
        r["potential_document_actions"] = min(await actions.count(),20)
        # Portal public detail page can include an intermediary withdrawal form. Never submit it,
        # and never pretend that finding a URL alone demonstrates successful DCE acquisition.
        r["status"] = "ACTION_REQUIRED"
        r["reason"] = "Public detail inspected; authorized DCE withdrawal/form and download remain unverified"
    except Exception as exc:
        r.update(status="FAILED",error_type=err_type(exc),reason="Cannot inspect official DCE detail page")
        await screenshot(page,"gate4-failure.png")
    finally:
        await page.close()

async def main():
    browser = None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(locale="fr-FR",accept_downloads=False)
            page = await context.new_page()
            page.set_default_timeout(20000)
            samples = await gate1(page)
            await gate4(context,samples)
            await browser.close()
    except Exception as exc:
        RESULT["fatal_error_type"] = err_type(exc)
        if RESULT["gate1"]["status"] == "NOT_EXECUTED":
            RESULT["gate1"] = {"status":"FAILED","reason":"Browser failed before connection"}
    finally:
        RESULT["finished_at"] = datetime.now(timezone.utc).isoformat()
        (ART/"probe-report.json").write_text(json.dumps(RESULT,indent=2,ensure_ascii=False)+"\\n",encoding="utf-8")
        print("BEGIN_PROBE_REPORT_JSON")
        print(json.dumps(RESULT,indent=2,ensure_ascii=False))
        print("END_PROBE_REPORT_JSON")
    if RESULT["gate1"]["status"] not in ("PASS","PASS_SAMPLE"):
        raise SystemExit(1)

if __name__ == "__main__":
    asyncio.run(main())
