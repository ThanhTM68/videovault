# Storage Design

## Goal

Downloader creates/processes media in temporary local space.
Final output is committed through a StorageProvider.

## Local provider

Root configured with:
`LOCAL_STORAGE_ROOT`

Recommended hierarchy:

platform/
  creator/
    YYYY/
      MM/
        filename.mp4

Filename:
`{date}_{videoId}_{shortSlug}_{height}p.mp4`

Do not use unbounded full titles.
Sanitize reserved Windows characters.

## Google Drive provider

Phase 08 introduces:
- OAuth connection setup
- root folder configuration
- nested folder creation/reuse
- upload with resumable behavior where supported
- store Drive file ID as storage key
- upload failure does not destroy local temp file until recovery policy completes

Secrets/tokens:
- never Git
- prefer OS/local secure storage if practical
- otherwise clearly documented local credential file ignored by Git

## Delete semantics

Delete file:
- storage provider deletes object;
- media_files row is marked deleted;
- video/download history remains.

Delete everything:
- storage object deletion;
- relevant history deletion/soft deletion;
- operation should be explicit and confirmable from UI.

## Storage naming

Database IDs are canonical.
Folder and filename organization is for human convenience, not identity.
