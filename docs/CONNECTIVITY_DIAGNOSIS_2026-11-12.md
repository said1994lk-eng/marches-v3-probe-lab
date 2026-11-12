# Marchés Intelligence V3 — 12 Nov 2026 official connectivity diagnosis

**Scope:** one bounded search/filter gate and one separate bounded homepage GET from GitHub-hosted Chromium. No bulk scraping, accounts, DCE or DB.

## Evidence from real GitHub Actions

### Run 59 — Exact official public search route

GitHub Actions: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/43267252895
Artifact: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/43267252895/artifacts/13965993382

- **240/240 offline Python tests PASS**.
- GitHub Chromium reached response **HTTP 888** on the previously verified exact official public search route (one GET).
- Reason: `NAVIGATION_NOT_CONFIRMED`, `ACCESS_OR_PORTAL_ERROR`; `ERROR_PAGE`, `HTTP_ERROR`.
- No fallback was attempted after non-200 access/portal error.
- No FORM_READY, no Fournitures selection, no search postback, no detail GET.
- No 100/page, pagination, Neon, DCE or downloads.

### Run 60 — Official /pmmp/ homepage, isolated

GitHub Actions: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/43267773877
Artifact: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/43267773877/artifacts/13965284583

- **240/240 offline Python tests PASS**.
- Exactly one Chromium GET to `https://www.marchespublics.gov.ma/pmmp/?lang=fr&page=plan`.
- `document_committed=true`, **HTTP 888**, status `HOMEPAGE_HTTP_NON_200`.
- No DOM readiness declared or public links inspected; no navigation retries.
- No POST, category search, details, pagination, DB or downloads.

## External source context (not runner proof)

The TGR notice on the official public PMMP site announced reactivation on 9 November, procedures resuming on 10 November, and public daily access from 07:30 until midnight, following security-related downtime. A contemporary report described a remodeled interface after reopening.

- https://www.marchespublics.gov.ma/pmmp/?lang=fr&page=plan
- https://medias24.com/2026/11/09/portail-des-marches-publics-la-tgr-reactive-la-plateforme-et-reamenage-les-delais-1788945

These sources show the public portal is intended to be available, but do NOT prove that a GitHub-hosted Chromium runner can reach it. The 9 November official direct search canary DID reach FORM_READY once: https://github.com/said1994lk-eng/marches-v3-probe-lab/actions/runs/42723203468

## Engineering interpretation (do not overstate)

- The two real probes show that on 12 Nov, **both** the exact legacy search entry and the current public PMMP homepage returned the same unusual **HTTP 888** to GitHub-hosted Chromium.
- 888 is not a standard HTTP status. The evidence does NOT identify which server/gateway/proxy/security rule generated it.
- It is incorrect to conclude the portal is globally down, the current public URL is invalid, the user's normal browser cannot connect, the bot's PRADO filter is broken, or a WAF/IP ban is proven.
- A new portal design may need selector adaptation, but no such claim can be made before an actual live DOM is observed.
- Existing category evidence remains UNCONFIRMED. The strongest old POST candidate was a 30 October HTTP 200 DOCUMENT_POST and displayed 1377 results, but five first-page records lacked independently source-labelled category.
- Newest code compiles and 240 offline regressions pass; production readiness and category coverage are not established.

## Next controlled diagnostic

1. Do NOT repeat identical GitHub-hosted requests rapidly or switch IPs to evade access policies.
2. Compare an authorized normal browser/connection from the user's own environment (where the portal reportedly works) with an authenticated **none** read-only request to the official public homepage. Record only safe status, timing and sanitized DOM flags.
3. If genuinely necessary, compare transport-level DNS/TLS/HTTP response with one unrelated known-good control from GitHub while never logging cookies, sensitive response bodies, credentials or network tokens.
4. If the public site does not permit automated access from GitHub cloud hosts, seek the official public interface/API or explicit permission for an appropriate runner.
5. Once a genuinely accessible environment reliably reaches FORM_READY, perform at most one Fournitures search and one public consultation detail; a single labelled record supports DIRECT_SPOT_CHECK_ONLY, not all-result coverage. Five independently labelled records are needed to make a first-page sample claim.
6. Defer 100/page, pagination, DCE, Neon and scheduled production jobs until the above source evidence is confirmed.

No cron/automation or repeated live attempts were created after the two bounded diagnostic runs.
