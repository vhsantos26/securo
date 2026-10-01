# Backlog

## Pending

## Deferred Decisions

## Done (recent)
- [x] Kept BrasilAPI institution lookup on for the fork via `docker-compose.vps.yml` (upstream v0.16.2 made it opt-in) — completed 2026-10-01
- [x] Frontend vitest failure traced to Node 26 (Web Storage vs jsdom); suite passes under Node 22/24. Added `frontend/.nvmrc` (22, matches CI and Docker) — completed 2026-10-01
- [x] Merged upstream/main (19 commits, v0.16.2) — resolved 6 conflicts (pluggy provider/tests, connection_service display_name, sidebar balances in app-layout keeping our shared-card cycle totals, dashboard chips keeping zero-balance hiding, account-utils); renumbered upstream migration 096 -> 102 to keep a single alembic head — completed 2026-10-01
- [x] Merged upstream/main (28 commits, v0.16.0) into `atualizar-dependencias`, resolving 18 conflicts (15 locale files, credit-card-cycle.ts add/add, rule-dialog.tsx, workspace.py schema imports, connection_service.py payment-matching/installment-category integration, account-detail.tsx duplicate hook declarations) — completed 2026-09-17
