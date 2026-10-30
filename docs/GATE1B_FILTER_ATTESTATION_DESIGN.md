# Gate 1B — PRADO-aware Fournitures filter attestation

Status: implemented as a **standalone, disabled-by-default, evidence-only probe**. It is not yet integrated into the full-coverage collector.

## Why this implementation differs from an expect_navigation-only recipe

Official Playwright Python docs mark page.expect_navigation as deprecated/racy and recommend URL/response/assertion-based synchronization. More importantly, PRADO's search action may be an AJAX request (XHR/fetch) without a main-frame navigation. Waiting solely for page navigation to commit would then time out despite a successful AJAX request.

Reference documentation:
- https://playwright.dev/python/docs/api/class-page
- https://playwright.dev/python/docs/api/class-locator

The proven initial navigation still uses wait_until="commit" via src/navigation_recovery.py. **The search button** has a separate response observer for an official-host POST of type xhr/fetch/document, with exactly one click and no automatic re-click.

## Three stages

0. FORM_HYDRATED: source category selector, search button and a nonempty hidden PRADO_PAGESTATE input must exist in DOM. This is a conservative hypothesis to verify live, not a claim that the portal always uses the exact input name. If missing, we stop without clicking.
1. SELECTED: choose exact "Fournitures", then require selection and PAGESTATE to remain stable for 700 ms while no same-host XHR/fetch is pending. If callback never settles, stop before the search click. Never log PAGESTATE, raw query strings, form values or request bodies.
2. APPLIED (technical candidate): observe a same-host public search POST with HTTP status 200; recognize whether it is AJAX_POST or DOCUMENT_POST; require a public results marker and either a changed PAGESTATE or an independently observed results transition. POST 200 or PAGESTATE change alone is NOT enough to prove Fournitures.
3. CONFIRMED_BY_RESULTS_SAMPLE: independently inspect up to five first-page result cards, using explicit source-labelled category fields (with bounded public detail fallback). A keyword inside title/object is not a valid category. All required sample rows must be expressly Fournitures and there must be no explicit Travaux/Services contradiction.

**Never claim full-portal filter proof from five cards.** The strongest positive status is SAMPLED_CONFIRMED, which means only a correctly source-labelled first-page sample.

## Diagnostic matrix

| State/code | Meaning |
|---|---|
| FORM_HYDRATION_NOT_PROVEN | Required PRADO form controls/state not observed; no click |
| PRADO_CALLBACK_NOT_SETTLED | Category option selected but form callback/state did not settle; no click |
| SEARCH_CLICK_NOT_CONFIRMED_NO_RETRY | Action failure; click may have happened; do not retry blindly |
| SEARCH_POST_NOT_OBSERVED | No recognized same-host POST response; this does not prove server outage |
| SEARCH_POST_HTTP_NOT_200 | Response was observed but not HTTP 200 |
| RESULTS_DOM_NOT_READY | POST responded but no usable results DOM |
| POSTBACK_EFFECT_NOT_OBSERVED | HTTP 200 and results markers, but cannot attribute the current results to the submitted search |
| SOURCE_CATEGORY_SAMPLE_INCOMPLETE | Missing, unknown or insufficient explicit source category labels |
| NON_FOURNITURES_CATEGORY_OBSERVED | An independent source-labelled sample contains Travaux/Services |
| SOURCE_LABELLED_FOURNITURES_SAMPLE | Independent source-labelled Fournitures sample only; NOT all tenders |

## Guardrails and limitations

- At most two pre-approved public navigation URLs, one search button click, and five public detail pages. No uncontrolled retries.
- No credentials, portal login, CAPTCHA, proxy rotation, Neon, DCE downloads, tender content storage or bulk pagination.
- A zero-results page is UNCONFIRMED rather than full proof.
- A generic form count or 200 response does not prove the advanced-search form exists.
- PAGESTATE contents never appear in logs or artifacts.
- If the portal exposes no hidden PRADO_PAGESTATE input or uses a different callback shape, Gate 1B fails closed; follow with public DOM evidence before changing the selector.
- src/reliability_v32.py and all legacy full-coverage workflows remain untouched.
- The live entrypoint src/gate1b_probe.py is OFF unless ENABLE_LIVE_GATE1B=1 is explicitly set.

## Tests

Run from repository root:

    python -m unittest discover -s tests -q
    python -m py_compile src/gate1b_attestation.py src/gate1b_probe.py

The unit suite includes pure policy checks, simulated AJAX one-click completion, missing hydration, cross-origin POST rejection, and no raw PRADO state in the reports.
