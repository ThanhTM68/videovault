# Database Design

SQLite V1 with SQLAlchemy 2 + Alembic.

## Core tables

### creators
- id UUID/string
- platform
- platform_creator_id nullable when unavailable
- handle/name
- canonical_url
- created_at
- updated_at

Useful unique key where reliable:
(platform, platform_creator_id)

### videos
- id
- platform
- platform_video_id
- canonical_url
- creator_id nullable
- title
- description
- duration_seconds
- upload_date nullable
- view_count nullable
- like_count nullable
- comment_count nullable
- width nullable
- height nullable
- fps nullable
- thumbnail_url nullable
- metadata_json
- discovered_at
- last_refreshed_at

Unique:
(platform, platform_video_id)

### downloads
Represents requested/completed download events.
- id
- video_id
- job_id nullable
- requested_quality
- status
- started_at
- completed_at
- failure_code nullable
- failure_message nullable
- forced boolean
- created_at

History logic should query successful downloads.

### media_files
- id
- video_id
- download_id nullable
- storage_provider
- storage_key/path
- file_name
- mime_type
- size_bytes
- sha256 nullable
- width nullable
- height nullable
- duration_seconds nullable
- kind: original|edited|thumbnail|audio
- exists_last_checked_at nullable
- created_at
- deleted_at nullable

### jobs
- id
- type
- status
- payload_json
- progress_percent
- current_step
- attempt_count
- max_attempts
- error_code nullable
- error_message nullable
- created_at
- started_at nullable
- heartbeat_at nullable
- completed_at nullable
- cancelled_at nullable

### collections
- id
- name
- description nullable
- created_at

### collection_videos
- collection_id
- video_id
Unique pair.

### tags
- id
- name unique

### video_tags
- video_id
- tag_id
Unique pair.

### storage_accounts
No raw OAuth tokens in ordinary columns if secure local token storage is used.
- id
- provider
- display_name
- provider_account_id nullable
- config_json containing non-secret configuration only
- created_at

## V2 tables

### video_stats
Snapshots:
- video_id
- recorded_at
- views
- likes
- comments
- shares nullable

### similarity_edges
- video_a_id
- video_b_id
- visual_score nullable
- audio_score nullable
- text_score nullable
- combined_score
- algorithm_version

### watchlists
### download_rules

## Important semantics

Deleting a physical media file must not automatically erase a video record.

Removing download history may delete/soft-delete the relevant download record
according to implementation, but must not silently delete the file.

Force download creates a new download event.
