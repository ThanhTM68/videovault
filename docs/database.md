# Database Design

SQLite V1 with SQLAlchemy 2 + Alembic.

## Phase 02 persistence conventions

Entity primary keys are UUID4 strings of length 36, generated on insert. Association
tables use composite primary keys. ORM insert defaults supply IDs, timestamps,
empty JSON objects, and initial queued status; raw SQL callers must provide required
values themselves. Engagement counts and file sizes use BigInteger. Unknown duration,
dimensions, counts, creator, and upload date remain nullable. Upload dates use SQL DATE.

All application timestamps must be timezone-aware. `UTCDateTime` normalizes input
to UTC, stores naive UTC in SQLite, and returns aware UTC on load. Naive input is
rejected. Creator `updated_at` changes on ORM updates. Raw SQL writers must obey
the same UTC policy and supply update timestamps explicitly.

String-backed Python enums persist their lowercase values in VARCHAR columns with
named CHECK constraints. SQLAlchemy also validates strings on writes. Platform values
are `youtube`, `tiktok`, `douyin`, `instagram`, and `facebook`; storage providers are
`local` and `google_drive`. Job and download status values are `queued`, `resolving`,
`downloading`, `processing`, `uploading`, `completed`, `failed`, `cancelled`, and
`skipped_duplicate`. Media kinds are `original`, `edited`, `thumbnail`, and `audio`.
This defines storage representation only, not a status transition/worker system.

`metadata_json` and `payload_json` store variable metadata only. Top-level dictionary
changes are tracked; replace a nested structure or the whole dictionary when changing
nested values. Core searchable values stay in ordinary columns.

### Engine, paths, and transactions

`DATABASE_URL` is resolved centrally by the DB layer. The default relative SQLite
path always means repository-root `data/videovault.db`, even from `backend/` or
another cwd. Absolute Windows paths work; SQLite URI filenames and URL query options
are not supported. Custom database parent directories must already exist.

Every connection enables `PRAGMA foreign_keys=ON`. Python 3.12 SQLite uses explicit
transaction mode (`autocommit=False`) so DDL and reads participate consistently in
transactions. Engines connect lazily and are disposed at application shutdown.
In-memory configurations use StaticPool; production and tests normally use files.
Startup and health do not migrate or create schema. Alembic is the schema authority.

Request sessions close and rollback outstanding work. Sessions expire objects on
commit to reload database-driven reference changes. Repositories flush writes but
never commit. Services/application boundaries explicitly commit successful work and
rollback failed work. An IntegrityError requires rollback before session reuse.
All DB tests use temporary databases migrated with Alembic, never the development DB.

### Identity and indexes

`(platform, platform_video_id)` is unique and nonempty. The unique creator pair
`(platform, platform_creator_id)` permits multiple NULL IDs, while duplicate known
IDs within one platform fail. Tag names are unique and case-sensitive in V1.
Association composite primary keys prevent duplicate pairs. Additional indexes cover
foreign-key lookups and reverse association deletion; status/search indexes are deferred.

### Deletion policy

| Deleted entity | Database behavior |
|---|---|
| Creator | Set related video `creator_id` to NULL; retain videos |
| Job | Set download `job_id` to NULL; retain history |
| Download event | Set media `download_id` to NULL; retain media/video |
| Video with downloads or media | RESTRICT deletion |
| Video without downloads/media | Delete its collection/tag associations |
| Collection or tag | Delete association rows only |
| Association | Retain both entities |
| Media record | Retain video/history; never touch physical storage |
| Storage account | Retain media; no account ownership FK exists in this shell |

Database FK rules own these actions. Parent ORM relationships use
`passive_deletes="all"` and no entity delete cascades, including when children are
loaded. Related objects reload on access after commit; explicitly refresh/expire them
to observe database actions before commit. A media record's video and optional download are
separate FKs; future services must ensure they describe the same video when linking.

### History and storage configuration

Successful history means status `completed`, independent of media presence or soft
deletion. Forced downloads are additional events. Removing history preserves files,
and a skipped duplicate is not a successful download event.

Storage-account `config_json` is a non-secret shell. ORM writes accept only flat string
values for `root_path` and `root_folder_id`, including tracked dictionary updates.
Unknown keys, tokens, credentials, and nested values are rejected. This is application
write validation, not credential scanning or an encryption store; direct SQL must obey
the same policy. Provider account IDs are metadata, not OAuth credentials.

### Migrations

Initial revision: `0001_v1`. Revisions contain fixed SQL types/DDL, not calls to current
model `create_all`. Metadata imports do not start the FastAPI application. Alembic
supports SQLite batch migrations for future table alterations. Upgrade/downgrade/upgrade
and metadata parity are tested on temporary databases; downgrade drops V1 records and
must not be used on a populated database without a backup and explicit intent.

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
- attempt_number nullable (0003_library; legacy events remain NULL)
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
- missing_at nullable (0003_library; missing is distinct from deliberately deleted)

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
- cancel_requested_at nullable (0002_queue; request time, distinct from acknowledgement)

### Phase 05 queue extension

Revision 0002_queue adds cancel_requested_at and ix_jobs_queue(type, status, created_at).
0001_v1 is unchanged. Upgrade/downgrade/re-upgrade preserves existing job rows; downgrade
removes request timestamps and the index. Back up real databases before rollback.

QueueService owns commits; repository claims/updates return changed rows. Claim is a
single conditional UPDATE with a queued-candidate subquery, not a read then write or
SELECT FOR UPDATE. Each started claim increments attempt_count; updates compare that
attempt and running status, preventing an old attempt from mutating a replacement.
Completion additionally requires no cancellation request. Recovery rechecks heartbeat,
status, attempt and observed cancellation timestamp to avoid overwriting fresh work.

Existing progress_percent remains nonnullable: unknown/reset is 0, pre-success maximum
99 and successful completion 100. current_step distinguishes validating from processing.
cancelled_at records acknowledgement; completed_at timestamps all terminal outcomes.
Retry clears runtime/error/request fields, retains attempt_count. max_attempts defaults
to 3 total started attempts. Queue pause is runtime state, without a settings table.
Phase 05 originally left validated output temporary. Phase 07 extends the worker with
the durable Video/Download/MediaFile lifecycle below.

### Phase 07 library extension

Revision `0003_library` adds nullable downloads.attempt_number, unique index
ix_downloads_job_attempt(job_id, attempt_number), and nullable media_files.missing_at.
0001_v1 and 0002_queue are unchanged. Existing data remains valid, including legacy
downloads with NULL attempt/job links. Upgrade/downgrade/re-upgrade on populated 0002
data preserves Video, Download and MediaFile links and passes foreign_key_check.
Downgrade drops only the two columns and attempt index; migrations never delete media.

Video identity is `(platform, platform_video_id)`. Metadata upsert uses the existing
DB unique constraint and merges nonempty fields; creators reuse reliable platform IDs.
Creator names without reliable IDs remain metadata, not invented Creator identities.
One Download is inserted per actual resolved job attempt, initially downloading.
requested_quality stores compact JSON: max_height, preferred_container, audio_enabled,
force. Retries produce another event/attempt_number; skipped duplicates and resolution
failures before an attempt starts do not fabricate events. Restart recovery closes
stale execution events as failed (WORKER_LOST) or cancelled in the same job transaction.

After validated output is copied to an exclusive durable name and SHA-256 is streamed,
MediaFile, completed Download and cancellation/attempt-fenced Job completion commit
in one short transaction. Copy/hash/media/delete I/O never holds a DB transaction.
Copy/hash/DB failures or losing cancellation remove owned new output where possible;
no completed event is retained after rollback. Historical success, not file existence
or hash, blocks normal identity downloads. Forced attempts retain older files/events.

History removal hard-deletes Download rows and uses the existing ON DELETE SET NULL
MediaFile.download_id relationship. Video, Creator, MediaFile, tags and collections
remain. File deletion marks deleted_at and keeps history; externally missing files
set missing_at on page/detail checks. Public flags distinguish active file presence
from completed history. File-filter queries use last-known missing/deleted state.

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
