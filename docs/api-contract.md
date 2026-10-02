# API Contract

Base: `/api/v1`

## Health
GET `/health`

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

Paginated lists:
- items
- page
- page_size
- total
