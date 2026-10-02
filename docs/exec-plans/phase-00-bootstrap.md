# Phase 00 — Repository Bootstrap

## Goal
Create runnable empty frontend/backend foundations and developer tooling.

## Model
gpt-6-luna medium OR gpt-6.1-sol medium.

## Deliverables
- frontend Vue 3 + TS + Vite
- backend FastAPI package
- `/api/v1/health`
- pytest setup
- Vitest setup
- data directories
- README local setup
- `.env` loading
- basic Dockerfiles may be prepared, but Docker is not required to be the only dev path

## Non-goals
No downloader, database business schema, Google Drive, editor, batch.

## Tests
- backend health test
- frontend smoke test
- build/typecheck

## Acceptance
- [x] PASS: backend starts — Uvicorn startup completed; live health returned HTTP 200.
- [x] PASS: frontend starts — Vite served the application and Vue module with HTTP 200.
- [x] PASS: frontend can display API health in development — live Vite proxy returned
  `{"status":"ok"}`; routed application smoke test rendered `Backend reachable`.
- [x] PASS: tests pass — 6 backend tests and 7 frontend tests; typecheck, Ruff, and build pass.

## Relevant docs
- `AGENTS.md`
- `.agent/PLANS.md`
- `docs/product-spec.md`
- `docs/architecture.md`
- `docs/api-contract.md` (health route prefix)

## Current state assumptions
The starting repository contained documentation, setup scripts, and empty data
directories, with no frontend or backend code. Git was clean on `main`.
Implementation uses the branch `phase/00-bootstrap`.

## Implementation steps
1. Add an installable Python package, minimal settings, and a versioned health route.
2. Verify backend imports, health behavior, configuration, and lint.
3. Add the Vue shell, router, Pinia health state, and development API proxy.
4. Verify frontend health success/failure behavior, typecheck, and build.
5. Exercise both running development servers and review the final diff.

## Data/API changes
No database changes. `GET /api/v1/health` returns HTTP 200 with `{"status":"ok"}`.
This reports API reachability only; no future service readiness checks are implied.

## Decisions
- Use FastAPI, Pydantic Settings, and Uvicorn only for backend runtime dependencies.
- Keep Python configuration in `backend/pyproject.toml` and an editable local package.
- Root `.env` supplies host, port, and environment; unused future settings are ignored.
- Use a Vite development proxy rather than adding CORS configuration in Phase 00.
- Put health response types in the frontend shared types layer and state in Pinia.
- Health requests have a five-second timeout and explicit unreachable/retry behavior.
- Use pytest/HTTPX, Ruff, Vitest, Vue Test Utils, and jsdom for local verification.
- Pin TypeScript to 5.9 because TypeScript 7 is incompatible with the installed
  `vue-tsc`. Use Vue Test Utils 2.4 and jsdom 26 to support the available Node 25
  without the newer test utilities' transitive Node engine exclusions.
- Use the existing data directories; do not add speculative backend modules or Docker.

## Rollback/recovery
All bootstrap changes are isolated on the phase branch. Dependencies and build
outputs are ignored. Stop the development servers before switching branches.

## Deferred work
Phase 01 backend foundation; database models/migrations; downloader/adapters;
queue/worker; library/history/dedup; local/Drive storage services; editing and
batch workflows; production hosting/API routing; Python dependency locking.

## Verification record
Completed on 2026-10-02 using Python 3.12.9, Node 25.2.1, and npm 11.2.0.

- `python -m venv .venv`: PASS.
- `.venv/Scripts/python.exe -m pip install -e './backend[dev]'`: PASS.
- Backend `python -c 'from app.main import app; print(app.title)'`: PASS (`VideoVault`).
- Backend `python -m pip check`: PASS.
- Backend `python -m pytest`: PASS, 6 tests, including versioned health and settings failures.
- Backend `python -m ruff check .`: PASS.
- Backend `python -m ruff format --check .`: PASS, 11 files formatted.
- Frontend `npm install` and `npm ci`: PASS; audit reported zero vulnerabilities.
- Frontend `npm run typecheck`: PASS after the TypeScript compatibility fix.
- Frontend `npm test`: PASS, 7 tests, including routed shell and health failure/retry paths.
- Frontend `npm run build`: PASS, 28 modules transformed.
- Backend `python -m app.main`: PASS, application startup completed.
- Frontend `npm run dev`: PASS, Vite ready on port 5173.
- Live HTTP checks: backend health, frontend root, Vue module, and proxied health PASS.
- `git diff --check`, status/diff review, and ignored-file checks: PASS.

Initial verification ran before pip finished and was rerun after installation.
The initial TypeScript check failed due to a package export incompatibility;
pinning TypeScript 5.9 fixed it. An overlapping dependency reinstall also caused
an intermediate build to read missing files; the final clean `npm ci`, typecheck,
test, and build sequence completed successfully.

Known limitations: Starlette emits a deprecation warning for its HTTPX-based
TestClient; npm emits deprecation notices for transitive test dependencies.
These are not suppressed. Python dependencies have version bounds but no lockfile.
Live browser rendering was not inspected; component rendering and live HTTP/proxy
checks cover the Phase 00 acceptance criteria.
