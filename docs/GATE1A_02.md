# Gate 1A-02 — Navigation Recovery and Fournitures Filter Attestation

Status: **offline implementation delivered; real portal behavior NOT verified.**

## Files

- src/navigation_recovery.py — bounded two-route search-form recovery; uses src/page_state.py.
- src/filter_attestation.py — independently checks source-labelled result categories; refuses unsupported success.
- tests/test_navigation_recovery.py — offline navigation tests including Run #40904566211 reclassification.
- tests/test_filter_attestation.py — offline filter-evidence tests.

## What changed and what did not

- Existing V3.2 and all workflows remain unchanged. No automatic integration, GitHub Actions dispatch, live request, database connection, Secrets, or DCE operations.
- New navigation worker can make at most two allowlisted public-search-route navigations when separately called by a future integration. It refuses external redirect destinations and never retries clicks blindly.
- A navigation timeout may leave stale DOM; the new worker detects a stale route when the browser URL differs.
- A results-only page is NOT accepted as a ready advanced-search form.
- A selected Fournitures dropdown, postback success, HTTP 200 or reduced count does NOT prove server-side filtering.
- Even after selecting Fournitures and submitting a search, select_fournitures_and_observe returns UNCONFIRMED until results provide independently verified category evidence.
- The DOM helper observe_categories_in_cards exists for future use, but a category CSS selector must be established from trusted live public source evidence before that evidence can be marked trusted. No selector is guessed.

## Local test command

    python -m unittest discover -s tests -v

Python standard library only for tests. Tests use stub browser pages, not the public website.

New Gate 1A-02 tests: 36 tests passed in isolated local run. GitHub-hosted CI has not been executed for this change.

## Acceptance criteria still open

1. Locate a real, official advanced-search form reliably using a bounded live test.
2. Validate a real category label on result cards or details; do not trust category text solely from a dropdown.
3. Confirm filter effect using actual results; maintain UNKNOWN / UNCONFIRMED when evidence is missing.
4. Establish safe integration into V3.2 behind a read-only bounded test, with an independent report verifier.
5. After Gate 1A succeeds, validate 100 rows/page and pagination under separate evidence gates.

## Evidence reference

Prior read-only Run (no new run was triggered):
https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/40904566211

This run showed Route A as RESULTS_VIEW (10 cards, no category form), Route B timed out while loading.
It does not prove Fournitures selection, 100/page, or coverage.
