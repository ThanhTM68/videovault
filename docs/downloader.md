# Downloader Design

## Principles

- yt-dlp is an implementation detail behind adapters.
- URLs must be classified/validated before use.
- Never invoke a shell with a concatenated user URL.
- Prefer library APIs or subprocess argv arrays.
- Live extractor behavior is not deterministic enough for CI.

## NormalizedVideo

Minimum:
- platform
- platform_video_id
- canonical_url
- title
- creator
- duration
- upload_date
- counts when available
- thumbnail
- raw metadata for debugging

## Platform capabilities

Every adapter exposes capabilities:

- resolve_single
- list_profile_or_channel
- sort_newest
- sort_oldest
- sort_views
- filter_views
- filter_date
- filter_duration

Capabilities may be false or unknown.

UI must not pretend unsupported sorting exists.

## Quality rule

Default:
- final video height <= 1080
- prefer best quality meeting max height
- prefer sensible MP4/H.264/AAC compatibility when possible
- avoid unnecessary transcode if merge/remux is enough

Use ffprobe to inspect resulting file.

## Progress

Progress event should include:
- job_id
- phase
- percent nullable
- downloaded_bytes nullable
- total_bytes nullable
- speed nullable
- eta nullable
- message

Throttle DB/UI progress writes to avoid excessive writes.

## Retry

Retry transient failures only.
Do not infinite retry:
- unsupported
- removed/private
- authentication-required without configuration
- invalid URL

## Testing

Unit-test:
- URL classification
- metadata normalization
- format selection
- duplicate policy
- error mapping

Integration tests can use saved metadata fixtures and a local tiny media sample.
