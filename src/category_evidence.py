"""Gate 1A-04: bounded public result/detail category evidence discovery.

Only explicit, associated category fields count; keywords inside tender titles do
NOT count. No page text, document URLs, HTML or credentials leave the browser in
logs. Every public detail URL is allowlisted and held transiently in memory.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence
from urllib.parse import urljoin, urlparse, parse_qs

from filter_attestation import normalized_category

PORTAL_HOST = "www.marchespublics.gov.ma"
PAGE_KEY = "entreprise.EntrepriseDetailsConsultation"

# Playwright evaluate: works in the DOM of an actual browser, and can be
# regression-tested on local HTML (fixtures). Do not return arbitrary text.
CATEGORY_FIELDS_JS = r"""({scope, limit}) => {
  function clean(s) { return (s || '').replace(/\s+/g, ' ').trim(); }
  function fold(s) { return clean(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase(); }
  function known(s) {
    const val = fold(s).replace(/[.\s:;\-]+$/, '');
    return ['fournitures', 'travaux', 'services'].includes(val) ? val : null;
  }
  function label(s) {
    return /^(categorie(?: principale| du marche)?|nature du marche|nature des prestations|type de prestation|type de marche)\s*[:\-]?$/i.test(fold(s));
  }
  function inspect(root) {
    if (!root) return {status:'MISSING', category:null, source:null, field_pairs:0};
    const evidence = [];
    const nodes = [root, ...root.querySelectorAll('[data-category],dt,th,label,strong,b,span,p,div,li,td,dd')];
    let pairs = 0;
    for (const el of nodes.slice(0, 700)) {
      if (el.hasAttribute && el.hasAttribute('data-category')) {
        const value = known(el.getAttribute('data-category'));
        if (value) evidence.push({value, method:'explicit_data_attribute'});
      }
      const raw = clean(el.textContent);
      // Avoid extracting the whole card or a nested container by accident.
      if (raw.length > 110) continue;
      const inline = /^\s*(categorie(?: principale| du marche)?|nature du marche|nature des prestations|type de prestation|type de marche)\s*[:\-]\s*(fournitures|travaux|services)\s*$/i.exec(fold(raw));
      if (inline && el.children.length === 0) {
        evidence.push({value:inline[2].toLowerCase(), method:'explicit_inline_label'});
        pairs++;
        continue;
      }
      if (!label(raw)) continue;
      pairs++;
      // Labels must have a dedicated adjacent value, not an arbitrary word
      // elsewhere on the page. A column of labels and a separate column of
      // unrelated data is NOT treated as proof.
      const adjacent = el.nextElementSibling;
      if (adjacent) {
        const candidate = known(adjacent.textContent);
        if (candidate && clean(adjacent.textContent).length <= 36)
          evidence.push({value:candidate, method:'explicit_label_pair'});
      }
      if (el.parentElement && el.parentElement.children.length === 2) {
        const sibling = [...el.parentElement.children].find(x => x !== el);
        if (sibling) {
          const candidate = known(sibling.textContent);
          if (candidate && clean(sibling.textContent).length <= 36)
            evidence.push({value:candidate, method:'explicit_label_pair'});
        }
      }
    }
    const values = [...new Set(evidence.map(x => x.value))];
    if (values.length !== 1) {
      return {status:values.length ? 'AMBIGUOUS' : 'MISSING', category:null, source:null,
              field_pairs: Math.min(pairs, 15)};
    }
    const source = evidence.some(x=>x.method === 'explicit_label_pair') ? 'explicit_label_pair'
      : evidence.some(x=>x.method === 'explicit_inline_label') ? 'explicit_inline_label'
      : 'explicit_data_attribute';
    return {status:'EXPLICIT', category:values[0], source, field_pairs:Math.min(pairs,15)};
  }
  if (scope === 'cards') {
    return [...document.querySelectorAll('.tender_item')].slice(0, limit).map(inspect);
  }
  if (scope === 'detail') {
    // Avoid page-wide navigation filters, which are NOT a source of evidence.
    const detail = document.querySelector('#ctl0_CONTENU_PAGE') || document.querySelector('main');
    return inspect(detail);
  }
  return null;
}"""


def safe_detail_url(raw: str, base_url: str) -> str | None:
    """Allow only the public detail route on the exact portal hostname."""
    if not isinstance(raw, str) or not raw.strip() or len(raw) > 1600:
        return None
    try:
        url = urljoin(base_url, raw)
        parsed = urlparse(url)
        if (parsed.scheme != 'https' or parsed.hostname != PORTAL_HOST or
                parsed.username or parsed.password or parsed.port not in (None,443) or
                parsed.path not in ('/', '/index.php') or parsed.fragment):
            return None
        params = parse_qs(parsed.query, keep_blank_values=True)
        if params.get('page') != [PAGE_KEY] or len(params) > 7:
            return None
        # Refuse action/download-like query controls even on the correct host.
        if any(any(word in key.lower() for word in ('download', 'dce', 'file', 'document',
                                                   'archive', 'attachment', 'auth', 'token',
                                                   'action', 'captcha')) for key in params):
            return None
        return url
    except (TypeError, ValueError):
        return None


def recognized_record(row: Mapping[str, Any]) -> tuple[str | None, str]:
    """Return a known category only from explicit associated field evidence."""
    if not isinstance(row, Mapping) or row.get('status') != 'EXPLICIT':
        return None, 'NO_EXPLICIT_FIELD'
    value = normalized_category(row.get('category'))
    if value not in {'fournitures', 'travaux', 'services'}:
        return None, 'UNRECOGNIZED_CATEGORY'
    if row.get('source') not in {'explicit_label_pair', 'explicit_inline_label', 'explicit_data_attribute'}:
        return None, 'UNTRUSTED_FIELD_SOURCE'
    return value, 'SOURCE_LABELLED'


@dataclass(frozen=True)
class CategorySample:
    cards_observed: int
    cards_with_category: int
    cards_ambiguous: int
    details_checked: int
    details_with_category: int
    details_ambiguous: int
    matching: int
    mismatching: int
    missing: int
    sample_categories: tuple[str | None, ...]
    evidence_source: str

    def report(self) -> dict[str, Any]:
        # Only category names from the fixed enum and aggregate counts.
        d = asdict(self)
        d['sample_categories'] = list(self.sample_categories)
        return d


def aggregate_samples(cards: Sequence[Mapping[str, Any]],
                      details: Sequence[Mapping[str, Any]] = ()) -> CategorySample:
    """Prefer card-attested categories; fill *only missing* records from details.

    Caller must provide details in the order of missing records. Never treat a
    detail sample as proof of categories for other, unopened results.
    """
    card_values = [recognized_record(c)[0] for c in cards]
    missing_positions = [i for i, v in enumerate(card_values) if v is None]
    result = card_values[:]
    for index, detail in enumerate(details):
        if index >= len(missing_positions):
            break
        value, _ = recognized_record(detail)
        if value is not None:
            result[missing_positions[index]] = value
    return CategorySample(
        cards_observed=len(cards),
        cards_with_category=sum(v is not None for v in card_values),
        cards_ambiguous=sum(x.get('status')=='AMBIGUOUS' for x in cards),
        details_checked=min(len(details),len(missing_positions)),
        details_with_category=sum(recognized_record(x)[0] is not None for x in list(details)[:len(missing_positions)]),
        details_ambiguous=sum(x.get('status')=='AMBIGUOUS' for x in list(details)[:len(missing_positions)]),
        matching=sum(v == 'fournitures' for v in result),
        mismatching=sum(v not in (None,'fournitures') for v in result),
        missing=sum(v is None for v in result),
        sample_categories=tuple(result),
        evidence_source='card_field_or_public_detail',
    )


async def inspect_public_cards(page: Any, *, max_cards: int = 5) -> list[dict[str, Any]]:
    if not 1 <= max_cards <= 10:
        raise ValueError('INVALID_CARD_LIMIT')
    data = await page.evaluate(CATEGORY_FIELDS_JS, {'scope':'cards','limit':max_cards})
    if not isinstance(data, list) or len(data) > max_cards:
        raise ValueError('UNEXPECTED_CARD_EVIDENCE')
    return data


async def inspect_public_detail(page: Any) -> dict[str, Any]:
    value = await page.evaluate(CATEGORY_FIELDS_JS, {'scope':'detail','limit':1})
    if not isinstance(value, dict):
        raise ValueError('UNEXPECTED_DETAIL_EVIDENCE')
    return value


async def sampled_detail_links(page: Any, *, max_links: int = 5) -> list[str | None]:
    """Return positional public detail URLs in memory; never log them.

    A missing/unsafe link stays None, preventing any accidental shift of the
    relationship between one card and a sampled detail page.
    """
    if not 1 <= max_links <= 5:
        raise ValueError('INVALID_DETAIL_LINK_LIMIT')
    raw = await page.evaluate("""max => [...document.querySelectorAll('.tender_item')]
      .slice(0, max).map(card => card.querySelector(
        'a[href*="EntrepriseDetailsConsultation"]')?.getAttribute('href') || null)""", max_links)
    if not isinstance(raw, list) or len(raw) > max_links:
        return []
    return [safe_detail_url(link, page.url) for link in raw]


async def inspect_few_details(context: Any, links: Sequence[str], *, limit: int = 5,
                              timeout_ms: int = 11000) -> list[dict[str, Any]]:
    """Single GET per public detail, no retries or download. Never leave host."""
    if not 1 <= limit <= 5 or not 1000 <= timeout_ms <= 15000:
        raise ValueError('UNSAFE_DETAIL_LIMITS')
    results = []
    for url in list(links)[:limit]:
        if url is None or safe_detail_url(url, url) is None:
            results.append({'status':'MISSING','category':None,'source':None,'reason':'UNSAFE_URL'})
            continue
        p = await context.new_page()
        try:
            response = await p.goto(url, wait_until='domcontentloaded', timeout=timeout_ms)
            if (not response or response.status != 200 or
                safe_detail_url(p.url, p.url) is None):
                results.append({'status':'MISSING','category':None,'source':None,'reason':'DETAIL_NOT_AVAILABLE'})
            else:
                results.append(await inspect_public_detail(p))
        except Exception:
            results.append({'status':'MISSING','category':None,'source':None,'reason':'DETAIL_READ_FAILED'})
        finally:
            await p.close()
    return results