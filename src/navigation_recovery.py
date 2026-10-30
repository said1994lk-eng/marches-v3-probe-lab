"""Gate 1A-02: bounded recovery to the *public* advanced-search form.

No automatic workflow, database access, document handling, or bypass of access
controls. Import-time dependencies are Python stdlib plus page_state; Playwright
is only needed when a caller supplies a Page. A results view is *not* a form.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence
from urllib.parse import parse_qs, urlparse

from page_state import classify_playwright_page
from navigation_destination import classify_destination, is_benign_official_redirect

ALLOWED_HOST = "www.marchespublics.gov.ma"
SEARCH_PAGE = "entreprise.EntrepriseAdvancedSearch"


@dataclass(frozen=True)
class Route:
    id: str
    url: str


@dataclass(frozen=True)
class RecoveryResult:
    form_ready: bool
    reason_code: str
    route_id: str | None
    observations: tuple[dict[str, Any], ...]

    def as_report(self) -> dict[str, Any]:
        return {
            "form_ready": self.form_ready,
            "reason_code": self.reason_code,
            "route_id": self.route_id,
            "observations": [dict(x) for x in self.observations],
            "filter_attested": False,
        }


def is_allowed_search_url(url: str) -> bool:
    """Hard allowlist: no fragments, userinfo, nonstandard ports or remote host."""
    try:
        u = urlparse(url)
        if (u.scheme != "https" or u.hostname != ALLOWED_HOST
                or u.username or u.password or u.port not in (None, 443)
                or u.path not in ("/", "/index.php") or u.fragment):
            return False
        return parse_qs(u.query).get("page") == [SEARCH_PAGE]
    except (TypeError, ValueError):
        return False


def navigation_decision(state: str, *, routes_remaining: bool) -> str:
    """Pure policy. Never continue to filtering from a results view."""
    if state == "FORM_READY":
        return "FORM_READY"
    if state == "ERROR_PAGE":
        return "STOP_ACCESS_OR_PORTAL_ERROR"
    if state == "RESULTS_VIEW":
        return "TRY_NEXT_OFFICIAL_ROUTE" if routes_remaining else "SEARCH_FORM_NOT_OBSERVED"
    if state == "BLANK_OR_LOADING":
        return "WAIT_THEN_RECHECK"
    return "STOP_UNKNOWN_LAYOUT"


async def _observe(page: Any, *, status: int | None, timed_out: bool) -> dict[str, Any]:
    try:
        return await classify_playwright_page(
            page, http_status=status, navigation_timed_out=timed_out
        )
    except Exception:
        return {
            "state": "UNKNOWN_LAYOUT",
            "reason_code": "DOM_CLASSIFICATION_UNAVAILABLE",
            "next_action": "STOP_AND_REVIEW_STRUCTURE",
            "confidence": "LOW",
        }


async def recover_search_form(
    page: Any,
    routes: Sequence[Route],
    *,
    navigation_timeout_ms: int = 28000,
    settle_wait_ms: int = 1200,
) -> RecoveryResult:
    """Open at most two trusted routes once each; bounded passive recheck.

    No blind click, POST, category selection, CAPTCHA processing, proxy or
    alternative host. On a navigation timeout, a rendered FORM_READY can still
    be accepted, but an empty DOM never counts as zero results.
    """
    if not 1 <= len(routes) <= 2:
        raise ValueError("ROUTE_COUNT_MUST_BE_1_OR_2")
    if len({r.id for r in routes}) != len(routes) or not all(
        r.id.isidentifier() and len(r.id) <= 32 and is_allowed_search_url(r.url)
        for r in routes
    ):
        raise ValueError("UNSAFE_OR_DUPLICATE_SEARCH_ROUTE")
    if not 100 <= settle_wait_ms <= 5000 or not 1000 <= navigation_timeout_ms <= 60000:
        raise ValueError("UNSAFE_WAIT_LIMIT")

    observations: list[dict[str, Any]] = []
    for index, route in enumerate(routes):
        response_status = None
        timed_out = False
        try:
            response = await page.goto(
                route.url, wait_until="domcontentloaded", timeout=navigation_timeout_ms
            )
            response_status = response.status if response else None
        except Exception as exc:
            # Handle Playwright TimeoutError by type name for offline tests that
            # have no Playwright installed. Other exceptions are real failures.
            if type(exc).__name__ not in {"TimeoutError", "PlaywrightTimeoutError"}:
                observations.append({"route_id": route.id, "state": "UNKNOWN_LAYOUT",
                                     "reason_code": "NAVIGATION_EXCEPTION"})
                return RecoveryResult(False, "NAVIGATION_EXCEPTION", None, tuple(observations))
            timed_out = True

        # Prevent following a redirect to another host / private path.
        landed_url = getattr(page, "url", "")
        if landed_url and not is_allowed_search_url(landed_url):
            destination_class = classify_destination(landed_url)
            if is_benign_official_redirect(destination_class):
                # The portal may route to its own public home or a different
                # advanced-search URL. That DOM is NOT evidence of an accepted
                # form for the attempted route. One other *already-approved*
                # URL may be tried, but never loop or follow arbitrary links.
                observations.append({"route_id": route.id, "state": "UNKNOWN_LAYOUT",
                                     "reason_code": "OFFICIAL_REDIRECT_TO_OTHER_ROUTE",
                                     "destination_class": destination_class,
                                     "recommended_action": "TRY_NEXT_OFFICIAL_ROUTE"})
                continue
            observations.append({"route_id": route.id, "state": "ERROR_PAGE",
                                 "reason_code": "UNEXPECTED_NAVIGATION_DESTINATION",
                                 "destination_class": destination_class})
            return RecoveryResult(False, "UNEXPECTED_NAVIGATION_DESTINATION", None, tuple(observations))

        # A timed-out goto can leave the *previous route's* DOM visible.
        # Do not accept that stale form as proof of reaching this target.
        if timed_out and landed_url and landed_url != route.url:
            observations.append({"route_id": route.id, "state": "BLANK_OR_LOADING",
                                 "reason_code": "STALE_DOCUMENT_AFTER_TIMEOUT", "timed_out": True,
                                 "recommended_action": "TRY_NEXT_OFFICIAL_ROUTE"})
            continue

        observed = await _observe(page, status=response_status, timed_out=timed_out)
        state = observed["state"]
        if state == "BLANK_OR_LOADING":
            # One passive settle period, not another navigation or another click.
            await page.wait_for_timeout(settle_wait_ms)
            observed = await _observe(page, status=response_status, timed_out=timed_out)
            state = observed["state"]

        observations.append({
            "route_id": route.id,
            "state": state,
            "reason_code": observed["reason_code"],
            "http_status": response_status,
            "timed_out": timed_out,
            "recommended_action": navigation_decision(state, routes_remaining=index + 1 < len(routes)),
        })
        if state == "FORM_READY":
            return RecoveryResult(True, "SEARCH_FORM_CONFIRMED", route.id, tuple(observations))
        if state == "ERROR_PAGE":
            return RecoveryResult(False, "ACCESS_OR_PORTAL_ERROR", None, tuple(observations))
        if state == "UNKNOWN_LAYOUT":
            return RecoveryResult(False, "UNKNOWN_SEARCH_LAYOUT", None, tuple(observations))

    # At least one route served results but *not* the search form.
    reason = (
        "SEARCH_FORM_NOT_OBSERVED"
        if any(o["state"] == "RESULTS_VIEW" for o in observations)
        else "NAVIGATION_INCOMPLETE"
    )
    return RecoveryResult(False, reason, None, tuple(observations))