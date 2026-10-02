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
- startup validates config
- domain errors map to API errors
- tests cover invalid config and error mapping
