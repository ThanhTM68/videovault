# Phase 09 — Batch Channel/Profile

## Goal
Create a capability-aware batch workflow.

## Model
gpt-6.1-sol high.

## Input
- profile/channel/source URL
- N
- ordering requested
- optional min/max views
- optional date range
- optional duration range

## Deliverables
- source resolve endpoint
- adapter capability reporting
- preview candidate videos
- batch selection
- dedup before job creation
- enqueue selected videos
- clear unsupported-filter messages

## Rule
Do not fake sorting if source metadata/API does not support it reliably.

## Tests
Use deterministic source fixtures.
Test N limits, filtering, duplicate skipping, unsupported capability.

## Acceptance
At least one strong adapter (YouTube first) supports complete preview-to-batch workflow.
Other adapters degrade honestly according to capabilities.
