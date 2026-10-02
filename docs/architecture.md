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

Interface concept:

- resolve_url(url) -> NormalizedVideo
- list_source(source, options) -> list[NormalizedVideo]
- get_formats(video) -> formats
- build_download_request(video, options)
- execute_download(request, progress_callback)

Platform-specific quirks belong in adapters.

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
