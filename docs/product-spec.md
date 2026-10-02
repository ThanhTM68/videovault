# VideoVault Product Specification

## Product statement

VideoVault is a local-first web application for collecting, downloading,
organizing, and lightly processing short-form video.

It is not merely a paste-URL downloader.

## Primary user flows

### Quick Download
User pastes one or many supported public URLs.

System:
1. resolves metadata;
2. shows platform/title/creator/duration/available resolution;
3. checks known download state;
4. queues requested download;
5. downloads best available quality up to configured max height;
6. merges streams when required;
7. stores final media;
8. records download and file metadata.

### Batch Download
User enters a profile/channel source supported by its adapter.

User may request:
- latest N
- oldest N if source provides ordering
- highest-view N if reliable metadata is available
- filters by date/view/duration where source exposes those fields

Unavailable capabilities must be reported honestly per platform.

### Library
User can:
- search
- filter
- inspect metadata
- open file
- tag
- add to collections
- find download history
- request re-download
- delete file
- remove history
- delete both

### Queue
Statuses:
- queued
- resolving
- downloading
- processing
- uploading
- completed
- failed
- cancelled
- skipped_duplicate

Operations:
- pause queue
- resume queue
- retry failed job
- cancel queued/running job where feasible
- clear completed jobs from queue view without deleting history

### Storage
V1:
- local filesystem
- Google Drive provider

Downloaded files and database records are separate concepts.

### Editor
V1 lightweight editing:
- trim
- crop
- resize
- aspect presets 9:16, 1:1, 16:9
- black/white/blur background
- text overlay
- playback speed
- mute/volume
- export <=1080p

No CapCut-style timeline in V1.

## Dedup semantics

Primary identity:
`(platform, platform_video_id)`

Additional:
- canonical URL
- SHA-256 exact file hash
- later V2 perceptual similarity

"Remove history" makes the video eligible for a normal download again.
"Force redownload" bypasses downloaded-history skip without requiring history deletion.

## V2

- cross-platform discovery
- saved searches
- similarity groups
- quality score
- earliest-known upload comparison
- watchlists
- automation rules

## Non-goals V1

- multi-user accounts
- payment/subscription
- auto reposting
- mobile app
- browser extension
- cloud microservices
- DRM/private access bypass
