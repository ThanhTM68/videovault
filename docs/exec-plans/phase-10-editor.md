# Phase 10 — FFmpeg Editor & Presets

## Goal
Provide lightweight reproducible batch media transformations.

## Model
gpt-6.1-sol high.

## Operations
- trim
- crop
- resize
- 9:16 / 1:1 / 16:9
- black / white / blur background
- text overlay
- speed
- mute/volume
- export <=1080p

## Deliverables
- validated edit request schema
- FFmpeg command builder
- preset CRUD
- edit jobs through queue
- edited outputs tracked as media_files kind=edited
- UI form, not a complex timeline

## Security/correctness
Never interpolate raw user text into a shell string.
Use argument arrays and controlled filter escaping.

## Tests
Command-construction tests and a tiny local sample integration test.

## Acceptance
Preset can be applied to one or multiple selected library videos.
