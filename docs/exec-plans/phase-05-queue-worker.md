# Phase 05 — Persistent Queue & Worker

## Goal
All download work becomes persistent jobs.

## Model
gpt-6.1-sol high.

## Deliverables
- SQLite-backed jobs
- queue service
- worker loop
- configurable concurrency
- progress persistence throttling
- cancel
- retry
- pause/resume
- restart recovery
- status API

## State machine
queued -> resolving -> downloading -> processing -> uploading -> completed

Other terminal/intermediate:
failed, cancelled, skipped_duplicate

Invalid transitions must be rejected.

## Recovery
On app restart, stale running jobs must not remain permanently running.
Define deterministic recovery/requeue policy.

## Tests
- transition tests
- retry limits
- concurrent claim test as practical with SQLite
- stale job recovery
- cancellation behavior

## Acceptance
A multi-URL request creates multiple durable jobs and survives process restart semantics.
