"""Gate 1B-02: DOM-attribute discovery and one public detail spot-check.

Public evidence only. Never export HTML, raw text, hrefs, IPs, form tokens,
refConsultation IDs, cookies, form values, request bodies, or screenshots.
Candidate alt/title values are NOT source-labelled official categories.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping
from urllib.parse import parse_qs, urljoin, urlparse

from category_evidence import inspect_public_detail, recognized_record

HOST = "www.marchespublics.gov.ma"
DETAIL_PAGE_NAMES = (
    "entreprise.EntrepriseDetailsConsultation",
    "entreprise.EntrepriseDetailConsultation",
)
KNOWN = {"fournitures", "travaux", "services"}
ATTRIBUTE_KINDS = {"alt", "title", "aria-label", "data-category", "data-categorie", "data-type"}

# All string values returning to Python are from fixed enumerations. No raw
# outerHTML, titles, labels, reference IDs, HTML attributes or query values.
CARD_ATTR_JS = r"""(limit) => {
  function clean(s) { return (s || '').trim().toLowerCase().normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '').replace(/\s+/g, ' '); }
  const known = new Set(['fournitures', 'travaux', 'services']);
  const keys = ['alt','title','aria-label','data-category','data-categorie','data-type'];
  const cards = [...document.querySelectorAll('.tender_item')].slice(0, limit);
  const cat = document.querySelector('#ctl0_CONTENU_PAGE_AdvancedSearch_categorie');
  const option = cat?.options?.[cat.selectedIndex];
  const checked = option ? clean(option.textContent) : '';
  const output = cards.map(card => {
    const sources = new Set();
    const values = new Set();
    let candidateNodes = 0;
    // inspect attributes in browser; export fixed enums only, NOT HTML.
    for (const n of [card,...card.querySelectorAll('*')].slice(0,200)) {
      let candidate = false;
      for (const key of keys) {
        const value = n.getAttribute?.(key);
        if (value && known.has(clean(value))) {
          sources.add(key);
          values.add(clean(value));
          candidate = true;
        }
      }
      if (candidate) candidateNodes++;
    }
    const links = [...card.querySelectorAll('a[href]')];
    let detailLinkRoute = 'NONE';
    for (const a of links) {
      const href=a.getAttribute('href') || '';
      const singular=href.includes('EntrepriseDetailConsultation');
      const plural=href.includes('EntrepriseDetailsConsultation');
      if (singular || plural) {
        detailLinkRoute = plural ? 'PLURAL' : 'SINGULAR';
        break;
      }
    }
    const tag = card.tagName?.toUpperCase();
    return {container_tag:['DIV','TR','LI'].includes(tag) ? tag : 'OTHER',
      attribute_candidate_values:[...values].sort(),
      attribute_candidate_sources:[...sources].sort(),
      candidate_element_count:Math.min(candidateNodes,200),
      detail_link_route:detailLinkRoute};
  });
  return {cards_observed:cards.length,
    result_rows_visible:document.querySelectorAll('tr').length > 0,
    server_echo: {
      selected_option_is_fournitures: checked==='fournitures',
      selected_markup_attribute_present:option?.hasAttribute('selected') || false,
      search_control_still_present: !!cat
    },
    cards:output};
}"""

DETAIL_STRUCTURE_JS = r"""() => {
 const root=document.querySelector('#ctl0_CONTENU_PAGE') || document.querySelector('main');
 if (!root) return {container_present:false, explicit_category_label_present:false,
                    category_attribute_candidates:0, label_tag_types:[]};
 function fold(s) {return (s || '').trim().toLowerCase().normalize('NFD')
     .replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ');}
 const labelRe=/^(categorie(?: principale| du marche)?|nature du marche|type de marche)\s*[:\-]?$/;
 const labels=new Set();
 let candidateCount=0;
 const cats=new Set(['fournitures','travaux','services']);
 for (const e of [root,...root.querySelectorAll('*')].slice(0,800)) {
   const text=fold(e.textContent || '');
   if (text.length<=70 && e.children.length===0 && labelRe.test(text))
     labels.add(['TH','DT','STRONG','LABEL','TD','SPAN'].includes(e.tagName) ? e.tagName : 'OTHER');
   for (const key of ['alt','title','aria-label','data-category','data-categorie']) {
     const v=e.getAttribute?.(key);
     if(v && cats.has(fold(v))) {candidateCount++; break;}
   }
 }
 return {container_present:true, explicit_category_label_present:labels.size>0,
         category_attribute_candidates:Math.min(candidateCount,200),
         label_tag_types:[...labels].sort()};
}"""


def allowed_detail_url(raw: object, base: str) -> str | None:
    """Exact host, official public detail route, no action/download controls."""
    if not isinstance(raw, str) or not raw or len(raw) > 1800:
        return None
    try:
        url = urljoin(base, raw)
        u = urlparse(url)
        if (u.scheme != "https" or u.hostname != HOST or u.username or
            u.password or u.port not in (None, 443) or
            u.path not in ("/", "/index.php") or u.fragment):
            return None
        qs = parse_qs(u.query, keep_blank_values=True)
        if qs.get("page") not in ([DETAIL_PAGE_NAMES[0]], [DETAIL_PAGE_NAMES[1]]):
            return None
        if len(qs) < 2 or len(qs) > 9:
            return None
        forbidden = ("download","dce","file","document","archive","attachment",
                     "auth","token","action","captcha","connexion","redirect")
        if any(any(s in k.casefold() for s in forbidden) for k in qs):
            return None
        if any(any(len(v) > 800 for v in values) for values in qs.values()):
            return None
        return url
    except (ValueError, TypeError):
        return None


def classify_card_attributes(value: Mapping[str, Any]) -> dict[str, Any]:
    """Card icon/alt/title candidates are not official field evidence."""
    cards = value.get("cards", [])
    if not isinstance(cards, list):
        return {"status":"INVALID_INSPECTION","cards":0,"candidate_cards":0,
                "candidate_fournitures":0,"candidate_other":0}
    cards = cards[:5]
    counts = {"candidate_cards":0, "candidate_fournitures":0, "candidate_other":0}
    for c in cards:
        if not isinstance(c, Mapping): continue
        vals = set(c.get("attribute_candidate_values", [])) & KNOWN
        if vals:
            counts["candidate_cards"] += 1
        if "fournitures" in vals: counts["candidate_fournitures"] += 1
        if vals & {"travaux","services"}: counts["candidate_other"] += 1
    return {"status":"ATTRIBUTE_CANDIDATES_ONLY" if counts["candidate_cards"] else "NO_ATTRIBUTE_CANDIDATES",
            "cards":len(cards), **counts}


@dataclass(frozen=True)
class DirectSpotCheck:
    status: str
    reason_code: str
    official_category: str | None
    trusted_source: bool
    records_verified: int
    can_claim_all_results: bool = False

    def report(self) -> dict[str, Any]:
        return asdict(self)


def decide_detail_proof(postback_applied: bool, detail_record: Mapping[str, Any] | None) -> DirectSpotCheck:
    """Confirm at most one inspected record; never whole-filter confirmation."""
    if not postback_applied:
        return DirectSpotCheck("UNCONFIRMED","SEARCH_POSTBACK_NOT_APPLIED",None,False,0)
    if not isinstance(detail_record, Mapping):
        return DirectSpotCheck("UNCONFIRMED","NO_TRUSTED_PUBLIC_DETAIL",None,False,0)
    category, _ = recognized_record(detail_record)
    if category == "fournitures":
        return DirectSpotCheck("DIRECT_SPOT_CHECK_ONLY","ONE_DETAIL_SOURCE_LABELLED_FOURNITURES",
                               category,True,1)
    if category in {"travaux","services"}:
        return DirectSpotCheck("CONTRADICTED_SPOT_CHECK","ONE_DETAIL_SOURCE_LABELLED_OTHER_CATEGORY",
                               category,True,1)
    return DirectSpotCheck("UNCONFIRMED","DETAIL_HAS_NO_EXPLICIT_CATEGORY",None,False,0)


def interpret_differential(fourni_ids: set[str], travaux_ids: set[str],
                           fourn_total: int, travaux_total: int) -> str:
    """A disjoint first-page sample can NEVER prove whole-set disjointness."""
    if (not fourni_ids or not travaux_ids or
        not all(isinstance(x,str) and x for x in fourni_ids|travaux_ids) or
        type(fourn_total) is not int or type(travaux_total) is not int or
        fourn_total < 0 or travaux_total < 0):
        return "DIFFERENTIAL_UNCONFIRMED"
    if fourni_ids & travaux_ids:
        return "DIFFERENTIAL_SAMPLE_OVERLAP_REVIEW"
    return "DIFFERENTIAL_SUPPORT_ONLY"


async def inspect_card_structure(page: Any) -> dict[str, Any]:
    data = await page.evaluate(CARD_ATTR_JS, 5)
    if not isinstance(data, dict) or not isinstance(data.get("cards"),list):
        return {"status":"INVALID_INSPECTION", "cards_observed":0}
    return {
        "cards_observed":min(5,len(data["cards"])),
        "card_container_tags":[v.get("container_tag","OTHER") for v in data["cards"][:5]
                               if isinstance(v,dict)],
        "detail_link_routes":[v.get("detail_link_route","NONE") for v in data["cards"][:5]
                              if isinstance(v,dict)],
        "attribute_candidates":classify_card_attributes(data),
        "post_search_selected":bool(data.get("server_echo",{}).get("selected_option_is_fournitures")),
        "selected_markup_attribute_present":bool(
            data.get("server_echo",{}).get("selected_markup_attribute_present")),
        "search_control_still_present":bool(
            data.get("server_echo",{}).get("search_control_still_present")),
    }


async def one_detail_link(page: Any) -> str | None:
    # Link returned only in RAM and never persisted in reports.
    raw = await page.evaluate("""() => {
      const first=document.querySelector('.tender_item');
      return [...(first?.querySelectorAll('a[href]') || [])]
        .map(a => a.getAttribute('href'))
        .find(h => /EntrepriseDetails?Consultation/.test(h || '')) || null;
    }""")
    return allowed_detail_url(raw, page.url) if raw else None


async def inspect_one_public_detail(context: Any, url: str | None) -> dict[str, Any]:
    """At most one detail GET with commit-first navigation and sanitized report."""
    report = {"status":"NOT_CHECKED","http_status":None,
              "detail_field":None,"structure":None}
    if url is None or allowed_detail_url(url,url) is None:
        report["status"] = "DETAIL_LINK_NOT_VERIFIED"
        return report
    page = await context.new_page()
    try:
        resp = await page.goto(url, wait_until="commit", timeout=17000)
        report["http_status"] = resp.status if resp else None
        if report["http_status"] != 200 or allowed_detail_url(page.url,page.url) is None:
            report["status"] = "PUBLIC_DETAIL_NOT_AVAILABLE"
            return report
        try:
            await page.wait_for_function("""() => !!document.querySelector(
              '#ctl0_CONTENU_PAGE, main')""",timeout=9000)
        except Exception:
            report["status"] = "DETAIL_BODY_NOT_READY"
            return report
        field=await inspect_public_detail(page)
        structure=await page.evaluate(DETAIL_STRUCTURE_JS)
        category, reason=recognized_record(field)
        report["detail_field"] = {
            "status": field.get("status") if field.get("status") in
                      {"EXPLICIT","MISSING","AMBIGUOUS"} else "UNKNOWN",
            "source": field.get("source") if field.get("source") in
                      {"explicit_label_pair","explicit_inline_label","explicit_data_attribute"} else None,
            "official_category": category,
            "reason_code":reason,
        }
        report["structure"] = structure if isinstance(structure,dict) else None
        report["status"] = "DETAIL_INSPECTED"
        return report
    except Exception as exc:
        report["status"] = "DETAIL_EXCEPTION"
        report["error_class"] = type(exc).__name__[:35]
        return report
    finally:
        await page.close()
