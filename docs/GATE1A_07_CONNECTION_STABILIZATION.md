# Gate 1A-07 — Public portal connectivity improvement

Date: 2026-10-30 (UTC)
Target: official Moroccan public procurement search on www.marchespublics.gov.ma.
Scope: public-only navigation and network evidence; NOT a full tender collector.

## Change made on main

1. src/connectivity_gate1a07.py is a new opt-in diagnostic gate that:
   - checks DNS, standard verified TLS and one non-following HTTP GET to the official advanced-search path;
   - checks the same network baseline against an unrelated known-good control (github.com);
   - tests up to two official browser GET navigation routes, waiting for document commit then public DOM readiness;
   - exports only status codes, sanitized failure classes, public page-state enums and aggregate times, not IPs/URL strings/headers/cookies/body.
2. tests/test_connectivity_gate1a07.py verifies fail-closed classifications, host/path allowlists, no implicit live requests, and avoids treating generic HTTP 200 as source readiness.
3. src/navigation_recovery.py now uses wait_until="commit" rather than wait_until="domcontentloaded", followed by a bounded wait for official public DOM markers, before deciding FORM_READY/RESULTS_VIEW/etc.
4. tests/test_commit_connection.py verifies the shared navigation module cannot accept a document commit alone as evidence of search-form readiness.
5. src/gate1a07_navigation_canary.py checks that exact shared navigation module separately (no POST, filters, pagination or DCE).

## Two verified real GitHub runs

### 1) Layered diagnosis — PASS

Run: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/41125587771
Workflow: 44 - Gate 1A-07 Connectivity Layers (one bounded run)
JSON artifact: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/41125587771

Results from the workflow's actual JSON:
- portal.dns = RESOLVED
- portal.tcp_tls = VERIFIED
- portal.http = RESPONSE_RECEIVED, http_status=302 (no follow)
- control.dns = RESOLVED; control.tcp_tls=VERIFIED; control.http_status=200
- Chromium primary: DOCUMENT_COMMITTED, HTTP 200, RESULTS_VIEW, 7238 ms
- Chromium secondary: DOCUMENT_COMMITTED, HTTP 200, FORM_READY, 1804 ms
- status = SEARCH_FORM_REACHABLE_ONCE
- GitHub unit regressions: 129 tests passed

### 2) Shared navigation module canary — PASS

Run: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/41125924774
Workflow: 45 - Live Navigation Commit Canary (one bounded run)

Results from the actual JSON:
- navigation.form_ready = true
- navigation.reason_code = SEARCH_FORM_CONFIRMED
- navigation.route_id = secondary
- primary = RESULTS_VIEW / HTTP 200 / no timeout
- secondary = FORM_READY / HTTP 200 / no timeout
- status = FORM_READY_CONFIRMED_ONCE
- GitHub unit regressions: 132 tests passed

## Important limitation

Two successful runs minutes apart establish that the GitHub runner CAN reach the official form, and the new navigation module works on the tested route. They do NOT prove 24/7 availability, a minimum success percentage or an absence of future timeouts.

A Python HTTP 302 is not by itself failure. The independent Chromium checks confirmed an actual FORM_READY on the official search URL. Do not claim that changing the wait milestone fixed the underlying network for all time.

Nothing in these tests selected or validated a Fournitures filter. It remains unconfirmed. No coverage, 100-per-page claim or tenders were collected; no DB writes, DCE download or account authentication.

## Operational recommendation

- Keep the old src/reliability_v32.py full-coverage collector unchanged until independent Fournitures category evidence is available.
- Run a small number of spaced, low-frequency manual/controlled navigation canaries over different periods. Count actual FORM_READY outcomes; never interpret missing source as zero notices.
- If accessibility later varies, compare portal DNS/TLS/HTTP against the control and sanitized Chromium request failures. Avoid speculative IP-block or WAF claims.
- If GitHub connectivity remains genuinely intermittent across a reasonable set of samples, test one authorized stable host/runner before spending money on a VPS. Switching IP or hosting is not a guaranteed fix.
- Next development gate is independent proof of the Fournitures category on the results/details, followed by bounded 100-per-page and pagination tests.
