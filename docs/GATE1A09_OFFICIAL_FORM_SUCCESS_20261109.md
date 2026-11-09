# Gate 1A-09 — Marchés V3 public search connection confirmed on 9 Nov 2026

## Source-grounded fix

The actual official "Consultations en cours" link on the public portal leads to:
`https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch&searchAnnCons=`

This exact public query differs from the guessed advanced-search URLs used by prior gates. It was independently observed through the official home page link; this alone did not attest any Fournitures category.

The canary `src/gate1a09_exact_public_search.py` now uses this route FIRST with `wait_until="commit"`, bounded DOM observation, and one older preapproved fallback at most.

## Verified live GitHub evidence — SUCCESS

Live workflow: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/42723203468
Official sanitized artifact: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/42723203468/artifacts/13720968597
Date: 2026-11-09 UTC.

Exact original JSON:
- status: **FORM_READY_CONFIRMED_ONCE**
- form_reachable: **true**
- public_link_form_reachable: **true**
- route_id: **official_menu_exact**
- navigation reason_code: **SEARCH_FORM_CONFIRMED**
- first route page state: **FORM_READY**
- first route reason_code: **CATEGORY_CONTROL_PRESENT**
- first route HTTP status: **200**
- first route timed_out: **false**
- no fallback route required
- 239/239 offline Python regressions passed before the network check
- no filter attestation, pagination, DB writes or DCE downloads

This confirms that the new route actually rendered the advanced-search form in one real GitHub-hosted Chromium run. **One success does not establish 24/7 reliability, and reaching the form is not evidence of properly filtered Fournitures results.**

## Integration now applied

- `src/gate1b_probe.py` uses the exact route pair from `gate1a09_exact_public_search.ROUTES`.
- `src/gate1b02_probe.py` uses the same pair.
- Both now allow a 35-second bounded commit-first navigation; do not submit a search if FORM_READY is not actually confirmed.
- `tests/test_gate1a09_exact_public_search.py` verifies both subsequent gates import the verified route rather than drifting back to guessed query strings.
- Offline GitHub integration run: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/42723512862 — **SUCCESS, 240/240 Python tests**.
- A separate `58-gate1b02-verified-link-manual.yml` workflow was added for controlled manual-only Fournitures selection + one public detail. It was **not launched**, so category proof remains unconfirmed.

## Other diagnostic findings (do not confuse with this success)

- Earlier home-menu canaries succeeded in loading the public home page HTTP 200 but sometimes couldn't navigate from the visible consultations link.
- The GitHub runner on ubuntu26.04 couldn't install Playwright's Chromium with `--with-deps`; the successful canary pins `ubuntu-24.04` and runs `python -m playwright install chromium`.
- Those earlier failures do NOT prove permanent portal downtime, IP throttling or blocking. They also don't negate the official direct-search success.

## Next gate and safeguards

Gate 1B-02 (manual): select Fournitures with PRADO state observation, submit **one** public search action, inspect at most **one** public consultation detail, and only accept a source-labelled category as proof for that individual record. Keep absent categories UNCONFIRMED. Do not start 100/page, bulk pagination, DCE, Neon or automated daily scanning without separate validated evidence.

The exact public search URL is now the baseline entrypoint for V3. There is no guaranteed availability SLA and no automated repeated reconnect loop.
