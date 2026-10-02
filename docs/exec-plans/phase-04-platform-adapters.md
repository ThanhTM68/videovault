# Phase 04 — Platform Adapters

## Goal
Add adapters for prioritized public-content sources.

## Model
gpt-6.1-sol high.

## Priority
1. YouTube
2. TikTok
3. Douyin
4. Instagram
5. Facebook

## Deliverables
Each adapter:
- URL recognition
- normalized metadata
- single-video resolve
- capability report
- downloader delegation

Only expose profile/channel listing when reasonably supported.

## Reliability rule
A failure in one adapter must not break other platforms.

## Tests
Recorded metadata fixtures per platform.
Tests must not assume live extractor availability.

## Acceptance
Supported URL fixture for each platform normalizes consistently.
Unsupported/changed extractor errors produce stable domain errors.
