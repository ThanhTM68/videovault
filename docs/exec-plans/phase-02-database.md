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
Fresh DB can migrate and tests pass.
