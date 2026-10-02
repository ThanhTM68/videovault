# Phase 07 — Library, History & Dedup

## Goal
Make downloaded state reliable and user-manageable.

## Model
gpt-6.1-sol high.

## Deliverables
- primary dedup `(platform, platform_video_id)`
- successful-download history
- SHA-256 exact file hash after completed media
- Library API/UI
- History API/UI
- search/filter basics
- collections
- personal tags
- force redownload
- delete file
- remove history
- delete everything

## Critical semantics
Operations must not accidentally conflate:
video metadata, history records, and physical files.

## Tests
Every destructive operation needs tests.
Force-redownload needs regression test.

## Acceptance
Previously successful video is skipped by normal download,
but can be downloaded after history removal or via explicit force policy.
