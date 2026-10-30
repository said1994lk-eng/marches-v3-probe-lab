"""Strict detail-page category parser independent of a specific container ID.

Only an explicit official field label/value pairing counts. Full page text,
title keywords, menu filters, form dropdowns, image alt/title, raw HTML, URLs,
and PRADO tokens are NEVER returned as category proof.
"""
from __future__ import annotations
from typing import Any

DETAIL_CATEGORY_JS = r"""() => {
  const body = document.body;
  const root =
    document.querySelector('#ctl0_CONTENU_PAGE') ||
    document.querySelector('main') ||
    document.querySelector('[id^="ctl0_CONTENU_PAGE_"]') ||
    body;
  const context = !root ? 'NO_BODY' : root === body ? 'BODY_FALLBACK' : 'CONTENT_ROOT';
  const fold = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase()
      .normalize('NFD').replace(/[\u0300-\u036f]/g,'');
  const cats = new Set(['fournitures','travaux','services']);
  const labelOnly = /^(categorie principale|categorie du marche)\s*[:\-]?$/;
  const inline = /^(categorie principale|categorie du marche)\s*[:\-]\s*(fournitures|travaux|services)$/;
  const hits = [];
  let labelledNodes = 0;
  function category(el) {
    if (!el) return null;
    if (el.matches?.('input,select,option,textarea,button')) return null;
    if (el.querySelector?.('input,select,textarea,button')) return null;
    const raw=(el.textContent || '');
    if (raw.length > 70) return null;
    const v=fold(raw);
    return cats.has(v) ? v : null;
  }
  if (root) {
    const elements = [...root.querySelectorAll('th,td,dt,dd,label,strong,span,p,div,li,b')].slice(0,1600);
    for (const e of elements) {
      // Only leaf labels and leaf inline category declarations.
      if (e.children.length !== 0) continue;
      const raw=e.textContent || '';
      if(raw.length > 110) continue;
      const v=fold(raw);
      const direct=inline.exec(v);
      if (direct) {
        labelledNodes++;
        hits.push({value:direct[2],method:'explicit_inline_label'});
        continue;
      }
      if (!labelOnly.test(v)) continue;
      labelledNodes++;
      const candidates = [];
      if (e.nextElementSibling) candidates.push(e.nextElementSibling);
      const parent=e.parentElement;
      if (parent && parent.children.length===2)
        for(const x of parent.children) if(x!==e) candidates.push(x);
      const cell=e.closest('th,td,dt,dd');
      if (cell && cell!==e && cell.nextElementSibling) candidates.push(cell.nextElementSibling);
      // Adjacent parent block is useful for PRADO's nested strong -> div.
      if(parent && parent.textContent.trim()===raw.trim() && parent.nextElementSibling)
        candidates.push(parent.nextElementSibling);
      for (const x of candidates) {
        const cat=category(x);
        if(cat) hits.push({value:cat,method:'explicit_label_pair'});
      }
    }
  }
  const values=[...new Set(hits.map(h=>h.value))];
  const status = values.length===1 ? 'EXPLICIT' : values.length ? 'AMBIGUOUS' : 'MISSING';
  const source = hits.some(h=>h.method==='explicit_label_pair')
        ? 'explicit_label_pair'
        : hits.length ? 'explicit_inline_label' : null;
  const bodyLen = (body?.innerText || '').length;
  const textSize = bodyLen===0 ? 'ZERO' : bodyLen<100 ? 'SHORT'
                   : bodyLen<1000 ? 'MEDIUM' : 'LONG';
  return {status, category:status==='EXPLICIT'?values[0]:null,
          source:status==='EXPLICIT'?source:null,
          context, explicit_label_nodes:Math.min(labelledNodes,50),
          body_text_bucket:textSize,
          ready_state: document.readyState};
}"""


async def strict_detail_category(page: Any) -> dict:
    """Return small whitelist JSON only; no arbitrary DOM text leaves browser."""
    result = await page.evaluate(DETAIL_CATEGORY_JS)
    if not isinstance(result,dict):
        return {"status":"MISSING","category":None,"source":None,
                "context":"UNKNOWN","body_text_bucket":"UNKNOWN"}
    status = result.get("status") if result.get("status") in {"EXPLICIT","MISSING","AMBIGUOUS"} else "MISSING"
    category = result.get("category") if result.get("category") in {"fournitures","travaux","services"} else None
    source = result.get("source") if result.get("source") in {"explicit_label_pair","explicit_inline_label"} else None
    if status=="EXPLICIT" and (category is None or source is None):status="MISSING"
    return {
        "status":status,
        "category":category if status=="EXPLICIT" else None,
        "source":source if status=="EXPLICIT" else None,
        "context":result.get("context") if result.get("context") in
                  {"NO_BODY","BODY_FALLBACK","CONTENT_ROOT"} else "UNKNOWN",
        "explicit_label_nodes":min(50,max(0,int(result.get("explicit_label_nodes",0)))),
        "body_text_bucket":result.get("body_text_bucket") if result.get("body_text_bucket") in
                           {"ZERO","SHORT","MEDIUM","LONG"} else "UNKNOWN",
        "ready_state":result.get("ready_state") if result.get("ready_state") in
                       {"loading","interactive","complete"} else "UNKNOWN",
    }
