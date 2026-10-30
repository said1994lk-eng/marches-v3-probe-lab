# Gate 1B-02 — One public detail category spot-check

Date: 2026-10-30

## Starting evidence (actual prior artifact)

Run: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/41128376880
Artifact: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/41128376880/artifacts/13012116342

The artifact contains ONE JSON report (gate1b-report.json), with no HTML, DOM tree, screenshot, or card attribute dump. Thus we cannot infer whether an icon alt/title contains an official category.

Prior evidence: FORM_READY, Fournitures SELECTED, DOCUMENT_POST HTTP 200, PAGESTATE changed, results transitioned, displayed total 1377, five cards sampled, zero source-labelled category matches, zero source-labelled contradictions, five unclassified, final UNCONFIRMED.

## Evidence hierarchy

1. Analyze 5 card DOM elements for title, alt, aria-label, and data-* category values using in-browser JS. Publish only fixed-enum categories and attribute types, never raw HTML or arbitrary text. These are ATTRIBUTE_CANDIDATES_ONLY, not certified source fields.
2. Record whether Fournitures is selected after POST, and whether the selected option has a selected markup attribute. This supports understanding form state; retained client selection is NOT proof of server-side correct filter.
3. Follow at most one directly observed, allowlisted public consultation detail URL, with wait_until=commit. Accept known public detail route variants only. Test for associated official category labels and values. The portal may not publish these labels; do not assert that it does until observed.
4. If first detail is explicitly Fournitures, report DIRECT_SPOT_CHECK_ONLY: one inspected consultation record, not all 1377 and not full-filter proof. If expressly Travaux/Services, report CONTRADICTED_SPOT_CHECK: that one record contradicts the requested filter. If neither, UNCONFIRMED.
5. Do not execute Travaux differential at this gate. Non-overlap of the first five IDs does NOT prove disjoint whole result sets; report DIFFERENTIAL_SUPPORT_ONLY at most. Different totals are not proof of category correctness.

## Files and limits

- src/gate1b02_dom_evidence.py: DOM attributes, sanitization, allowed detail URLs, one GET, bounded decision.
- src/gate1b02_probe.py: commit-first official navigator plus previous Gate 1B one-click POST, with no implicit detail pages, then one separate detail GET.
- src/gate1b_attestation.py: max_detail_pages=0 avoids reopening five details during this new diagnostic.
- tests/test_gate1b02_dom_evidence.py: offline tests.

One read-only search session, two allowlisted official navigation routes maximum, one explicit search click, one public detail GET maximum, no credentials, DCE, downloads, login, proxy, CAPTCHA bypass, Neon or pagination. URL, page HTML, PAGESTATE, refConsultation identifiers and raw title text must never be published.

Only a first-page sample with sufficient explicit, trustworthy category labels can become SAMPLED_CONFIRMED. A single detail can never prove all results or full coverage; all_results_verified remains false in this gate.

The probe is disabled unless ENABLE_LIVE_GATE1B02=1. It must pass offline tests before any one-shot live workflow.
