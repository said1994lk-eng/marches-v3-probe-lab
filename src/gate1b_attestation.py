"""Gate 1B: evidence-limited Fournitures filter attestation.

A search is ONE user-equivalent click, with a bounded AJAX/document POST
response observer. Never equate an HTTP 200, a dropdown selection, a PAGESTATE
change or a word in the title with category proof. No storage/DCE/coverage.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

from category_evidence import (
    CategorySample, aggregate_samples, inspect_few_details,
    inspect_public_cards, sampled_detail_links,
)
from filter_attestation import normalized_category
from navigation_destination import classify_destination

HOST = "www.marchespublics.gov.ma"
CATEGORY = "#ctl0_CONTENU_PAGE_AdvancedSearch_categorie"
BUTTON = "#ctl0_CONTENU_PAGE_AdvancedSearch_lancerRecherche"
SAMPLE_LIMIT = 5

# The PAGESTATE is inspected only inside the browser or temporarily in memory,
# never exported or logged. The >20 heuristic is diagnostic, not authentication.
FORM_JS = r"""() => {
  const c = document.querySelector('#ctl0_CONTENU_PAGE_AdvancedSearch_categorie');
  const b = document.querySelector('#ctl0_CONTENU_PAGE_AdvancedSearch_lancerRecherche');
  const p = document.querySelector('input[name="PRADO_PAGESTATE"], input#PRADO_PAGESTATE');
  const option = c?.options?.[c.selectedIndex];
  return {category: !!c, button: !!b && !b.disabled, pagestate: !!p,
          pagestate_value: p?.value || '', selected_label: (option?.text || '').trim(),
          ready: document.readyState};
}"""

RESULT_JS = r"""() => {
  const text = document.body?.innerText || '';
  const m = /Nombre de r[eé]sultats\s*:\s*([\d\s\u00a0]+)/i.exec(text);
  const total = m ? Number(m[1].replace(/\D/g, '')) : null;
  const cards = [...document.querySelectorAll('.tender_item')];
  const details = cards.map(c => c.querySelector(
     'a[href*="EntrepriseDetailsConsultation"]')?.getAttribute('href') || '');
  return {total, count_label: !!m, cards:cards.length, first: details[0] || '',
          last: details[details.length - 1] || ''};
}"""


@dataclass(frozen=True)
class Decision:
    status: str
    selection_state: str
    postback_state: str
    results_verification_state: str
    reason_code: str
    official_total: int | None
    sample_rows_checked: int
    fournitures_rows_matched: int
    contaminating_rows_found: int
    unclassified_rows: int
    sampled_only: bool = True

    def report(self) -> dict[str, Any]:
        return asdict(self)


def assess_gate(*, selected: bool, settled: bool, post_status: int | None,
                results_ready: bool, pagestate_changed: bool,
                result_transition: bool, official_total: int | None,
                sample: CategorySample, minimum_sample: int = SAMPLE_LIMIT) -> Decision:
    """Pure, fail-closed three-stage policy; no whole-portal claims."""
    if not 1 <= minimum_sample <= 10:
        raise ValueError("INVALID_SAMPLE")
    valid_total = isinstance(official_total, int) and not isinstance(official_total, bool) and official_total > 0
    expected = min(minimum_sample, official_total) if valid_total else minimum_sample
    selection = "SELECTED" if selected and settled else ("UNSETTLED" if selected else "NOT_SELECTED")
    applied = post_status == 200 and results_ready and (pagestate_changed or result_transition)
    postback = "APPLIED" if applied else ("POST_200_UNVERIFIED" if post_status == 200 else "NOT_APPLIED")
    matching = sample.matching
    mismatch = sample.mismatching
    unknown = sample.missing
    size = sample.cards_observed
    if not selected:
        status, reason = "UNCONFIRMED", "CATEGORY_SELECTION_NOT_VERIFIED"
    elif not settled:
        status, reason = "UNCONFIRMED", "PRADO_CALLBACK_NOT_SETTLED"
    elif post_status != 200:
        status, reason = "UNCONFIRMED", "SEARCH_POST_RESPONSE_NOT_200"
    elif not results_ready:
        status, reason = "UNCONFIRMED", "RESULTS_DOM_NOT_READY"
    elif not (pagestate_changed or result_transition):
        status, reason = "UNCONFIRMED", "POSTBACK_EFFECT_NOT_OBSERVED"
    elif mismatch > 0:
        status, reason = "CONTRADICTED_SAMPLE", "NON_FOURNITURES_CATEGORY_OBSERVED"
    elif not valid_total:
        status, reason = "UNCONFIRMED", "OFFICIAL_TOTAL_UNVERIFIED"
    elif size < expected or unknown or matching < expected:
        status, reason = "UNCONFIRMED", "SOURCE_CATEGORY_SAMPLE_INCOMPLETE"
    else:
        status, reason = "SAMPLED_CONFIRMED", "SOURCE_LABELLED_FOURNITURES_SAMPLE"
    verification = (
        "CONFIRMED_BY_RESULTS_SAMPLE" if status == "SAMPLED_CONFIRMED"
        else "CONTRADICTED_BY_RESULTS_SAMPLE" if status == "CONTRADICTED_SAMPLE"
        else "UNCONFIRMED"
    )
    return Decision(status, selection, postback, verification, reason,
                    official_total if valid_total else None, size, matching,
                    mismatch, unknown)


def _approved_response(response: Any) -> bool:
    try:
        req = response.request
        url = urlparse(response.url)
        return (url.scheme == "https" and url.hostname == HOST and
                url.username is None and url.password is None and
                url.port in (None, 443) and url.path in ("/", "/index.php") and
                not url.fragment and req.method == "POST" and
                req.resource_type in {"xhr", "fetch", "document"})
    except Exception:
        return False


def _public_snapshot_ok(snapshot: dict) -> bool:
    return (isinstance(snapshot, dict) and snapshot.get("count_label") is True
            and isinstance(snapshot.get("cards"), int) and
            not isinstance(snapshot.get("cards"), bool)
            and snapshot["cards"] > 0)


async def _settle_prado(page: Any, pending: set[int], *, timeout_ms: int = 9000,
                        stable_ms: int = 700) -> tuple[bool, bool, str | None]:
    """Verify selection and PAGESTATE are unchanged for a quiet interval.

    PAGESTATE text is transient private state. Only boolean evidence is
    returned. Request tracking observes public-host XHR/fetch, no request data.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    last = None
    since = time.monotonic()
    while time.monotonic() < deadline:
        try:
            snap = await page.evaluate(FORM_JS)
        except Exception:
            return False, False, None
        label = snap.get("selected_label", "")
        selected = normalized_category(label) == "fournitures"
        token = snap.get("pagestate_value", "")
        ready = (selected and snap.get("button") is True and
                 snap.get("category") is True and snap.get("pagestate") is True and
                 isinstance(token, str) and len(token) > 20)
        if not ready:
            last = None
            since = time.monotonic()
        elif not pending:
            # Comparison only; never add this token to reports.
            if token != last:
                last = token
                since = time.monotonic()
            elif (time.monotonic() - since) * 1000 >= stable_ms:
                return True, True, token
        else:
            last = None
            since = time.monotonic()
        await asyncio.sleep(0.15)
    return False, False, None


async def run_gate_1b(page: Any, context: Any, *, max_detail_pages: int = 5) -> dict[str, Any]:
    """Call ONLY after navigation.form_ready; one search click, no retry.

    max_detail_pages=0 enables a zero-detail discovery mode so a newer,
    separately reviewed spot-check can make exactly one public detail GET.
    """
    if not 0 <= max_detail_pages <= 5:
        raise ValueError("INVALID_DETAIL_BUDGET")
    started = time.monotonic()
    report: dict[str, Any] = {
        "schema": "marches-gate1b-filter/1",
        "status": "STARTED",
        "form_hydrated": False,
        "selection_state": "NOT_STARTED",
        "postback_state": "NOT_STARTED",
        "postback_kind": None,
        "postback_http_status": None,
        "pagestate_changed": False,
        "result_transition_seen": False,
        "results_verification_state": "UNTESTED",
        "official_total": None,
        "sample_rows_checked": 0,
        "fournitures_rows_matched": 0,
        "contaminating_rows_found": 0,
        "unclassified_rows": 0,
        "scope": "FIRST_PAGE_SAMPLE_ONLY",
        "reason_code": None,
        "search_clicks": 0,
    }
    pending: set[int] = set()

    def track_request(req: Any) -> None:
        try:
            if urlparse(req.url).hostname == HOST and req.resource_type in ("xhr", "fetch"):
                pending.add(id(req))
        except Exception:
            pass

    def untrack_request(req: Any) -> None:
        pending.discard(id(req))

    def done(status: str, reason: str) -> dict[str, Any]:
        report["status"] = status
        report["reason_code"] = reason
        return report

    page.on("request", track_request)
    page.on("requestfinished", untrack_request)
    page.on("requestfailed", untrack_request)
    try:
        if classify_destination(getattr(page, "url", "")) != "OFFICIAL_ADVANCED_SEARCH_ROUTE":
            return done("UNCONFIRMED", "NOT_OFFICIAL_ADVANCED_SEARCH")
        # Do not assume the document is hydrated merely because commit returned.
        try:
            await page.wait_for_function(r"""() => {
              const c=document.querySelector('#ctl0_CONTENU_PAGE_AdvancedSearch_categorie');
              const b=document.querySelector('#ctl0_CONTENU_PAGE_AdvancedSearch_lancerRecherche');
              const p=document.querySelector('input[name="PRADO_PAGESTATE"],input#PRADO_PAGESTATE');
              return !!c && !!b && !b.disabled && !!p && typeof p.value==='string'
                     && p.value.length > 20;
            }""", timeout=14000, polling=150)
        except Exception:
            return done("UNCONFIRMED", "FORM_HYDRATION_NOT_PROVEN")
        report["form_hydrated"] = True
        initial = await page.evaluate(FORM_JS)
        before = await page.evaluate(RESULT_JS)
        cat = page.locator(CATEGORY)
        btn = page.locator(BUTTON)
        if await cat.count() != 1 or await btn.count() != 1:
            return done("UNCONFIRMED", "NON_UNIQUE_FORM_CONTROLS")
        try:
            await cat.select_option(label="Fournitures", timeout=11000)
        except Exception:
            return done("UNCONFIRMED", "SELECTION_ACTION_FAILED")
        settled, selected, settled_token = await _settle_prado(page, pending)
        report["selection_state"] = "SELECTED" if selected else "UNSETTLED"
        if not settled or settled_token is None:
            return done("UNCONFIRMED", "PRADO_CALLBACK_NOT_SETTLED")

        # One click only. A PRADO response may be an XHR or a full document
        # POST; expect_navigation would time out for XHR-only updates.
        seen: list[tuple[int, str]] = []
        def response_observer(response: Any) -> None:
            if _approved_response(response):
                kind = response.request.resource_type
                seen.append((response.status, kind))

        page.on("response", response_observer)
        try:
            report["search_clicks"] = 1
            try:
                await btn.click(timeout=13000, no_wait_after=True)
            except Exception:
                return done("UNCONFIRMED", "SEARCH_CLICK_NOT_CONFIRMED_NO_RETRY")
            deadline = time.monotonic() + 17
            while time.monotonic() < deadline and not seen:
                await asyncio.sleep(0.15)
            if not seen:
                return done("UNCONFIRMED", "SEARCH_POST_NOT_OBSERVED")
            status, kind = seen[0]
            report["postback_http_status"] = status
            report["postback_kind"] = "AJAX_POST" if kind in ("xhr", "fetch") else "DOCUMENT_POST"
            if status != 200:
                return done("UNCONFIRMED", "SEARCH_POST_HTTP_NOT_200")
        finally:
            page.remove_listener("response", response_observer)

        if classify_destination(getattr(page, "url", "")) != "OFFICIAL_ADVANCED_SEARCH_ROUTE":
            return done("UNCONFIRMED", "UNEXPECTED_SEARCH_DESTINATION")
        try:
            await page.wait_for_function(r"""() => {
              const text=document.body?.innerText || '';
              return document.querySelectorAll('.tender_item').length > 0
                && /Nombre de r[eé]sultats\s*:/i.test(text);
            }""", timeout=13000, polling=200)
        except Exception:
            return done("UNCONFIRMED", "RESULTS_DOM_NOT_READY")
        # Response may arrive before AJAX finishes replacing result cards.
        await asyncio.sleep(0.45)
        after = await page.evaluate(RESULT_JS)
        post = await page.evaluate(FORM_JS)
        report["official_total"] = after.get("total")
        report["pagestate_changed"] = (
            isinstance(post.get("pagestate_value"), str)
            and bool(post.get("pagestate_value"))
            and post["pagestate_value"] != settled_token
        )
        report["result_transition_seen"] = (
            after.get("first") != before.get("first") or
            after.get("last") != before.get("last") or
            after.get("total") != before.get("total") or
            after.get("cards") != before.get("cards")
        )
        if not _public_snapshot_ok(after):
            return done("UNCONFIRMED", "RESULTS_DOM_NOT_READY")
        report["postback_state"] = (
            "APPLIED" if report["pagestate_changed"] or report["result_transition_seen"]
            else "POST_200_UNVERIFIED"
        )
        # Source-labelled category only. Text in the tender title NEVER counts.
        cards = await inspect_public_cards(page, max_cards=SAMPLE_LIMIT)
        missing_positions = [i for i, c in enumerate(cards) if c.get("status") != "EXPLICIT"]
        details = []
        if missing_positions and max_detail_pages > 0:
            links = await sampled_detail_links(page, max_links=SAMPLE_LIMIT)
            positional = [links[i] if i < len(links) else None for i in missing_positions]
            details = await inspect_few_details(
                context, positional[:max_detail_pages], limit=max_detail_pages
            )
        sample = aggregate_samples(cards, details)
        decision = assess_gate(
            selected=selected, settled=settled,
            post_status=report["postback_http_status"],
            results_ready=True,
            pagestate_changed=report["pagestate_changed"],
            result_transition=report["result_transition_seen"],
            official_total=after.get("total"), sample=sample,
        )
        report.update({
            "status": decision.status,
            "selection_state": decision.selection_state,
            "postback_state": decision.postback_state,
            "results_verification_state": decision.results_verification_state,
            "reason_code": decision.reason_code,
            "sample_rows_checked": decision.sample_rows_checked,
            "fournitures_rows_matched": decision.fournitures_rows_matched,
            "contaminating_rows_found": decision.contaminating_rows_found,
            "unclassified_rows": decision.unclassified_rows,
        })
        return report
    except Exception as exc:
        return done("UNCONFIRMED", "GATE_EXCEPTION_" + type(exc).__name__[:40])
    finally:
        for event, callback in (
            ("request", track_request),
            ("requestfinished", untrack_request),
            ("requestfailed", untrack_request),
        ):
            try:
                page.remove_listener(event, callback)
            except Exception:
                pass
        report["duration_ms"] = round((time.monotonic() - started) * 1000)
