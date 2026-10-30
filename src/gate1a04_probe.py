"""One bounded, opt-in public evidence probe (Gate 1A-04).

No pagination, database, DCE download, login, proxy or captcha bypass. Two
known search routes and at most five public detail pages. A sample cannot prove
full-portal coverage; this program never returns VERIFIED_COMPLETE.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from navigation_recovery import Route, recover_search_form
from category_evidence import (aggregate_samples, inspect_public_cards,
                               inspect_few_details, sampled_detail_links)
from filter_evidence_gate1a04 import evaluate_gate

OFFICIAL = 'https://www.marchespublics.gov.ma'
ROUTES = (
    Route('official_primary', OFFICIAL + '/?page=entreprise.EntrepriseAdvancedSearch&AllCons&searchAnnCons'),
    Route('official_secondary', OFFICIAL + '/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons&EnCours&searchAnnCons'),
)


def new_report() -> dict:
    return {
        'schema': 'marches-gate1a04/1',
        'mode': 'READ_ONLY_PUBLIC_NO_DB_NO_DCE',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'status': 'LIVE_DISABLED',
        'navigation': None,
        'search_evidence': None,
        'category_sample': None,
        'filter_decision': None,
        'db_writes': 0,
        'downloads': 0,
        'pagination_started': False,
        'coverage_claimed': False,
    }


async def _public_result_metadata(page):
    """Only aggregate result counts and a transient fingerprint, no raw titles."""
    return await page.evaluate(r"""() => {
      const text = document.body?.innerText || '';
      const match = /Nombre de r[eé]sultats\s*:\s*([\d\s\u00a0]+)/i.exec(text);
      const official = match ? Number(match[1].replace(/\D/g,'')) : null;
      // Only used in transient comparison, never published.
      const links = [...document.querySelectorAll('.tender_item a[href*="EntrepriseDetailsConsultation"]')];
      return {total: official, cards: document.querySelectorAll('.tender_item').length,
              first_href: links.length ? (links[0].getAttribute('href') || '') : ''};
    }""")


async def run() -> dict:
    report = new_report()
    if os.getenv('ENABLE_LIVE_GATE1A04') != '1':
        return report
    from playwright.async_api import async_playwright
    report['status'] = 'STARTED_NOT_VERIFIED'
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                context = await browser.new_context(locale='fr-FR', accept_downloads=False)
                page = await context.new_page()
                nav = await recover_search_form(page, ROUTES, navigation_timeout_ms=22000,
                                                settle_wait_ms=800)
                report['navigation'] = nav.as_report()
                if not nav.form_ready:
                    report['status'] = 'NAVIGATION_NOT_CONFIRMED'
                    return report

                category = page.locator('#ctl0_CONTENU_PAGE_AdvancedSearch_categorie')
                if await category.count() != 1:
                    report['status'] = 'CATEGORY_CONTROL_NOT_UNIQUE'
                    return report
                before = await _public_result_metadata(page)
                await category.select_option(label='Fournitures', timeout=12000)
                selected = (await category.locator('option:checked').inner_text()).strip().casefold() == 'fournitures'
                if not selected:
                    report['status'] = 'CATEGORY_SELECTION_FAILED'
                    return report

                # Collect evidence of a same-host POST response only after the
                # search is explicitly submitted. Do not count unrelated assets.
                responses = []
                def on_response(response):
                    try:
                        host = urlparse(response.url).hostname
                        if host == 'www.marchespublics.gov.ma' and response.request.method == 'POST' and response.status < 400:
                            responses.append(True)
                    except Exception:
                        pass
                page.on('response', on_response)
                try:
                    await page.locator('#ctl0_CONTENU_PAGE_AdvancedSearch_lancerRecherche').click(timeout=16000)
                    await page.locator('text=/Nombre de résultats/i').first.wait_for(state='visible', timeout=20000)
                    await page.wait_for_timeout(500)
                finally:
                    page.remove_listener('response', on_response)

                after = await _public_result_metadata(page)
                retained = None
                if await category.count() == 1:
                    retained = (await category.locator('option:checked').inner_text()).strip().casefold() == 'fournitures'
                changed = (after['first_href'] != before['first_href'] or
                           (before['cards']==0 and after['cards']>0) or
                           (before['total'] is not None and after['total'] != before['total']))
                report['search_evidence'] = {
                    'selected': selected,
                    'retained_after_search': retained,
                    'post_response_seen': bool(responses),
                    'result_transition_seen': bool(changed),
                    'official_total': after['total'],
                    'cards_after': after['cards'],
                }
                cards = await inspect_public_cards(page, max_cards=5)
                # Details are only sampled when cards lack explicit fields.
                missing_positions = [i for i, row in enumerate(cards) if row.get('status') != 'EXPLICIT']
                details = []
                if missing_positions and after['cards']:
                    links = await sampled_detail_links(page, max_links=5)
                    selected_links = [links[i] if i < len(links) else None for i in missing_positions]
                    details = await inspect_few_details(context, selected_links, limit=5, timeout_ms=11000)
                sample = aggregate_samples(cards, details)
                report['category_sample'] = sample.report()
                decision = evaluate_gate(selected=selected, retained=retained,
                                         search_response_seen=bool(responses),
                                         result_transition_seen=bool(changed),
                                         official_total=after['total'], sample=sample)
                report['filter_decision'] = decision.report()
                report['status'] = decision.status
                return report
            finally:
                await browser.close()
    except Exception as exc:
        report['status'] = 'PROBE_EXCEPTION'
        report['exception_class'] = type(exc).__name__
        return report


def main():
    report = asyncio.run(run())
    print('BEGIN_GATE1A04_JSON')
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print('END_GATE1A04_JSON')
    if report['status'] not in ('LIVE_DISABLED', 'SAMPLED_CONFIRMED'):
        raise SystemExit(2)


if __name__ == '__main__':
    main()