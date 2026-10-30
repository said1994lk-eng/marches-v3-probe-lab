"""Gate 1B-02: bounded detail DOM readiness and zero-raw-content diagnostics.

This is NOT a network body/stream monitor. HTML byte count is the *serialized
rendered DOM* size, not HTTP Content-Length, transfer size or proof of throttling.
One commit-first navigation is performed by the caller; this helper only waits.
"""
from __future__ import annotations

from typing import Any

DETAIL_TELEMETRY_JS = r"""() => {
  const body = document.body;
  const html = document.documentElement?.outerHTML || '';
  const len = new TextEncoder().encode(html).length;
  const fold = s => (s || '').trim().normalize('NFD')
      .replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').toLowerCase();
  // Title content is NEVER returned; only one of these fixed labels.
  const title = fold(document.title);
  let titleClass='OTHER';
  if (!title) titleClass='EMPTY';
  else if (/(connexion|identification|login|authentification)/.test(title))
    titleClass='LOGIN_LIKE';
  else if (/(maintenance|indisponible)/.test(title))
    titleClass='MAINTENANCE_LIKE';
  else if (/(erreur|error|interdit)/.test(title))
    titleClass='ERROR_LIKE';
  else if (/(consultation|appel d.offres|marches publics)/.test(title))
    titleClass='PUBLIC_TENDER_LIKE';
  const labelRe=/^(categorie principale|categorie du marche)\s*[:\-]?\s*$/;
  const inlineRe=/^(categorie principale|categorie du marche)\s*[:\-]\s*(fournitures|travaux|services)$/;
  const nodes=body ? body.querySelectorAll('th,td,dt,strong,b,span,div,p,label,li') : [];
  let found=false;
  for (const n of [...nodes].slice(0,1600)) {
    if(n.children.length!==0) continue;
    const t=fold(n.textContent);
    if(t.length<=110 && (labelRe.test(t)||inlineRe.test(t))) {found=true;break;}
  }
  const rawLen=(body?.innerText || '').trim().length;
  return {ready_state:document.readyState,
          category_label_present:found,
          dom_html_bytes:Math.min(len,5000000),
          dom_html_bytes_capped:len>5000000,
          body_text_bucket:rawLen===0?'ZERO':rawLen<100?'SHORT':
                           rawLen<1000?'MEDIUM':'LONG',
          title_class:titleClass};
}"""

PARSED_HTML_JS = r"""() => !!document.body &&
  ['interactive','complete'].includes(document.readyState) &&
  (document.body.innerText || '').trim().length > 0"""

CATEGORY_LABEL_JS = r"""() => {
  const fold = s => (s || '').trim().normalize('NFD')
      .replace(/[\u0300-\u036f]/g,'').replace(/\s+/g,' ').toLowerCase();
  const label=/^(categorie principale|categorie du marche)\s*[:\-]?\s*$/;
  const inline=/^(categorie principale|categorie du marche)\s*[:\-]\s*(fournitures|travaux|services)$/;
  for(const n of [...(document.body?.querySelectorAll('th,td,dt,strong,b,span,div,p,label,li')||[])].slice(0,1600)){
    if(n.children.length!==0) continue;
    const t=fold(n.textContent);
    if(t.length<=110&&(label.test(t)||inline.test(t))) return true;
  }
  return false;
}"""

SAFE_TITLE_CLASSES = {
    "EMPTY", "LOGIN_LIKE", "MAINTENANCE_LIKE",
    "ERROR_LIKE", "PUBLIC_TENDER_LIKE", "OTHER",
}


async def detail_telemetry(page: Any) -> dict:
    """Export fixed enums and numeric DOM size, never raw title/HTML."""
    try:
        data = await page.evaluate(DETAIL_TELEMETRY_JS)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    ready = data.get("ready_state")
    html_bytes = data.get("dom_html_bytes")
    return {
        "ready_state": ready if ready in ("loading", "interactive", "complete") else "UNKNOWN",
        "dom_html_bytes": (
            min(5_000_000, html_bytes)
            if type(html_bytes) is int and html_bytes >= 0 else None
        ),
        "dom_html_bytes_capped": data.get("dom_html_bytes_capped") is True,
        "body_text_bucket": data.get("body_text_bucket")
        if data.get("body_text_bucket") in ("ZERO", "SHORT", "MEDIUM", "LONG") else "UNKNOWN",
        "category_label_present": data.get("category_label_present") is True,
        "title_class": data.get("title_class")
        if data.get("title_class") in SAFE_TITLE_CLASSES else "UNKNOWN",
    }


async def wait_detail_readiness(page: Any, *, parse_timeout_ms: int = 13000,
                                label_timeout_ms: int = 5000) -> dict:
    """First require parsed HTML, then allow bounded time for late PRADO fields.

    A detail without a category label stays UNCONFIRMED. Never wait for load or
    networkidle and never retry navigation; this is purely passive DOM waiting.
    """
    if not (1000 <= parse_timeout_ms <= 20000 and
            0 <= label_timeout_ms <= 8000):
        raise ValueError("UNSAFE_READINESS_TIMEOUT")
    try:
        await page.wait_for_function(PARSED_HTML_JS, timeout=parse_timeout_ms)
    except Exception:
        return {
            "status": "DETAIL_DOCUMENT_NOT_PARSED",
            "telemetry": await detail_telemetry(page),
        }
    initial = await detail_telemetry(page)
    if initial["category_label_present"]:
        return {"status": "READY_EXPLICIT_LABEL_VISIBLE", "telemetry": initial}
    if label_timeout_ms > 0:
        try:
            await page.wait_for_function(CATEGORY_LABEL_JS, timeout=label_timeout_ms)
        except Exception:
            pass
    last = await detail_telemetry(page)
    return {
        "status": "READY_EXPLICIT_LABEL_VISIBLE"
        if last["category_label_present"] else "READY_NO_EXPLICIT_LABEL",
        "telemetry": last,
    }
