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
- backend starts
- frontend starts
- frontend can display API health in development
- tests pass
