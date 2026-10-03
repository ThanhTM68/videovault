# Downloader Design

## Principles

- yt-dlp is an implementation detail behind adapters.
- URLs must be classified/validated before use.
- Never invoke a shell with a concatenated user URL.
- Prefer library APIs or subprocess argv arrays.
- Live extractor behavior is not deterministic enough for CI.

## Service boundary (Phases 03–04)

`DownloaderService` classifies the URL, selects an injected adapter, resolves metadata,
prepares a validated `DownloadRequest`, executes it in an isolated workspace, and probes
the output. It is synchronous: Phase 05 must execute blocking work outside API handlers.
There is no resolve/download API endpoint, DB write, history inference, or background job.

`DownloaderAdapter` exposes `resolve`, `get_formats`, `download`, and frozen capability
metadata. Phase 04 defaults to five concrete adapters through `AdapterRegistry`.
`YtDlpAdapter` remains the shared single-video core; all yt-dlp imports and options stay
in `services/downloader/ytdlp.py`. Explicit injected adapter mappings remain supported.
Each operation creates its own YoutubeDL instance; no mutable extractor is shared.

Detection uses the existing `Platform` enum for recognized HTTP(S) hosts, plus the
detector-only string `unknown`. The persisted enum/schema is unchanged. Host boundary
matching distinguishes `youtube.com` from `youtube.com.evil.example`. Classification
uses no network requests. Credentials, malformed hosts, local paths, nonstandard ports,
control characters, whitespace, and non-HTTP(S) schemes are rejected. Host recognition
does not certify every URL type or extractor on a platform.

## Platform adapters (Phase 04)

Each adapter adds `can_handle` and platform-specific URL, canonical page, creator and
extractor policies while implementing the existing resolve/get_formats/download contract.
The registry is the only selection owner. The service exposes `capabilities()` internally,
returning a fresh mapping of Platform to immutable AdapterCapabilities; no HTTP route is added.

| Adapter | Supported individual URL forms | Extraction policy |
|---|---|---|
| YoutubeAdapter | `watch?v=ID`, `youtu.be/ID`, `shorts/ID` | YouTube video extractor only; Shorts remain Platform.YOUTUBE |
| TikTokAdapter | `@user/video/ID`, `share/video/ID`, `vm.tiktok.com/TOKEN`, `vt.tiktok.com/TOKEN`, `www.tiktok.com/t/TOKEN` | Native TikTok/video redirect extractors; challenge solving blocked |
| DouyinAdapter | `douyin.com/video/ID` | Separate Douyin extractor and identity |
| InstagramAdapter | `/reel/CODE`, `/reels/CODE`, `/p/CODE`, `/tv/CODE` | Single public video only; images/carousels/multi-entry results rejected |
| FacebookAdapter | `/reel/ID`, `/watch?v=ID`, `/video.php?v=ID`, `/PAGE/videos/ID` | Facebook video/reel extractors only |

Support means implemented delegation through the configured yt-dlp extractor when the
public source is resolvable. It does not guarantee current live-site availability. No
live-platform check was performed for Phase 04; deterministic fixtures are the evidence.
Douyin short links (`v.douyin.com`) and `fb.watch` remain recognized platform hosts but
are unsupported extraction inputs: no Generic fallback or custom redirect scraper is used.
Other native URL forms not listed above remain unsupported until deliberately added.

Common mobile/root hosts are normalized to official canonical hosts where implemented.
Adapters strip non-identity query parameters from extraction URLs, including tracking
and playlist selection. Watch URLs containing both a video ID and playlist query resolve
only that video. Profiles/channels/tags/search/playlist/story pages fail before extraction.

An internal frozen `ExtractionPolicy` restricts loaded extractor names and supplies a
metadata normalization callback. The wrapper first enforces its shared single-video,
DRM/live/auth checks, then invokes platform normalization. Download refreshes and checks
metadata again before media transfer; changed IDs, wrong extractor families, foreign
canonical pages or multi-entry results fail. No recursive playlist/carousel unwrapping.

IDs accept exact nonnegative integers or safe strings, never float conversion. Video
identity remains `(Platform, platform_video_id)`; a TikTok ID never becomes Douyin identity.
Resolved TikTok short links with only a video ID use the native `/share/video/ID`
canonical form; missing creator information remains null.
YouTube creator_id uses channel_id, not an inferred username/handle. TikTok/Douyin prefer
display names and explicit uploader IDs; Instagram/Facebook reuse available uploader
identity. Optional unsafe/missing creator URLs become null. Upload date is a date with
UTC timestamp fallback; counts remain nullable/nonnegative and integer strings preserve
precision. Missing dimensions/fps may use structured video format metadata; titles are
never parsed for resolution. Resolution summaries may describe the highest source format
even above 1080; the existing selection and final probe still enforce the download cap.

The existing yt-dlp dependency is pinned to **2026.8.19** because the TikTok safety guard
overrides a version-sensitive challenge hook. Both the TikTok policy and unconfigured
generic core stop that library path with AuthenticationRequiredError. Upgrading requires
review of the hook and running its real-extractor, mocked-webpage regression test; do not
remove the guard merely to make a changing live site work. No new scraper/browser package,
credential configuration, automated login, or challenge/signature solving system is added.

## Network boundary

Production registry selection requires exact permitted social hosts and individual URL
shapes. Unknown domains, localhost, IP literals (including private/link-local addresses),
non-HTTP schemes, and arbitrary platform subdomains cannot select an adapter. Extractor
names are restricted per platform, without Generic; post-extraction canonical pages must
match that platform and the requested identity where the URL carries it.

Redirects and CDN/media requests remain owned by yt-dlp. These controls limit inputs and
extractor families; they are not complete transport-level DNS/IP or rebinding protection.
No generic fetch proxy, manual HTTP client, custom short-link redirect following, or
DNS enforcement gateway is introduced. Stronger transport enforcement remains deferred.

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

All five adapters expose only resolve_single/download_single as true. Other capabilities are
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
Phase 07 workers explicitly consume or remove it. No permanent move,
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

### Phase 05 cancellation integration

DownloaderService.download accepts an optional per-invocation threading.Event. Its
ContextVar scope keeps the existing adapter protocol unchanged and separates thread
signals. ProgressReporter checks cancellation even with no observer and propagates
DownloadCancelledError while still isolating ordinary observer failures. This reaches
yt-dlp download/postprocessing hooks. The service also checks around resolve and probe;
the existing checked workspace cleanup runs on cancellation.

Blocking extraction/network/FFmpeg is cooperative: no arbitrary process termination,
and cancellation can wait until a hook/operation returns. Queue workers acknowledge
only after execution and cleanup stop; a cancel request racing a validated return uses
discard_result to remove only that invocation's temporary workspace before acknowledgement.
Completed callback alone never finalizes a durable job; successful return is required.
These additions supersede the earlier Phase 03/04 deferral of cancellation above.
The downloader itself adds no history or credential workflow. Phase 07 worker/library
orchestration consumes its validated output as described below.

### Phase 07 identity and durable completion

The queue worker resolves `(platform, platform_video_id)` before entering the shared
identity lock, upserts nonempty metadata and queries completed Download events. A normal
duplicate skips before calling download, regardless of file deletion/missing status.
Force starts a real attempt. Download still uses existing adapters, format selection,
cooperative cancellation and real ffprobe validation; the returned identity must match
the pre-resolved identity. No yt-dlp calls were added to API handlers.

LocalFiles copies validated output into an exclusively created unique managed filename
under LOCAL_STORAGE_ROOT, fsyncs it, streams SHA-256 in 1 MiB chunks and verifies size.
Only then can the worker commit MediaFile, successful Download and fenced Job completion.
The temporary workspace is consumed after success. On copy/hash/commit failure or lost
cancellation, only newly owned output is removed; older forced files remain intact.
Retries have distinct attempt events; restart recovery closes stale events. No full-file
hash buffer, ffmpeg hash subprocess, filename/history inference or hash identity dedup.

Managed keys must be relative; lexical traversal, drive/absolute paths, backslashes,
symlinks and Windows reparse points are rejected independently of DB contents. Delete
operations cannot unlink an external file, even if a corrupt row points to it. Public
Library/History/Job responses never expose managed roots or absolute local paths.
Crash-window or failed-cleanup orphans and full-root reconciliation are deferred.

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

Deferred: broader platform URL forms, discovery/crawling, persistent queue/cancellation,
history/dedup, Drive, batch, editor, similarity, codec conversion, and unknown-height policy.

## Phase 08 final destination integration

Queue payload includes local/google_drive storage_target; downloader preparation excludes
it and force. Both destinations use the same resolve/download/process/probe path.
Worker hands validated TEMP output to StorageService; Drive adds uploading progress.
Provider success precedes atomic MediaFile/Download/Job completion, then TEMP cleanup.
Failed/cancelled attempts compensate only new output and clean TEMP after that attempt;
retry downloads anew. Identity history still drives duplicate skips across providers.
Source adapters never import or call the Google SDK. Drive is implemented in Phase 08;
Batch/Editor and later features remain deferred.
