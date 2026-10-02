# Phase 14 — V2 Watchlists & Download Rules

## Goal
Monitor explicitly configured public sources and create review/download jobs based on rules.

## Model
gpt-6.1-sol high.

## Deliverables
- watchlists
- scan state
- dedup-aware new-item detection
- rules:
  - view threshold where metadata exists
  - duration
  - date
  - source
- review-first default
- optional explicit auto-download rule
- scheduling abstraction

## Reliability
Scanning must not re-download known items.
Failures must be isolated per source.
