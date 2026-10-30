# Gate 1B-02 — Detail readiness hardening before the next live run

Date: 2026-10-30.

## Answer to the review

Before this patch, the detail reader navigated with wait_until="commit" and then waited up to 9 seconds for all of:
- document.body exists
- document.readyState != "loading"
- document.body.innerText has more than 30 trimmed characters.

It did **not** wait specifically for Catégorie principale or its labelled value. A PRADO view adding its detail fields asynchronously after the DOM parser finishes could therefore be read too early. Conversely a detail page without a `main` element is no longer treated as missing merely because that wrapper is absent.

## Implemented change (no live rerun)

- src/gate1b02_detail_readiness.py: after commit, wait at most 13 s for the page's HTML to be parsed (readyState interactive/complete and a nonempty body); then allow at most 5 s more for an explicit leaf category label before running the strict label/value parser.
- src/gate1b02_dom_evidence.py: uses this helper in the one-detail public spot check, keeps no-retry and safe-domain controls, distinguishes DETAIL_DOCUMENT_NOT_PARSED from READY_NO_EXPLICIT_LABEL.
- If a page title looks like login, maintenance or error and no explicit category label is visible, report DETAIL_POSSIBLE_ERROR_PAGE rather than treating it as a normal consultation.
- New diagnostic enums: ready_state, body_text_bucket, category_label_present, title_class and dom_html_bytes (bounded to 5 MB) with a capped flag.
- No raw HTML, title, page text, URLs, consultation IDs, PAGESTATE, request bodies, or cookies are sent to reports.

### Measurement caveats

- dom_html_bytes is the byte length of the browser's serialized **current DOM**, not the HTTP transfer body's byte count. A small DOM may be a minimal legitimate response, a login page, a blank shell, or a partial page; it **cannot prove chunked streaming failure or WAF throttling**.
- A successful commit means the navigation started loading, not that the body arrived. A readyState of interactive means the HTML parser finished, but PRADO/AJAX fields may be appended later.
- The observed GitHub-run fluctuations do not establish IP throttling or rate limiting; no WAF assertion is warranted from 200 with a non-ready DOM.
- One verified category on a detail is DIRECT_SPOT_CHECK_ONLY, not proof about all 1377 results, while an unlabelled detail remains UNCONFIRMED.

## Regression validation

- tests/test_gate1b02_detail_readiness.py checks two separate waits, missing labels, blank/unparsed DOM, redaction and timeout bounds.
- tests/gate1b02_readiness_browser_fixture.py drives local Chromium against delayed category insertion, login-like title and misleading object text.
- Workflow 52 runs the full unit suite and both local Chromium fixtures, without contacting marchespublics.gov.ma.
- No automatic live retry or timer is introduced.

Next live experiment, if separately triggered in a spaced low-frequency slot, is the existing **single** public search + **one** detail GET; preserve only sanitized JSON, and do not progress to 100/page until category evidence is sufficient.
