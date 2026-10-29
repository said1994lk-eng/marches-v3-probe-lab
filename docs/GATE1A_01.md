# Gate 1A-01 — Read-only Page State Classifier

Status: **code added to GitHub; offline component tested; no live portal run in this change**.

## Scope

The new source file src/page_state.py classifies public pages using sanitized DOM signals. It does not establish that Fournitures was applied, that 100 rows/page works, or that pagination/coverage succeeded.

Recognized states:
- FORM_READY: identifiable category control exists.
- RESULTS_VIEW: result cards or result-count label, but advanced-search form not confirmed.
- ERROR_PAGE: HTTP error, access challenge, or observed portal error.
- BLANK_OR_LOADING: unfinished page, possibly following navigation timeout.
- UNKNOWN_LAYOUT: insufficient or unrecognized evidence.

The recommended next_action is advisory only. This change does NOT alter existing V3.2 navigation.

## Evidence from real Run #40904566211

https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/40904566211

The run ended SOURCE_UNAVAILABLE.
- Route 1: 10 tender cards, count label, no category control => RESULTS_VIEW.
- Route 2: DOM still loading, no visible content after navigation timeout => BLANK_OR_LOADING.

These are offline reclassifications of existing evidence; not a new portal test.

## Offline tests

From repository root:

    python -m unittest discover -s tests -v
    python -m py_compile src/page_state.py tools/apply_v32_integration.py

No external network, browser, Neon, or DCE are needed.

## Diagnostic-only integration preview

Generate a separate file with observational classification added:

    python tools/apply_v32_integration.py src/reliability_v32.py src/reliability_v32_gate1a_preview.py
    python -m py_compile src/reliability_v32_gate1a_preview.py

The original V3.2 remains unchanged. The preview adds diagnostic fields but keeps navigation, filtering, retry and exit logic unchanged. Do not run it on the official portal without authorizing a bounded live test.

## Safety

- No cookies, form values, credentials, raw HTML, or full URLs are returned from the DOM collector.
- No CAPTCHA or authentication bypass.
- No Neon writes, DCE processing or workflow dispatch.
- Existing .github/workflows/30-source-reliability.yml was not changed.

## Gate 1A-02 — Not implemented yet

Design a bounded navigation decision policy; separate FORM_READY from RESULTS_VIEW routing; independently attest that Fournitures is really applied before collection. Test against offline fixtures first.
