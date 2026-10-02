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
width, height and thumbnail_url; metadata fields may be null. No raw extractor data,
filesystem paths, formats, credentials or downloaded-state summary is returned.
The service calls the existing resolver without downloading media or writing jobs.

## Download
Phase 05 implements submission only. POST returns 202 after an atomic durable commit.
Body is strict (unknown fields rejected):
- urls: 1..100 HTTP(S) supported individual video URLs
- max_height: optional integer 1..1080; defaults to DOWNLOAD_MAX_HEIGHT
- preferred_container: mp4 (default), mkv or webm
- audio_enabled: strict boolean, default true
- storage_target: local only; this means existing temporary output, not permanent storage
- force: false only; force/dedup and Drive values fail validation (422)

Malformed input returns 422; unsupported platform/URL form returns the existing domain
error (400). Either failure creates no jobs. Submitted URLs retain identity queries only.
No network resolution occurs before submission returns. Response:
```json
{"jobs":[{"id":"uuid","status":"queued"}]}
```
Response describes submission state; polling may already show running work. Duplicate
URLs create separate jobs; no history/dedup decisions are made. GET downloads/{id} and
the broader behavior below remain planned; use GET jobs/{id} in Phase 05.

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
GET `/videos`
GET `/videos/{id}`
PATCH `/videos/{id}`
DELETE `/videos/{id}/file`
DELETE `/videos/{id}/history`
DELETE `/videos/{id}/all`
POST `/videos/{id}/redownload`

## Collections
GET/POST `/collections`
POST `/collections/{id}/videos/{video_id}`
DELETE `/collections/{id}/videos/{video_id}`

## Tags
GET/POST `/tags`
POST `/videos/{id}/tags/{tag_id}`
DELETE `/videos/{id}/tags/{tag_id}`

## Storage
GET `/storage/providers`
GET `/storage/status`

Google Drive connection routes are introduced only in Phase 08.

## Batch
POST `/sources/resolve`
POST `/sources/batch-download`

Input must express requested sorting/filtering, while adapter reports supported capabilities.

## Editor
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
