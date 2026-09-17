# Backlog

## Pending
- [ ] Frontend vitest suite fails entirely in this environment (`TypeError: Cannot read properties of undefined (reading 'clear')` on `localStorage` in `src/test/setup.ts`) — Node v26's experimental global Web Storage API conflicts with jsdom's own `localStorage`/`sessionStorage`. Confirmed unrelated to the upstream merge (affects unrelated pre-existing tests too, e.g. `date-utils.test.ts`). Workaround tried (`--no-experimental-webstorage`, `--localstorage-file`) did not fix it. Needs either pinning Node version for this project or a vitest/jsdom config fix (discovered 2026-09-17).

## Deferred Decisions

## Done (recent)
- [x] Merged upstream/main (28 commits, v0.16.0) into `atualizar-dependencias`, resolving 18 conflicts (15 locale files, credit-card-cycle.ts add/add, rule-dialog.tsx, workspace.py schema imports, connection_service.py payment-matching/installment-category integration, account-detail.tsx duplicate hook declarations) — completed 2026-09-17
