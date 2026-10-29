"""Gate 1A-01: safe, read-only classification of a public portal page.

This module is deliberately independent of Playwright at import time.  The
classifier is deterministic and can be tested against sanitized DOM signals.
It does NOT attest Fournitures, page size, pagination or full coverage.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping


class PageState(str, Enum):
    FORM_READY = "FORM_READY"
    RESULTS_VIEW = "RESULTS_VIEW"
    ERROR_PAGE = "ERROR_PAGE"
    BLANK_OR_LOADING = "BLANK_OR_LOADING"
    UNKNOWN_LAYOUT = "UNKNOWN_LAYOUT"


class NextAction(str, Enum):
    APPLY_FILTER_WITH_ATTESTATION = "APPLY_FILTER_WITH_ATTESTATION"
    LOCATE_SEARCH_FORM = "LOCATE_SEARCH_FORM"
    STOP_AND_RECORD_ERROR = "STOP_AND_RECORD_ERROR"
    WAIT_WITH_BOUNDED_TIMEOUT = "WAIT_WITH_BOUNDED_TIMEOUT"
    STOP_AND_REVIEW_STRUCTURE = "STOP_AND_REVIEW_STRUCTURE"


@dataclass(frozen=True)
class Classification:
    state: PageState
    reason_code: str
    next_action: NextAction
    confidence: str
    navigation_timed_out: bool
    signals: dict[str, Any]

    def as_report(self) -> dict[str, Any]:
        output = asdict(self)
        output["state"] = self.state.value
        output["next_action"] = self.next_action.value
        return output


def _count(value: Any) -> int:
    """Tolerate sparse/old JSON logs, not arbitrary truthy strings."""
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value)) if value is not None else 0
    except (TypeError, ValueError, OverflowError):
        return 0


def _flag(value: Any) -> bool:
    return value is True


def classify_page(
    snapshot: Mapping[str, Any] | None,
    *,
    http_status: int | None = None,
    navigation_timed_out: bool = False,
) -> Classification:
    """Classify *observed page type*; never infer a successful search.

    A timeout does not override evidence of a rendered results page.  HTTP 200
    alone is never proof that the advanced search form is present.  A results
    count label of 0 is not proof that the portal contains zero tenders.
    """
    snapshot = snapshot or {}
    ready_state = snapshot.get("ready_state")
    if ready_state not in {"loading", "interactive", "complete"}:
        ready_state = "unknown"
    category_present = _flag(snapshot.get("category_control_found"))
    category_semantic = _flag(snapshot.get("semantic_category_control_found"))
    has_form = category_present or category_semantic
    has_result_count = _flag(snapshot.get("has_result_count_label"))
    tender_cards = _count(snapshot.get("tender_cards"))
    detail_links = _count(snapshot.get("detail_links"))
    body_text_length = _count(snapshot.get("body_text_length"))
    body_html_length = _count(snapshot.get("body_html_length"))
    errors = snapshot.get("error_signals")
    errors = errors if isinstance(errors, dict) else {}
    challenge = _flag(errors.get("captcha")) or _flag(errors.get("auth_required"))
    access_denied = _flag(errors.get("access_denied"))
    site_failure = _flag(errors.get("service_unavailable"))
    try:
        status = int(http_status) if http_status is not None else None
    except (TypeError, ValueError, OverflowError):
        status = None

    evidence = {
        "ready_state": ready_state,
        "category_control_found": category_present,
        "semantic_category_control_found": category_semantic,
        "has_result_count_label": has_result_count,
        "tender_cards": tender_cards,
        "detail_links": detail_links,
        "body_text_length": body_text_length,
        "body_html_length": body_html_length,
        "http_status": status,
        "challenge_signalled": challenge,
        "access_denied_signalled": access_denied,
        "service_unavailable_signalled": site_failure,
    }

    def decision(state: PageState, reason: str, action: NextAction, confidence: str) -> Classification:
        return Classification(state, reason, action, confidence, navigation_timed_out, evidence)

    # Do not treat an access challenge as an invitation to work around it.
    if status in {401, 403, 429} or challenge or access_denied:
        return decision(PageState.ERROR_PAGE, "ACCESS_OR_CHALLENGE", NextAction.STOP_AND_RECORD_ERROR, "HIGH")
    if status is not None and status >= 400:
        return decision(PageState.ERROR_PAGE, "HTTP_ERROR", NextAction.STOP_AND_RECORD_ERROR, "HIGH")

    # A real category control is stronger evidence of a form than form_count=1.
    if has_form:
        return decision(PageState.FORM_READY, "CATEGORY_CONTROL_PRESENT", NextAction.APPLY_FILTER_WITH_ATTESTATION, "HIGH" if category_present else "MEDIUM")

    # Distinguish results view from search form; this is the actual last-run case.
    if tender_cards > 0:
        return decision(
            PageState.RESULTS_VIEW,
            "RESULT_CARDS_WITH_COUNT" if has_result_count else "RESULT_CARDS_NO_COUNT",
            NextAction.LOCATE_SEARCH_FORM,
            "HIGH" if has_result_count else "MEDIUM",
        )
    if has_result_count:
        return decision(PageState.RESULTS_VIEW, "RESULT_COUNT_ONLY_UNVERIFIED", NextAction.LOCATE_SEARCH_FORM, "LOW")

    if site_failure:
        return decision(PageState.ERROR_PAGE, "PORTAL_ERROR_MESSAGE", NextAction.STOP_AND_RECORD_ERROR, "MEDIUM")
    if ready_state == "loading" or (body_text_length == 0 and body_html_length <= 128):
        return decision(PageState.BLANK_OR_LOADING, "DOCUMENT_EMPTY_OR_LOADING", NextAction.WAIT_WITH_BOUNDED_TIMEOUT, "MEDIUM")
    if navigation_timed_out and body_text_length <= 32:
        return decision(PageState.BLANK_OR_LOADING, "NAVIGATION_TIMEOUT_WITHOUT_CONTENT", NextAction.WAIT_WITH_BOUNDED_TIMEOUT, "MEDIUM")

    return decision(PageState.UNKNOWN_LAYOUT, "NO_RECOGNIZED_PUBLIC_PAGE_MARKERS", NextAction.STOP_AND_REVIEW_STRUCTURE, "LOW")


async def capture_public_signals(page: Any) -> dict[str, Any]:
    """Observe DOM-only booleans/counts; export no HTML, cookie, URL or form values.

    Supports Playwright Page, without importing or launching Playwright here.
    The content is checked in-browser and never returned as raw page text.
    """
    return await page.evaluate(r"""() => {
      const body = document.body;
      const text = body?.innerText || '';
      const main = document.querySelector('#ctl0_CONTENU_PAGE_AdvancedSearch_categorie');
      const semantic = [...document.querySelectorAll('select')].some(select => {
        const identity = `${select.id} ${select.name}`.toLowerCase();
        const hasFournitures = [...select.options].some(option =>
          (option.textContent || '').trim().toLowerCase() === 'fournitures');
        return hasFournitures && /cat[eé]gorie/.test(identity);
      });
      // Only booleans and counts leave the browser. No private inputs or text.
      return {
        ready_state: document.readyState,
        category_control_found: !!main,
        semantic_category_control_found: semantic,
        has_result_count_label: /Nombre de r[eé]sultats\s*:/i.test(text),
        tender_cards: document.querySelectorAll('.tender_item').length,
        detail_links: document.querySelectorAll('.tender_item a[href*="EntrepriseDetailsConsultation"]').length,
        body_text_length: text.length,
        body_html_length: (body?.innerHTML || '').length,
        error_signals: {
          captcha: /captcha|je ne suis pas un robot/i.test(text),
          auth_required: /connexion obligatoire|authentification requise/i.test(text),
          access_denied: /acc[eè]s refus[eé]|access denied|403 forbidden/i.test(text),
          service_unavailable: /service indisponible|site en maintenance|internal server error|bad gateway/i.test(text)
        }
      };
    }""")


async def classify_playwright_page(
    page: Any, *, http_status: int | None = None, navigation_timed_out: bool = False
) -> dict[str, Any]:
    """Structured report fragment used by the V3.2 diagnostic integration."""
    signals = await capture_public_signals(page)
    return classify_page(signals, http_status=http_status, navigation_timed_out=navigation_timed_out).as_report()