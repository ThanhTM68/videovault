# Phase 01 — Backend Foundation

## Goal
Build configuration, error handling, dependency structure, API versioning, logging.

## Model
gpt-6.1-sol medium.

## Deliverables
- settings module
- structured app startup
- domain error base classes
- stable API error envelope
- service/repository directories
- DB session placeholder ready for Phase 02
- CORS restricted to configured dev frontend origin

## Non-goals
No full DB tables or yt-dlp implementation.

## Acceptance
- [x] PASS: startup validates config (invalid environment values fail at factory creation).
- [x] PASS: domain errors map to API errors (400/404/409 codes, messages, details tested).
- [x] PASS: tests cover invalid config and error mapping (55 deterministic backend tests).
- [x] PASS: centralized settings support documented defaults and environment overrides.
- [x] PASS: application startup is clean (import, Uvicorn startup, and live health verified).
- [x] PASS: API versioning remains `/api/v1`; health response remains compatible.
- [x] PASS: stable error envelope covers domain, validation, HTTP, and unexpected errors.
- [x] PASS: exception handlers are tested; normal tests still raise unexpected errors.
- [x] PASS: CORS uses a configured origin and excludes untrusted origins/credentials.
- [x] PASS: centralized standard logging supports development/test/production levels.
- [x] PASS: service/repository packages and DB session seam exist without DB implementation.
- [x] PASS: backend/frontend tests, frontend typecheck/build, and Ruff checks pass.
- [x] PASS: no Phase 02+ features, credentials, media, or test-only production routes added.

## Relevant docs
`AGENTS.md`, `.agent/PLANS.md`, `docs/product-spec.md`,
`docs/architecture.md`, and `docs/api-contract.md`.

## Current state assumptions
Phase 00 is committed; the working tree is clean on `phase/01-foundation`.
The existing backend uses Pydantic Settings, an application factory, and an
`api/v1` router. Health remains process-only and returns `{"status":"ok"}`.

## Implementation steps
1. Extend validated settings and support explicit factory settings in tests.
2. Add domain errors, transport-owned HTTP mappings, and central handlers.
3. Configure standard logging and restricted CORS in the factory.
4. Add shared test fixtures, foundation packages, and a nonfunctional DB seam.
5. Run backend/frontend compatibility checks, startup, and final diff review.

## Decisions and security boundaries
- Only SQLite URLs are accepted for the V1 database setting. No engine, session,
  tables, or filesystem directories are created in this phase.
- Relative storage paths resolve against the repository root, independent of cwd.
- A single explicit HTTP(S) frontend origin is allowed; credentials are disabled.
  The generic 500 handler adds that same trusted origin because Starlette handles
  unexpected failures outside its CORS middleware; rejected origins remain excluded.
- Domain errors contain intentionally public messages/details. HTTP mappings
  belong to the API layer, and request validation omits submitted values/context.
- Unexpected errors return a generic 500. Server logs include exception class
  and stack locations, omitting exception messages, request data, and locals to
  avoid exposing credentials. TestClient continues to raise unexpected errors
  by default; only response-contract tests disable that behavior.
- DB session dependency raises NotImplementedError until Phase 02 and is not
  attached to any production route. Service/repository packages contain only
  boundary documentation.
- The factory lives in `app/application.py`, separating creation from the
  environment-loading `app/main.py` entry point for deterministic test imports.
- Pydantic v2 is now an explicit runtime dependency because foundation modules
  import it directly. No database/media packages are introduced.

## Data/API changes
No database changes. Health is unchanged. Domain, HTTP, request validation, and
unexpected errors use the documented `error.code/message/details` envelope.

## Test plan
Defaults, dotenv/environment overrides, invalid settings and startup rejection;
settings dependency isolation; health; domain/HTTP error mappings and headers;
validation sanitization; generic 500 and sanitized server logs; allowed/rejected
CORS; logging level/idempotence; DB placeholder; frontend compatibility.

## Rollback/recovery
Changes are isolated on the phase branch. No data migration or storage mutation
occurs. Restore Phase 00 code to roll back; existing `.env` values are not edited.

## Deferred work
SQLAlchemy engines/sessions/models and foreign-key activation, Alembic migrations,
repositories, downloader, adapters, persistent queue, library, storage providers,
Google Drive, FFmpeg editor, batch workflows, and Python dependency locking.

## Verification
Completed on 2026-10-02. Commands used the repository virtual environment:

- Backend `python -m pip install -e '.[dev]'`: PASS.
- Backend `python -m pip check`: PASS, no broken requirements.
- Backend `python -m pytest`: PASS, 55 tests.
- Backend `python -m ruff check .`: PASS.
- Backend `python -m ruff format --check .`: PASS, 26 files formatted.
- Backend `python -c 'from app.main import app; print(app.title)'`: PASS (`VideoVault`).
- Backend `python -m app.main`: PASS, Uvicorn application startup completed.
- Live HTTP checks: health 200 with configured CORS origin, preflight 200,
  and missing-route 404 with the standard error envelope.
- Frontend `npm run typecheck`: PASS.
- Frontend `npm test`: PASS, 7 tests.
- Frontend `npm run build`: PASS, 28 modules transformed.
- `git status`, `git diff`, new-file inspection, `git diff --check`, and
  secret/media ignore-rule checks: PASS. Frontend source files are unchanged.

Initial Ruff checks identified import/formatting issues, fixed with Ruff and
verified again. A test payload class was renamed to avoid pytest collection
warnings. The remaining warning is Starlette's existing HTTPX TestClient
deprecation; no warning suppression was added. Python locking remains deferred.
The temporary development server was stopped after verification. No commit made.
