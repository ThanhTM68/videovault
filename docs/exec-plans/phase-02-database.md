# Phase 02 — Database & Migrations

## Goal
Implement V1 persistence model from `docs/database.md`.

## Model
gpt-6.1-sol high.

## Deliverables
- SQLAlchemy models
- session lifecycle
- Alembic
- initial migration
- repositories for videos/downloads/jobs/media_files
- SQLite foreign key enforcement
- UTC timestamp policy
- uniqueness for platform video identity

## Critical decisions
- Define deletion semantics explicitly.
- Define enum/status representation consistently.
- Avoid JSON fields holding data that belongs in queryable core columns.

## Tests
- migration up from empty DB
- unique `(platform, platform_video_id)`
- FK behavior
- repository CRUD
- history query semantics

## Acceptance
- [x] PASS: fresh DB can migrate and tests pass (115 backend tests).
- [x] PASS: SQLAlchemy 2 engine/session layer exists with request cleanup and shutdown disposal.
- [x] PASS: SQLite foreign keys are enabled and enforced on multiple connections.
- [x] PASS: Alembic is configured without importing the FastAPI entry point.
- [x] PASS: initial revision `0001_v1` upgrades an empty DB; downgrade/re-upgrade works.
- [x] PASS: all ten V1 tables exist; schema/ORM metadata parity and FK actions are inspected.
- [x] PASS: platform/video identity, known creator identity, tag names, and association pairs are unique.
- [x] PASS: four repositories have tested basic persistence and successful history queries.
- [x] PASS: commits are caller-owned; integrity and request failures roll back safely.
- [x] PASS: deletion rules preserve media/history and restrict unsafe video deletion.
- [x] PASS: UUID IDs, aware UTC round-trips, enums, numeric checks, and non-secret config are tested.
- [x] PASS: Ruff, dependency checks, application import/startup, and frontend compatibility checks pass.
- [x] PASS: no Phase 03+ behavior, V2 tables, secrets, generated DBs, or frontend source changes.

## Relevant docs
`AGENTS.md`, `.agent/PLANS.md`, `docs/product-spec.md`,
`docs/architecture.md`, `docs/database.md`, and `docs/api-contract.md`.

## Current state assumptions
Phase 01 is committed and the working tree is clean on `phase/02-database`.
Database sessions are a failing placeholder. Settings validate SQLite URLs, and
application health is independent of database readiness. No database exists yet.

## Implementation steps
1. Add SQLAlchemy/Alembic and database engine/session/type conventions.
2. Define the ten V1 tables and explicit constraints/relationships.
3. Create and inspect a fixed initial Alembic migration.
4. Add four focused repositories and migrated temporary-database fixtures.
5. Verify migration up/down/up, persistence, integrity, deletion, and transactions.
6. Update documentation, run project checks, and review the entire diff.

## Decisions before implementation
- Entity IDs are UUID4 strings (36 characters); association identities are
  composite primary keys, enforcing pair uniqueness without redundant indexes.
- File sizes and engagement counts use BigInteger to avoid a future 32-bit
  limit; unknown metadata is nullable rather than replaced with guessed values.
- Aware datetimes are normalized to UTC; SQLite stores naive UTC values and the
  ORM returns aware UTC values. Naive input is rejected rather than guessed.
- Python StrEnum values use non-native SQLAlchemy enums with named CHECK
  constraints and value validation, avoiding SQLite native-enum assumptions.
- Repositories add/flush/query/delete only. Services own commit/rollback.
  Request sessions never auto-commit and rollback outstanding work on close.
  Sessions expire objects on commit so database-driven SET NULL/CASCADE actions
  do not leave stale relationship values in the next transaction.
- SQLite foreign keys are enabled on every engine connection. Relative database
  paths resolve against repository root. Engines are app-scoped, connect lazily,
  and are disposed on application shutdown. Startup does not migrate/create tables.
- Creator deletion sets video creator references to NULL. Job deletion sets
  download job references to NULL. Download deletion sets media download
  references to NULL, preserving files and video metadata.
- Video deletion is RESTRICTED while download/media records reference it.
  Association rows alone cascade when a video, collection, or tag is removed.
  ORM relationships do not cascade entity deletion or silently null restricted FKs.
- Successful history means download status `completed`, independently of media
  presence. Forced attempts remain separate download events.
- Storage keys are opaque identifiers. Storage-account config accepts only flat
  non-secret `root_path`/`root_folder_id` strings; credentials/tokens are not fields.
- No V2 tables, APIs, physical file operations, automatic dedup, job claiming,
  state-machine execution, or background worker logic are added.

## Data/API changes
Initial V1 schema only. No new production endpoints; health is unchanged.

## Test plan
Migrate temporary SQLite files with Alembic (no test create_all); inspect tables,
constraints, indexes, and metadata parity; downgrade/re-upgrade; identity and
association uniqueness; nullable creator identities; FK enforcement across
connections; UTC round-trips/naive rejection; enum/numeric/config validation;
four repositories, successful history, rollback and request session lifecycle;
loaded/unloaded relationship deletion behavior; Windows/root-relative paths.

## Rollback/recovery
Never downgrade a populated database casually: the initial downgrade drops all
V1 tables and their records. Back up the database before migration changes.
Up/down/up verification uses temporary databases only, never `data/videovault.db`.

## Deferred work
Download engine, adapters, queue worker/claiming/concurrency/recovery, library
services/UI, storage operations, Google Drive/OAuth, FFmpeg editor, batch workflows,
V2 tables, and Python dependency locking.

## Verification
Completed on 2026-10-02, using Python 3.12.9, SQLAlchemy 2.0.54, and Alembic 1.20.0.

- Root `.venv/Scripts/python.exe -m pip install -e './backend[dev]'`: PASS.
- Backend `python -m pip check`: PASS, no broken requirements.
- Backend `python -m pytest`: PASS, 115 tests.
- Backend `python -m ruff check .`: PASS.
- Backend `python -m ruff format --check .`: PASS, 48 Python files formatted.
- Backend `python -c 'from app.main import app; print(app.title)'`: PASS (`VideoVault`).
- Backend `python -m app.main`: PASS; live health returned HTTP 200 with `{"status":"ok"}`.
- CLI integration tests run `python -m alembic -c <absolute ini> upgrade head`,
  `downgrade base`, `upgrade head`, and `check` in another cwd against a temporary DB:
  PASS. Offline `upgrade head --sql` also passes without creating a DB.
- Migration metadata parity: no diffs; actual table/PK/unique/FK/index/CHECK contracts inspected.
- Frontend `npm run typecheck`: PASS.
- Frontend `npm test`: PASS, 7 tests.
- Frontend `npm run build`: PASS, 28 modules transformed.
- `git diff --check`, tracked/new-file review, status, and DB/secret ignore checks: PASS.
  The development data directory contains only its original three `.gitkeep` files.

The initial migration was generated against an empty temporary database, then
reviewed and formatted. BigInteger storage was added before release to avoid future
32-bit file-size/count limits. Initial Ruff import/formatting findings were fixed;
Alembic's path-separator deprecation was resolved explicitly. A first generation
command hit PowerShell native-argument quoting; using a Python stdin script fixed it.
Final migration CLI checks include separate processes and working-directory changes.

Known limitations: the existing Starlette HTTPX TestClient deprecation remains;
Python dependencies have no lockfile; enum/CHECK changes require reviewed migrations;
storage-config validation applies to ORM writes, and future services must enforce
cross-video consistency when linking a media record to a download. No new public
write APIs exist in this phase. Initial downgrade is destructive to V1 records.
The temporary server was stopped. No commit made.
