# Phase 12 — V2 Discover

## Goal
Search/discover candidate short videos through supported providers.

## Model
gpt-6.1-sol high.

## Deliverables
- provider-specific discovery interface
- keyword/hashtag query where legitimately supported
- normalized result list
- platform/date/views/duration filters when metadata exists
- save candidate into library metadata without forcing download
- select and enqueue

## Rule
Discovery capability and freshness vary by platform.
Expose this in capability metadata and UI.
