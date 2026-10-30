"""Sanitized classification of public portal navigation landing destinations.

Never export a full URL or query field. This is *diagnostic*, not a bypass.
Only exact known, publicly oriented official routes are classified as safe to
attempt a different approved search URL once; auth walls always stop.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlparse

HOST = 'www.marchespublics.gov.ma'
SEARCH_PAGE = 'entreprise.EntrepriseAdvancedSearch'
HOME_PAGE = 'entreprise.EntrepriseHome'


def classify_destination(url: str) -> str:
    """Return a low-information code; no raw URL/path/query in output."""
    if not isinstance(url, str) or not url.strip():
        return 'UNKNOWN_DESTINATION'
    # Chromium can remain at about:blank if goto timed out before commit.
    # It is not an external destination and must never count as portal content.
    if url.strip().lower() == 'about:blank':
        return 'BROWSER_BLANK_DOCUMENT'
    if url.strip().lower().startswith('chrome-error://'):
        return 'BROWSER_ERROR_DOCUMENT'
    try:
        u = urlparse(url)
        if (u.scheme != 'https' or u.hostname != HOST or
                u.username or u.password or u.port not in (None,443) or u.fragment):
            return 'UNTRUSTED_DESTINATION'
        if u.path not in ('/', '/index.php'):
            return 'UNRECOGNIZED_OFFICIAL_PATH'
        params = parse_qs(u.query)
        pages = params.get('page', [])
        if len(pages) != 1:
            return 'OFFICIAL_HOME_OR_LANDING' if not pages and not params else 'UNRECOGNIZED_OFFICIAL_QUERY'
        p = pages[0]
        if p == HOME_PAGE:
            return 'OFFICIAL_HOME_OR_LANDING'
        if p == SEARCH_PAGE:
            return 'OFFICIAL_ADVANCED_SEARCH_ROUTE'
        if any(w in p.lower() for w in ('auth', 'login', 'connect', 'captcha', 'identif')):
            return 'OFFICIAL_AUTH_WALL'
        return 'UNRECOGNIZED_OFFICIAL_PAGE'
    except (TypeError, ValueError):
        return 'UNKNOWN_DESTINATION'


def is_benign_official_redirect(code: str) -> bool:
    """Permits *only* trying the second pre-approved route; no form acceptance."""
    return code in {'OFFICIAL_HOME_OR_LANDING', 'OFFICIAL_ADVANCED_SEARCH_ROUTE'}