# Phase 03 — Download Engine Core

## Goal
Create platform-independent downloader contracts and a yt-dlp-backed core implementation.

## Model
gpt-6.1-sol high.

## Deliverables
- normalized video/domain types
- platform detector
- downloader adapter protocol/base class
- yt-dlp wrapper isolated from routes
- quality selection max 1080 default
- progress callback abstraction
- download to temp
- ffprobe validation
- error mapping

## Non-goals
Do not implement five full platform adapters yet.
Do not implement persistent worker queue yet.

## Tests
Use fixtures/mocks, not live websites for core CI.

Cover:
- URL validation
- normalized metadata
- max-height selection
- error mapping
- safe subprocess/library invocation

## Acceptance
A service can resolve/download using a mock/test adapter end-to-end into temp storage.
