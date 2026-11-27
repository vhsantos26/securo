# Backlog

## Pending
- [ ] Harden `deploy-vps.yml`: the `workflow_run` trigger filters only by branch name, so a CI run from a fork PR whose branch is called `deploy` also reaches the job. Today the deploy stops at `git cat-file` on the VPS; add `github.event.workflow_run.event == 'push'` (discovered 2026-11-27).

## Deferred Decisions
- Drop the fork rename of the credit card accounting mode (`purchase_date`/`invoice_due_date`) and return to upstream's `cash`/`accrual`. Every sync brings code comparing against the old names (silent wrong branch), now caught by `backend/tests/test_fork_guards.py`. Needs a data migration and a UI label decision.
- Accounts page still computes shared credit line card totals with per-cycle summary queries, while the sidebar uses upstream's `open_bill_total`. Moving the page to the same field removes the divergence; needs a check that both numbers match what the bank shows.
- `sync-deploy.yml` publishes to production without review whenever upstream merges cleanly and backend tests pass. Consider opening a PR instead of pushing to `deploy`.

## Done (recent)
- [x] Merged upstream/main (453 commits, v0.17.0 to v0.23.0), 49 conflicting files. Renumbered upstream migrations to 108-140 and dropped upstream 120/121 (same schema as our 079/080). Pointed the new `migrate` and plugin services at the locally built image in `docker-compose.vps.yml`. Guarded upstream-only workflows (fast lane, fork run approval, stale queue). Adapted workspace Pluggy credentials to upstream's provider settings and instance secret key. Rehearsed the migrations on a copy of the production database (no row lost) and the compose deploy locally, completed 2026-11-27
- [x] Merged upstream/main (87 commits, v0.16.5 + v0.16.6) — 28 conflicts (17 locales via 3-way JSON merge, accounts API/service/schema, connection_service holdings flow keeping workspace-resolved Pluggy provider, sidebar now uses upstream's shared-card open bill instead of our cycle queries, dashboard, account-detail). Renumbered upstream migrations 097-101 to 103-107 (single head). Fixed `POST /connections/oauth/url` returning 500 when the workspace has no Pluggy configured (now 503). Regenerated API contract baseline for fork-only routes — completed 2026-10-28
- [x] Kept BrasilAPI institution lookup on for the fork via `docker-compose.vps.yml` (upstream v0.16.2 made it opt-in) — completed 2026-10-01
- [x] Frontend vitest failure traced to Node 26 (Web Storage vs jsdom); suite passes under Node 22 (CI). Added `frontend/.nvmrc` (22, matches CI and Docker). Note: on Node 24 one upstream test (`account-detail-running-balance`, chart axis) still fails, so use Node 22 locally — completed 2026-10-01
- [x] Merged upstream/main (19 commits, v0.16.2) — resolved 6 conflicts (pluggy provider/tests, connection_service display_name, sidebar balances in app-layout keeping our shared-card cycle totals, dashboard chips keeping zero-balance hiding, account-utils); renumbered upstream migration 096 -> 102 to keep a single alembic head — completed 2026-10-01
- [x] Merged upstream/main (28 commits, v0.16.0) into `atualizar-dependencias`, resolving 18 conflicts (15 locale files, credit-card-cycle.ts add/add, rule-dialog.tsx, workspace.py schema imports, connection_service.py payment-matching/installment-category integration, account-detail.tsx duplicate hook declarations) — completed 2026-09-17
