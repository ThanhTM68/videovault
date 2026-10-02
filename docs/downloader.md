# Downloader Design

## Principles

- yt-dlp is an implementation detail behind adapters.
- URLs must be classified/validated before use.
- Never invoke a shell with a concatenated user URL.
- Prefer library APIs or subprocess argv arrays.
- Live extractor behavior is not deterministic enough for CI.

## Phase 03 service boundary

`DownloaderService` classifies the URL, selects an injected adapter, resolves metadata,
prepares a validated `DownloadRequest`, executes it in an isolated workspace, and probes
the output. It is synchronous: Phase 05 must execute blocking work outside API handlers.
There is no resolve/download API endpoint, DB write, history inference, or background job.

`DownloaderAdapter` exposes `resolve`, `get_formats`, `download`, and frozen capability
metadata. `YtDlpAdapter` is a generic single-video implementation, not five complete
platform adapters. All yt-dlp imports and options stay in `services/downloader/ytdlp.py`.
Each operation creates its own YoutubeDL instance; no mutable extractor is shared.

Detection uses the existing `Platform` enum for recognized HTTP(S) hosts, plus the
detector-only string `unknown`. The persisted enum/schema is unchanged. Host boundary
matching distinguishes `youtube.com` from `youtube.com.evil.example`. Classification
uses no network requests. Credentials, malformed hosts, local paths, nonstandard ports,
control characters, whitespace, and non-HTTP(S) schemes are rejected. Host recognition
does not certify every URL type or extractor on a platform.

## Normalized models

`NormalizedVideo` includes platform, platform_video_id, canonical_url, title, description,
creator identity/URL, duration_seconds, upload_date, counts, width/height/fps,
thumbnail_url, normalized formats, and raw_metadata. Missing optional values stay null.
IDs are never truncated; oversized or missing identities fail resolution.

`VideoFormat` includes format identity, extension, dimensions/fps, codecs, bitrates and
DRM status. Download URLs and headers are never stored in the normalized format model.
`DownloadRequest` accepts url, max_height, output_directory, preferred_container
(`mp4`, `mkv`, `webm`), and audio_enabled; no arbitrary options dictionary is accepted.
`FormatSelection`, `ProgressEvent`, `DownloadResult`, and media `ProbeResult` complete
the internal contracts. These models are not new public API schemas.

Raw metadata is a bounded scalar allowlist (short id/title/uploader/extractor/ext plus
numeric summaries). It excludes nested extractor structures, descriptions, stream URLs,
headers, cookies, and options. Format summaries are limited to 1000 entries. Canonical
URLs retain only identity query keys; creator/thumbnail URLs drop queries and fragments.
This can make signed thumbnail URLs unusable; future adapters can provide safe previews.

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

The core exposes only resolve_single/download_single as true. Other capabilities are
false; crawling/sorting/filtering remains future work. Playlists, live streams, and DRM
results are rejected. Metadata marked private/login-only produces authentication-required.

UI must not pretend unsupported sorting exists.

## Quality rule

Default max_height is 1080; requests may lower it. Settings also impose a ceiling on
externally constructed requests. Select highest known height within the cap, then fps,
then bitrate; MP4/H.264 compatibility breaks ties. Format ID provides a deterministic
final tie-breaker. Never choose an above-cap or DRM format. Unknown heights are ineligible
because the engine cannot establish the cap safely before downloading.

With audio enabled, use progressive video+audio or best eligible video plus audio-only
stream, ranked by audio bitrate with codec compatibility breaking ties. A lower-quality
progressive MP4 does not defeat a higher-quality separate stream. With audio disabled,
require video-only input; progressive-only sources fail rather than silently retaining
audio. Audio stripping and codec normalization remain deferred.

yt-dlp merges separate streams and uses FFmpegVideoRemuxer for the requested container.
Merge/remux copies streams; it does not force H.264 or re-encode. Incompatible codec/
container combinations fail cleanly instead of launching a hidden transcode. FFmpeg and
ffprobe must be globally available on PATH; binaries are not bundled.

## Temporary output and validation

`TEMP_STORAGE_ROOT` comes from centralized settings. An optional output_directory must
resolve inside it. Each download allocates a UUID subdirectory and a bounded filename
containing platform, sanitized video ID, and title. Traversal separators, unsafe Windows
characters/reserved names, trailing dots/spaces, and yt-dlp template `%` characters are
removed or replaced. Independent invocations cannot collide.

On failure, cleanup removes only the invocation's checked workspace. A cleanup failure
is logged by category and never turns the operation into success. The service does not
delete paths outside that workspace. Successful output remains temporary and caller-owned;
future storage/library services must explicitly consume or remove it. No permanent move,
media row, job, download record, or duplicate decision occurs here.

`services/media/probe.py` discovers tools and runs ffprobe with an argument array,
`shell=False`, a 30-second timeout, file-only protocols, and MOV/MP4/Matroska/WebM
demuxers. Disguised playlists cannot initiate embedded network requests. Validation
requires a regular nonempty file,
readable positive finite duration, a video stream (excluding attached cover art) with
positive dimensions, final height
within the effective cap, and audio presence matching the request. Extension alone is
never proof of valid media. The service alone emits completion after successful probing.

## Progress

Phase 03 events contain phase (`resolving`, `downloading`, `processing`, `validating`,
`completed`), percent, downloaded_bytes, total_bytes, speed, eta, and safe message. Metrics
are nullable and finite. Download-hook `finished` means processing, not completion.
Percentage is per stream and may reset when downloading a separate audio stream.

Observers are isolated: the first callback exception disables that observer for the
operation and logs only its exception class. No hook writes to the DB. Phase 05 owns job
IDs, throttled UI/DB updates, durable cancellation, and queue concurrency. The synchronous
callback boundary can support later cooperative cancellation; it does not implement it now.

## Retry

The core uses a finite 30-second network socket timeout and one retry for transport,
fragments, and extractor operations. There is no service-level retry loop. User/CLI config
is not loaded. No browser cookies, cookie file, netrc, login credentials, CAPTCHA handling,
or access-control/DRM bypass is configured.

## Stable errors and logging

Fixed public messages/codes extend AppError: UnsupportedPlatformError, InvalidVideoUrlError,
MetadataResolveError, DownloadUnavailableError, AuthenticationRequiredError,
DownloadFailedError, InvalidOutputDirectoryError, MediaValidationError, and
MissingMediaToolError. Existing API error handling would serialize them as domain errors
(HTTP 400); Phase 03 adds no public endpoint or status-code contract.

Structured extractor failures are mapped where available; yt-dlp sometimes wraps auth/
availability failures in text, so classification uses conservative message patterns.
Original messages/tracebacks are never returned or logged. Unknown resolve failures map
to metadata resolution failure; download/postprocessing failures map to download failure.
Lifecycle logs contain platform/category only, not user URLs, tokens, headers, remote
titles, raw extractor diagnostics, or every progress callback.

## Testing

Deterministic tests use synthetic JSON metadata, mocked extractors, and a test-only fake
adapter. Generated tiny media exercises real ffprobe, temporary output/cleanup, and
service completion. A loopback HTTP server also exercises real yt-dlp downloads, split
stream merging, and progressive MKV-to-MP4 remuxing through real FFmpeg.

No CI test contacts public platforms. Real-media integration skips only when required
executables are genuinely missing; installed tools with broken behavior fail tests.
An optional public metadata-only manual check is separate from acceptance and is not
evidence of full site support. No live-site check was required for this phase.

Deferred: real platform adapters, discovery/crawling, persistent queue/cancellation,
history/dedup, Drive, batch, editor, similarity, codec conversion, and unknown-height policy.
