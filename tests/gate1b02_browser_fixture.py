"""Local Chromium fixture for Gate 1B-02 DOM inspection (no network)."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from playwright.async_api import async_playwright
from gate1b02_dom_evidence import CARD_ATTR_JS, DETAIL_STRUCTURE_JS
from category_evidence import CATEGORY_FIELDS_JS


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content('''<html><body>
              <select id="ctl0_CONTENU_PAGE_AdvancedSearch_categorie">
                <option>Toutes</option><option selected="selected">Fournitures</option>
              </select>
              <div class="tender_item">
                <img alt="Fournitures"/>
                <a href="index.php?page=entreprise.EntrepriseDetailsConsultation&amp;refConsultation=5">Voir</a>
                <p class="p-objet">Travaux et fournitures - texte du titre non fiable</p>
              </div>
              </body></html>''')
            cards = await page.evaluate(CARD_ATTR_JS, 5)
            assert cards["cards_observed"] == 1, cards
            assert cards["cards"][0]["attribute_candidate_values"] == ["fournitures"], cards
            assert cards["cards"][0]["attribute_candidate_sources"] == ["alt"], cards
            assert cards["server_echo"]["selected_option_is_fournitures"] is True
            assert cards["cards"][0]["detail_link_route"] == "PLURAL"

            await page.set_content('''<html><body><main><table>
              <tr><th>Catégorie principale</th><td>Fournitures</td></tr>
              </table></main></body></html>''')
            detail = await page.evaluate(CATEGORY_FIELDS_JS, {"scope":"detail","limit":1})
            structure = await page.evaluate(DETAIL_STRUCTURE_JS)
            assert detail["status"] == "EXPLICIT", detail
            assert detail["category"] == "fournitures", detail
            assert structure["explicit_category_label_present"] is True, structure
            print("GATE1B02_CHROMIUM_FIXTURE_PASS")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
