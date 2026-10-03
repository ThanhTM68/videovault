# API Contract

Base: `/api/v1`

## Health
GET `/health`

Returns HTTP 200 with `{"status":"ok"}`. This reports application-process health;
it does not check database, storage, or external media services.

## Resolve
Phase 06 implements optional, single-video metadata preview.
POST `/videos/resolve`
Strict JSON body: `{"url":"https://www.youtube.com/watch?v=..."}`.
Uses existing download URL validation and identity-query sanitation. Invalid input
returns 422; resolve failures use the existing safe domain error envelope.

Returns platform, platform_video_id, canonical_url, title, creator, duration_seconds,
width, height and thumbnail_url; metadata fields may be null. Phase 07 adds nullable
video_id, has_file and has_download_history, derived from actual persisted identity and
managed file checks. Unknown identity returns null/false/false. No raw extractor data,
filesystem paths, formats or credentials are returned. The service resolves metadata
without downloading media or creating Video/Download/Job records; it may reconcile
missing-file markers for an existing video.

## Download
Phase 05 implements submission only. POST returns 202 after an atomic durable commit.
Body is strict (unknown fields rejected):
- urls: 1..100 HTTP(S) supported individual video URLs
- max_height: optional integer 1..1080; defaults to DOWNLOAD_MAX_HEIGHT
- preferred_container: mp4 (default), mkv or webm
- audio_enabled: strict boolean, default true
- storage_target: local or google_drive; omitted uses STORAGE_PROVIDER (local default)
- force: strict boolean, default false; true bypasses successful-history dedup

Malformed input returns 422; unsupported platform/URL form returns the existing domain
error (400). Either failure creates no jobs. Submitted URLs retain identity queries only.
No network resolution occurs before submission returns. Response:
```json
{"jobs":[{"id":"uuid","status":"queued"}]}
```
Response describes submission state; polling may already show running work. Duplicate
URLs create separate jobs. Dedup decisions occur after worker resolution, never in the
submission handler. A normal successful-history duplicate becomes skipped_duplicate;
it creates no Download or MediaFile. Force executes a real new attempt and preserves
older media. GET downloads/{id} remains planned; use GET jobs/{id}.

Planned broader contract:
POST `/downloads`
Body:
- urls[]
- max_height
- storage_target
- force

Returns created job IDs.

GET `/downloads/{id}`

## Jobs
Phase 05 implements the job operations and pause/resume below; Phase 06 adds the
read-only GET `/queue`, returning `{"paused":true/false}` from the running manager.
This allows browser reload to restore authoritative pause state. GET jobs accepts
optional status and type filters, page >=1 and page_size 1..100 (default 20). It returns
items/page/page_size/total, ordered by created_at then id. Job views expose id/type/status,
progress_percent, current_step, attempt_count/max_attempts, created_at/started_at/
heartbeat_at/completed_at/cancelled_at/cancel_requested_at and nullable error {code,message}.
Payloads, user URLs, extractor diagnostics and filesystem paths are excluded.

Cancel queued work immediately; running work records a request and remains running
until safe stop/cleanup. Repeated active requests are idempotent; terminal cancellation
and retry of any state except failed return 409 CONFLICT. Retry retains started-attempt
count, requires remaining capacity (default three attempts), resets runtime/error fields
and returns queued. Unknown IDs return 404 NOT_FOUND. Mutations return the updated job.
Pause/resume return {"paused":true/false}; pause blocks new claims only, and restart
resumes by default. Polling is the only delivery mechanism; no SSE/WebSocket is added.
GET `/jobs`
GET `/jobs/{id}`
POST `/jobs/{id}/cancel`
POST `/jobs/{id}/retry`
GET `/queue`
POST `/queue/pause`
POST `/queue/resume`

Progress delivery:
- begin with polling endpoint
- optional WebSocket/SSE can be added in Phase 05 if cleanly implemented

## Library
Implemented in Phase 07:

- GET `/videos`: page >=1, page_size 1..100 (default 25); search (title/creator,
  literal escaped LIKE, max 255), platform, has_file, has_download_history, tag_id,
  collection_id. Returns items/page/page_size/total, newest discovered first then id.
- GET `/videos/{id}`: Video metadata plus personal tags/collections, files and up to
  100 recent history events. Public file fields: id, size_bytes, sha256, container,
  width, height, state (available/missing/deleted/unavailable). No storage keys or
  local paths. has_file means an actually present active local file; has_download_history
  means at least one completed Download, irrespective of file presence.
- DELETE `/videos/{id}/file`: remove all active managed local files, mark deleted_at;
  preserve events. Missing files are idempotently marked deleted.
- DELETE `/videos/{id}/history`: hard-delete all this video's Download events;
  preserve files (download_id becomes NULL) and permit normal downloading again.
- DELETE `/videos/{id}/all`: delete files first, then history. All paths are validated
  before any unlink. A failed unlink preserves history; already deleted files remain
  accurately marked and retry can finish. Video/tag/collection records remain.
- POST `/videos/{id}/redownload`: no body; 202 with queued job IDs. Uses stored safe
  source URL, configured maximum height, mp4/audio defaults and force=true. No direct
  media operation in the route. Missing video returns 404; unsafe source 409.

Destructive routes return the updated Video detail, not a fabricated deletion count.
File filters use last-known DB missing/deleted markers; page/detail reads check actual
file presence and reconcile changed markers. There is no full managed-root scan.
PATCH video metadata and media streaming/open routes remain unimplemented.

## History
GET `/history`: page >=1, page_size 1..100 (default 25), platform and Download status
(queued/resolving/downloading/processing/uploading/completed/failed/cancelled/
skipped_duplicate). Returns actual
Download events newest first then id with video_id/title/platform, job_id, nullable
attempt_number, requested_quality, forced, timestamps and safe failure_code/message.
The worker only creates downloading/completed/failed/cancelled events; duplicate jobs
have none. requested_quality contains compact JSON options for new attempts; legacy
strings are preserved. Identity dedup queries completed events only.

## Collections
Implemented in Phase 07. Named lists return at most 1000 {id,name} objects.
Create accepts strict {name}, trims/collapses whitespace, rejects empty/over-255 input,
returns 201 {id,name}. Collection names may repeat; identities are distinct IDs.
Membership mutations are idempotent and return updated detail; missing resources 404.
GET/POST `/collections`
POST `/collections/{id}/videos/{video_id}`
DELETE `/collections/{id}/videos/{video_id}`

## Tags
Implemented in Phase 07 with the same strict create/list shape. Personal tag names
additionally casefold; repeated normalized creation returns the existing tag (201).
Membership uniqueness is enforced by composite primary keys. Source hashtags are not
automatically personal tags. Removing membership does not delete the tag itself.
GET/POST `/tags`
POST `/videos/{id}/tags/{tag_id}`
DELETE `/videos/{id}/tags/{tag_id}`

## Storage - Phase 08

GET `/storage`: `{default_target, providers:[{provider, configured, connected, available,
display_name, account_id, root_folder_id, error_code}]}`. Local snapshot, no Google I/O;
no tokens, client secrets, storage paths or credential filenames. Availability requires
connected credentials + root for Drive. It is not a live remote-health assertion.

POST `/storage/google-drive/connect` with `{}` returns `{authorization_url}` using
one-use state and PKCE. POST `/storage/google-drive/disconnect` with `{}` returns
StorageStatus; clears local credentials only and retains records/media.
GET `/storage/google-drive/callback?state=...&code=...` exchanges on backend, returns
303 to configured frontend `/storage?drive=connected` or `drive=error&reason=SAFE_CODE`.
No-store/referrer-policy protect the callback; raw code/token is never returned.
PUT `/storage/google-drive/root` with `{folder_id}` validates and selects a writable,
nontrashed accessible folder. POST same path with `{}` creates/reuses VideoVault (201).
Both return `{id,name}`; no broad folder browser or Picker.

POST `/videos/{video_id}/refresh-files` returns VideoDetail after targeted provider
existence checks. FileSummary adds `storage_provider` and `file_name` (basename).
States: available (checked), stored (Drive last-known), missing, deleted, unavailable.
Auth/network errors never mark remote files missing. Normal Library/preview reads do
not contact Drive. Existing delete routes dispatch through the provider; partial
failure preserves successful deletion markers and all history until every file succeeds.

Submission locally validates selected provider without upload/network I/O. Invalid enum
is 422; unconfigured/disconnected/root-unset Drive is safe HTTP 400. Stable storage
codes include STORAGE_NOT_CONFIGURED, STORAGE_NOT_CONNECTED, STORAGE_ROOT_INVALID,
STORAGE_UNAVAILABLE, STORAGE_PERMISSION_DENIED, STORAGE_UPLOAD_FAILED,
STORAGE_DELETE_FAILED, STORAGE_KEY_INVALID, STORAGE_UNMANAGED_OBJECT,
STORAGE_CREDENTIAL_FAILED, STORAGE_ACCOUNT_MISMATCH, STORAGE_ACCOUNT_AMBIGUOUS,
OAUTH_STATE_INVALID, OAUTH_DENIED, OAUTH_FAILED. Existing generic envelope applies.

## Batch
Implemented Phase 09. Routes are relative to `/api/v1` and reject extra body fields.

POST `/sources/resolve` (200): `{url,n?,ordering?,min_views?,max_views?,date_from?,date_to?,
min_duration?,max_duration?}`. URL length 1–2048; N strict integer 1–100 (default 20);
ordering `source` (default), `newest`, `oldest`, `views`. View bounds are strict
nonnegative integers; duration bounds finite nonnegative seconds; date bounds exact
YYYY-MM-DD. Ranges inclusive; low > high is 422. Zero is an explicit bound.

Response: `{preview_id,source,candidates,statistics,ordering}`. Source includes platform,
source_type=`channel_videos`, nullable source_id/display_name/total_available,
canonical_url, and seven Boolean capabilities (list_profile_or_channel, sort_newest,
sort_oldest, sort_views, filter_views, filter_date, filter_duration). Current YouTube
source adapter supports listing and duration only. Source order means unchanged flat
extractor order in a bounded window, without a newest or whole-channel guarantee.
Total_available is null. Supported URL forms and exact limits are in downloader.md.

Candidates: platform, platform_video_id, canonical_url, nullable title/creator/thumbnail_url/
duration_seconds/upload_date/view_count, has_download_history, has_file (DB last-known,
no provider network check). Statistics: enumerated_count, rejected_count, duplicate_count,
metadata_unavailable_count (unknown requested duration), filtered_count, returned_count,
already_downloaded_count and scan_limit=100. At most 100 raw entries are scanned; N caps
returned candidates after safe normalization, identity dedup and supported filtering.
No media downloads, full per-video resolve, Video/Job/Download/MediaFile writes or Google
calls. No raw extractor formats, URLs with credentials, headers or stream data are exposed.

POST `/sources/batch-download` (202): `{preview_id,selected_ids,max_height?,
preferred_container?,audio_enabled?,storage_target?,force?}`. Shared download option
validation/defaults match POST `/downloads`. Selected_ids: 1–100 safe YouTube IDs of
exactly 11 characters, including repeated selections. Arbitrary URLs/candidate objects
are rejected. Server verifies membership in its cached preview, canonical URLs, options
and local provider availability, then rechecks successful identity history in one query.
One ordinary job per eligible unique identity; all eligible jobs commit atomically.

Response: `{jobs,outcomes,requested_count,created_count,skipped_history_count,
skipped_duplicate_selection_count}`. Jobs are `{id,status:'queued'}` only. Each selected
occurrence has `{platform_video_id,outcome,job_id}`; outcome `queued`, `skipped_history`
or `skipped_duplicate_selection`; job_id null for skips. Force bypasses successful
history, preserving files; repeated selections still collapse to one job. Worker dedup
retains race protection. All-history selection returns 202 with zero jobs and truthful
counts. No submission source enumeration or Google API calls.

Previews are random opaque IDs, bounded to 32 snapshots with ten-minute TTL per backend
process. Successful submission consumes its preview, including zero-job results.
Validation/storage/transaction failure retains it for retry; expiry/restart/eviction/replay
requires a fresh preview. After an uncertain submission network failure check Queue first.

Safe 400 codes: SOURCE_URL_INVALID, SOURCE_UNSUPPORTED, SOURCE_LIST_UNSUPPORTED,
SOURCE_SORT_UNSUPPORTED, SOURCE_FILTER_UNSUPPORTED, SOURCE_RESOLVE_FAILED,
SOURCE_PREVIEW_EXPIRED, SOURCE_BUSY, BATCH_SELECTION_INVALID. Current other-platform
public profiles reject listing before extraction. Invalid schemas/ranges/options are 422;
existing storage errors retain their codes. No silent ordering/filter fallback.

## Editor
Planned Phase 10, not implemented.
POST `/editor/jobs`
GET `/editor/presets`
POST `/editor/presets`

## API conventions

Errors:
```json
{
  "error": {
    "code": "STABLE_CODE",
    "message": "Human readable message",
    "details": {}
  }
}
```

Do not expose raw stack traces to frontend.

Phase 01 mappings:

| Failure | HTTP status | Code |
|---|---|---|
| Base domain/application error | 400 | `APPLICATION_ERROR` |
| Missing resource/route | 404 | `NOT_FOUND` |
| Domain conflict | 409 | `CONFLICT` |
| Request validation | 422 | `VALIDATION_ERROR` |
| Unsupported HTTP method | 405 | `METHOD_NOT_ALLOWED` |
| Other handled HTTP exception | Original status | `HTTP_ERROR` |
| Unexpected exception | 500 | `INTERNAL_SERVER_ERROR` |

Domain error messages/details are intentionally public. HTTP exception headers
(for example `Allow` and `Retry-After`) are preserved. Validation details contain
an `errors` list with `location`, `type`, and the generic message `Invalid value`;
submitted values and validator context/messages are excluded. Unexpected errors
return `An unexpected server error occurred` and empty details in every environment.
Tests retain default exception re-raising to expose programming failures.
CORS preflight responses follow the middleware protocol and are not application
error responses. Only the configured frontend origin is allowed, without credentials.

Paginated lists:
- items
- page
- page_size
- total
