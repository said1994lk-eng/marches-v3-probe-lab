# Gate 1A-04 — Independent Fournitures category evidence

Scope: Public result-card category fields and up to 5 public tender detail pages. This is a bounded **evidence probe**, not a full collector.

## Engineering change

- `src/category_evidence.py`: examines result cards for *explicit* category fields (label/value pair, labelled inline field, explicit data-category attribute); ignores arbitrary title keywords. If missing, samples up to 5 public detail routes using an exact host/page allowlist. No raw text, URLs or HTML in emitted JSON.
- `src/filter_evidence_gate1a04.py`: fail-closed decision; refuses success based only on selecting Fournitures, HTTP 200, result counts, or title keywords. Accepts a **sample-supported** verdict only if 5 known matching categories were observed from source-labelled fields, the search update was observed, and no contradictory result exists. A hidden form after search does not automatically count as filter loss.
- `src/gate1a04_probe.py`: single opt-in probe (off without ENABLE_LIVE_GATE1A04=1), at most two official search routes and five public detail views, no pagination, DCE, login, database access or secrets.
- `tests/test_category_evidence.py` and `tests/test_gate1a04_probe.py`: offline source verification, URL restrictions and fail-closed behavior.

## Current evidence

Previous Run #40976378877, 2026-10-29:
- FORM_READY on the second official search route.
- Fournitures selected, but `retained_after_search=null` and no independent category proof.
- Correct result: `FILTER_EFFECT_UNCONFIRMED`.

This code tries to find explicit category source fields. It does **not** presume the fields exist.

## Tests and deployment

Local offline suite (prior tests plus new): **101 passed**. A local Chromium fixture checked labelled category detection, title-keyword rejection, conflicting categories, and main-content-only detail extraction.

```sh
python -m unittest discover -s tests -q
python tests/browser_fixture_check.py  # optional local Chromium fixture
```

The offline suite does not connect to the portal. Browser fixture requires Chromium.

## Safety

- `ENABLE_LIVE_GATE1A04` must be exactly `1` to make a real request.
- Public search form (2 routes maximum), followed by up to 5 public details only when the cards lack an explicit category.
- Does not download documents or interact with submission workflows.
- Does not store full URLs, raw HTML, titles, cookies, form values, or PII in public reports.
- `SAMPLED_CONFIRMED` is **not** `VERIFIED_COMPLETE`. It cannot establish full portal coverage or prove every result's category.
- Missing/ambiguous category evidence remains `UNCONFIRMED`.
- Workflow #40 is not modified or repeated. No change to V3.2.

## Next gate

After observing the actual Gate 1A-04 result, either refine the explicit field extractor against real (sanitized) structural evidence or move to Gate 1A-05 page-size 100 attestation if independent category evidence succeeds. Only schedule another live probe for a specific new hypothesis, never blind retries.
