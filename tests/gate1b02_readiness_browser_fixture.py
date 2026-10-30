"""Actual Chromium/DOM readiness assertions against local HTML only."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))

from playwright.async_api import async_playwright
from gate1b02_detail_readiness import wait_detail_readiness, detail_telemetry


async def main():
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        try:
            page=await browser.new_page()
            await page.set_content("""<html><head><title>Detail consultation - marches publics</title></head>
            <body><main id="fixture">
            <h2>Objet: travaux, services et fournitures (not proof)</h2>
            <div>Reference, Date limite, Acheteur public, Procédure</div>
            </main></body></html>""")
            # Simulate a PRADO-style category row arriving AFTER main DOM.
            await page.evaluate("""() => setTimeout(() => {
                const table=document.createElement('table');
                table.innerHTML='<tr><th>Catégorie principale</th><td>Fournitures</td></tr>';
                document.querySelector('#fixture').append(table);
            }, 300)""")
            late=await wait_detail_readiness(page,parse_timeout_ms=3000,label_timeout_ms=1600)
            assert late["status"]=="READY_EXPLICIT_LABEL_VISIBLE",late
            assert late["telemetry"]["category_label_present"] is True,late
            assert late["telemetry"]["dom_html_bytes"]>200,late
            assert late["telemetry"]["ready_state"] in ("interactive","complete"),late
            assert late["telemetry"]["title_class"]=="PUBLIC_TENDER_LIKE",late

            await page.set_content("""<html><head><title>Connexion - private account</title></head>
               <body><h2>Page d'identification</h2>
               <p>Vous devez vous connecter pour continuer sur le site officiel.</p>
               </body></html>""")
            missing=await wait_detail_readiness(page,parse_timeout_ms=1500,label_timeout_ms=350)
            assert missing["status"]=="READY_NO_EXPLICIT_LABEL",missing
            assert missing["telemetry"]["title_class"]=="LOGIN_LIKE",missing

            await page.set_content("""<html><head><title>Just a public page</title></head>
              <body><h2>Fournitures de bureau et travaux</h2>
              <p>Objet du marché: fourniture et pose avec livraison</p>
              </body></html>""")
            misleading=await wait_detail_readiness(page,parse_timeout_ms=1500,label_timeout_ms=350)
            assert misleading["status"]=="READY_NO_EXPLICIT_LABEL",misleading

            print("GATE1B02_READINESS_BROWSER_FIXTURE_PASS")
        finally:
            await browser.close()


if __name__=="__main__":
    asyncio.run(main())
