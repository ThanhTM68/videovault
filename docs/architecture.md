# Architecture

## Shape

Modular monolith:

Frontend -> FastAPI -> services -> repositories/providers -> SQLite/filesystem/Drive

Background jobs execute through an in-process worker abstraction in V1.

## Backend modules

Suggested structure:

backend/app/
- api/routes/
- core/
- db/
- models/
- schemas/
- repositories/
- services/downloader/
- services/storage/
- services/media/
- services/library/
- workers/
- main.py

## Dependency direction

Routes may depend on services.
Services may depend on repositories/providers.
Repositories depend on database session.
Adapters/providers do not depend on FastAPI route objects.

Avoid circular imports.

## Persistence foundation (Phase 02)

The application factory owns a lazy SQLite engine and session factory; shutdown
disposes the engine. `app.db.session.get_session` is the request-scoped dependency
and rolls back and closes uncommitted work. No shared mutable Session or automatic
request commit exists. Services own transactions; repositories use SQLAlchemy 2
selects and flush writes without committing. Repositories never touch physical files.

Alembic owns schema changes; application startup does not create tables. Models
import independently of FastAPI startup. All DB tests migrate temporary SQLite files.
See `docs/database.md` for timestamp, identity, enum, history, and deletion policies.

## Downloader boundary

Phase 03 implements `DownloaderAdapter.resolve/get_formats/download` with capability
metadata and a synchronous `DownloaderService.resolve/prepare_request/download` facade.
The service owns URL classification, capped selection, isolated temporary workspaces,
progress safety, failure cleanup, and validation before completion. The yt-dlp Python API
is imported only by its wrapper. Repositories/routes are absent from this execution path.
No API endpoint, job/history/media write, storage move, or platform-specific policy is added.

The generic adapter is shared safely because it has no mutable extractor state; each
operation creates a new YoutubeDL instance. Future workers must run this blocking work
outside request handlers. Platform-specific quirks and crawling belong to later adapters.
See `docs/downloader.md` for internal contracts, quality, authentication, and temp policy.

## Storage boundary

StorageProvider:
- put(local_temp_path, destination)
- exists(identifier)
- delete(identifier)
- get_metadata(identifier)

LocalStorageProvider
GoogleDriveStorageProvider

Database stores storage references, never assumes all files are local.

## Media boundary

MediaService:
- probe
- merge
- transcode
- trim
- crop/resize
- background composition
- text overlay
- speed
- hash

All ffmpeg/ffprobe command construction is isolated here.

Phase 03 implements only `services/media/probe.py`: globally discovered ffprobe,
argv invocation with a timeout, normalized duration/dimensions/size/audio validation.
yt-dlp manages its own FFmpeg merge/remux behind the downloader wrapper. The broader
editing/media operations above are future work; no media binaries are bundled.

## Queue

V1 queue is persistent in SQLite.

Worker:
- polls/claims queued jobs transactionally;
- updates progress;
- writes heartbeat/time;
- records error details;
- supports restart recovery.

Do not require Redis in V1.

## Error categories

Examples:
- UnsupportedPlatformError
- MetadataResolveError
- DownloadUnavailableError
- DuplicateDownloadError
- MediaProcessingError
- StorageError
- AuthenticationRequiredError
- ValidationError

Map domain errors to stable API error responses.
