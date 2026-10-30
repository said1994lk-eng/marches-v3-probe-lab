# Gate 1B-02 — Actual DOM/discovery evidence and remaining uncertainty

Date: 2026-10-30 UTC.

## Original Gate 1B artifact

Run: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/41128376880
Artifact: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/41128376880/artifacts/13012116342

The artifact holds exactly one JSON file. It has NO raw HTML, no <tr> or <div> tree, no screenshot, and no raw element attributes. Its 1377 displayed count and 5 unclassified cards DO NOT prove that the filter is correct.

## Gate 1B-02 first public inspection

Run: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/41129830129
Artifact: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/41129830129/artifacts/13012621704
Conclusion: FAILURE due to category evidence being absent; unit tests 191/191 PASS and offline Chromium fixture PASS.

Verified sanitized report:
- Navigation = SEARCH_FORM_CONFIRMED on the official secondary route.
- Fournitures SELECTED, DOCUMENT_POST HTTP 200, PAGESTATE changed, results transitioned.
- Official count displayed = 1377, sampled cards = 5, all five unclassified.
- All five result cards use DIV (NOT TR).
- Five sampled cards expose no *exact category attribute candidates* in alt, title, aria-label or named data-* attributes. No claim about all other cards.
- Five links point to the allowlisted PLURAL public detail route: EntrepriseDetailsConsultation.
- The post-search form category control was no longer present; selected markup/DOM state could not be observed. Do not infer the server retained or lost the filter from this.
- Exactly ONE public detail GET was attempted, HTTP 200, but the old detail parser's required #ctl0_CONTENU_PAGE/main root was not observed. Reported DETAIL_BODY_NOT_READY. Actual official category label UNKNOWN.
- No page-size claim, pagination, Neon, DCE, or downloads.

## Targeted parser correction

The old parser assumed a specific DOM wrapper for public details. A corrected parser:
- Uses a short, bounded body-readiness check, not a hard-coded main wrapper.
- Searches for an **explicit** associated detail-page field such as Catégorie principale: Fournitures, or a nested TH/TD label/value association.
- Rejects category keywords in title, object and input/dropdown controls.
- Emits only category enums, proof source and safe diagnostic states; no raw HTML, query strings, raw URLs, PAGESTATE or IDs.
- Continues to regard one verified detail as DIRECT_SPOT_CHECK_ONLY, never proof of all rows.

Files: src/gate1b02_detail_parser.py; src/gate1b02_dom_evidence.py; tests/test_gate1b02_detail_parser.py; tests/gate1b02_browser_fixture.py.

Offline validation run: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/41130179681
Result: SUCCESS, 196/196 Python unit tests PASS + Chromium local DOM fixture PASS.

## Gate 1B-02 second public attempt, after parser correction

Run: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/41130316799
Artifact: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/41130316799/artifacts/13012512969
Conclusion: FAILURE (safe stop).

Actual JSON:
- Offline 196 tests and Chromium fixture: PASS.
- Both official search routes returned HTTP 200 with no navigation timeout but never exposed a usable public search/results DOM.
- Primary and secondary both BLANK_OR_LOADING / DOCUMENT_EMPTY_OR_LOADING.
- No FORM_READY; no search click; no POST; no detail GET. Detail parser was therefore NOT exercised against the live site after the correction.
- No evidence of the Fournitures filter or official category label.
- No pagination, 100/page verification, downloads or database writes.

## Mathematical caution — differential comparison

Comparing the first five Fournitures consultation IDs against the first five Travaux IDs and observing empty intersection is at most DIFFERENTIAL_SUPPORT_ONLY. It is NOT proof that the whole sets are disjoint; different published totals also do not establish full category correctness. One category-labelled detail proves only that one record.

## Engineering decision

Current gate remains UNCONFIRMED. The network can sometimes commit an HTTP 200 without an effectively rendered DOM; do not treat it as a successful search and do not repeatedly retry identical live checks. Preserve the evidence and reuse the corrected parser in a later LOW-FREQUENCY, single bounded live test when the portal is observed to render FORM_READY.

No new run is scheduled or executed automatically, and no changes are made to legacy V3.2, full coverage collection, Neon or DCE.
