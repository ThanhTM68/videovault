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
