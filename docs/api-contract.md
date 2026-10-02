# API Contract

Base: `/api/v1`

## Health
GET `/health`

Returns HTTP 200 with `{"status":"ok"}`. This reports application-process health;
it does not check database, storage, or external media services.

## Resolve
POST `/videos/resolve`
Body:
- url

Returns normalized metadata and downloaded-state summary.

## Download
POST `/downloads`
Body:
- urls[]
- max_height
- storage_target
- force

Returns created job IDs.

GET `/downloads/{id}`

## Jobs
GET `/jobs`
GET `/jobs/{id}`
POST `/jobs/{id}/cancel`
POST `/jobs/{id}/retry`
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
