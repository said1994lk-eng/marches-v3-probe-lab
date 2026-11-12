"""One bounded public PMMP homepage connectivity canary.

No category search, form clicks, logins, downloads, pagination, raw URLs, HTML,
or cookies in output. This answers whether GitHub-hosted Chromium can load
the official homepage when the legacy advanced-search entry returned HTTP 888.
"""
from __future__ import annotations

import asyncio
import json
import os
from urllib.parse import urlparse

TARGET = "https://www.marchespublics.gov.ma/pmmp/?lang=fr&page=plan"


async def run():
    result = {
        "schema":"marches-v3-pmmp-homepage-connection/1",
        "status":"LIVE_DISABLED",
        "http_status":None,
        "document_committed":False,
        "dom_rendered":False,
        "advanced_search_link_present":False,
        "consultations_link_present":False,
        "request_count":0,
        "search_clicks":0,
        "detail_get_attempts":0,
        "database_writes":0,
        "downloads":0,
    }
    if os.environ.get("ENABLE_ONE_LIVE_PMMP_HOMEPAGE") != "1":
        return result
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        try:
            context=await browser.new_context(locale="fr-FR",accept_downloads=False)
            page=await context.new_page()
            async def public_only(route):
                request=route.request
                u=urlparse(request.url)
                if request.is_navigation_request() and not (
                    u.scheme=="https" and u.hostname=="www.marchespublics.gov.ma"
                    and u.username is None and u.password is None and u.port in (None,443)
                ):
                    await route.abort()
                else:
                    await route.continue_()
            await page.route("**/*", public_only)
            try:
                result["request_count"]=1
                resp=await page.goto(TARGET,wait_until="commit",timeout=18000)
                result["document_committed"]=resp is not None
                result["http_status"]=resp.status if resp else None
            except Exception as exc:
                result["status"]="GOTO_EXCEPTION_"+type(exc).__name__[:35]
                return result
            if result["http_status"]!=200:
                result["status"]="HOMEPAGE_HTTP_NON_200"
                return result
            try:
                await page.wait_for_function("""() => !!document.body &&
                    document.readyState !== 'loading' &&
                    (document.body.innerText||'').trim().length > 40
                """,timeout=9000)
                result["dom_rendered"]=True
            except Exception:
                result["status"]="HOMEPAGE_DOM_NOT_READY"
                return result
            flags=await page.evaluate("""() => {
                const links=[...document.querySelectorAll('a[href]')];
                return {
                    advanced:links.some(a => /recherche avancee|recherche avancée/i.test(a.textContent||'') ||
                        /EntrepriseAdvancedSearch/.test(a.getAttribute('href')||'')),
                    consultations:links.some(a => /consultations en cours/i.test(a.textContent||''))
                };
            }""")
            result["advanced_search_link_present"]=flags.get("advanced") is True
            result["consultations_link_present"]=flags.get("consultations") is True
            result["status"]="PMMP_PUBLIC_HOMEPAGE_REACHABLE"
            return result
        finally:
            await browser.close()


if __name__=="__main__":
    report=asyncio.run(run())
    print("BEGIN_PMMP_HOME_JSON")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    print("END_PMMP_HOME_JSON")
    if report["status"] not in ("LIVE_DISABLED","PMMP_PUBLIC_HOMEPAGE_REACHABLE"):
        raise SystemExit(2)
