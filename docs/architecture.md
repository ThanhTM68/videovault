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
No API endpoint, job/history/media write, or storage move is added.

Phase 04 adds AdapterRegistry and five concrete platform adapters. The existing common
contract is preserved; policies own exact supported URL forms, extractor families,
canonical pages and creator metadata. Registry selection is centralized, and the service
provides internal capability reports. The shared wrapper accepts an immutable trusted
ExtractionPolicy for normalization and restricted extractors; no user option dictionaries.
The TikTok challenge hook is blocked, including for explicit generic core callers.
yt-dlp is pinned to the tested version because this guard needs review on upgrades.

Each operation creates a new YoutubeDL instance; adapters never share mutable extractor
options or credentials. Future workers must run this blocking work outside request
handlers. Profiles/playlist/multi-entry inputs remain rejected; crawling is future work.
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

### Phase 05 implementation

Routes delegate to QueueService -> JobRepository -> SQLite. A submission validates
1..100 independent requests, writes all jobs in one transaction and returns 202 after
commit. No extractor/network I/O occurs in submission. DownloadPayload contains only
identity URL, capped height, container and audio flag; workers validate it again.

The app owns one WorkerManager: recovery runs before starting DOWNLOAD_CONCURRENCY
blocking worker threads (default 3). A separate supervisor maintains heartbeats every
5 seconds and scans for stale orphaned work. No shared Session; reads and conditional
writes each use short sessions, and downloader execution holds no transaction.
SQLite claim is one UPDATE with a candidate subquery and RETURNING. Started-attempt
count fences all worker writes; cancellation/completion/recovery compare current state.

Use one backend process (no uvicorn --workers >1). This is a file-backed SQLite local
queue, not a distributed lease protocol. Application construction remains lazy; normal
lifespan startup requires migrations and opens the DB for recovery. Tests can explicitly
use create_app(start_workers=False) for foundation/transport isolation, never inferred
from APP_ENV. Startup does not migrate/create tables or storage directories.

Pause serializes with claims and leaves active work running; it resets on restart.
Only failed jobs may explicitly retry, up to max_attempts total started attempts (3).
Running cancellation records cancel_requested_at, signals the invocation, and waits for
safe cleanup before cancelled status. Checkpoints surround resolve/probe and download/
postprocessing progress hooks; blocking extraction/FFmpeg can delay acknowledgement.

Stale means last heartbeat (fallback started_at/created_at) older than 60 seconds.
Recovery before startup and every 5 seconds requeues orphaned attempts below the limit,
fails exhausted attempts with WORKER_LOST, and acknowledges stale cancellation requests.
Fresh active rows stay running until a later scan. Periodic recovery excludes locally
executing attempts; heartbeat failure signals their stop, never starts a concurrent copy.

Shutdown stops claims, signals cancellation, and uses a five-second thread join budget
(an outstanding short SQLite operation also has a finite lock timeout). A blocked daemon
keeps the supervisor/engine until it exits; forced termination relies on restart recovery.
Phase 05 originally left completed output temporary; Phase 07 extends this lifecycle
with durable files and transactional media/history writes as described below.

## Phase 06 frontend boundaries

App owns navigation and the existing health indicator; Router selects Dashboard,
Quick Download or Queue. Views own presentation/form input, reusable JobCard and
StatusBadge render backend states, and typed API modules own transport validation.
Download Pinia state handles submission and optional explicit single-video preview.
Queue Pinia state handles paginated jobs, global counts, actions and runtime pause.
No downloader/platform rules, persistence or filesystem access live in components.

Dashboard/Queue each mount the same polling composable, with one shared-store owner.
It waits for each cycle before scheduling the next, aborts reads on unmount, fences
stale responses and preserves cached data on failure. Cadence is 2 seconds with
queued/active jobs and 10 seconds idle/error. Filtered totals supply global counts
every 10 seconds; separate reads are not an atomic snapshot. Latest jobs come from
the final backend page(s), while Queue retains the server's oldest-first ordering.

Mutations use returned server state, per-job busy guards and conflict refreshes.
Pause is read via GET /queue; cancel_requested_at is an in-progress cancellation,
not terminal status. Unknown/reset progress (null or zero) is indeterminate.
POST /videos/resolve delegates through PreviewService to the existing downloader
resolver and projects public metadata only, with no media download or DB writes.
These two additive endpoints require no schema or dependency changes.

## Phase 07 library/history boundaries

Library routes handle transport and delegate to LibraryService. LibraryRepository owns
Video/Creator upserts, bounded search/filter queries, actual attempt events, MediaFile
records and history removal; OrganizationRepository owns collection/tag membership.
LocalFiles isolates managed-root validation, exclusive file copying, unlink and
streaming SHA-256. This is local file lifecycle support, not a Drive/provider registry.

Workers resolve identity before media transfer. They share 256 bounded striped RLocks
with destructive library actions, keyed by `(platform, platform_video_id)`; waiting
workers check their cancellation Event every 100ms. Within the lock a short fenced
transaction upserts metadata and checks completed history. Normal duplicate work skips;
force starts another attempt. The lock spans download/finalization/completion, so two
normal jobs for one identity produce one transfer and one skip. Stripe collisions may
serialize unrelated videos; different identities never dedup by equal bytes. This is
strictly one backend process, not a distributed or multi-process guarantee.

No DB session remains open across media I/O, copying, hashing or file deletion.
After finalization, MediaFile + completed Download + current uncancelled Job commit
atomically. Exceptions/cancellation clean only owned new files and temporary workspaces.
Filesystem and SQLite cannot share a transaction: abrupt crashes/cleanup failures can
leave orphans; failed multi-file deletion can make partial progress but does not erase
history until all file removals succeed. No automatic root sweeping is introduced.

Reads do not wait for the entire download lock. Page/detail snapshots check managed
file presence after closing their read session and reconcile changed missing markers
in a short write. SQL file filtering uses last-known state. Public projections exclude
absolute paths/storage keys. Preview reports known DB flags but never creates history
or metadata. Library and History Pinia stores own typed transport, aborted/stale read
suppression, cached results and explicit actions; components show confirmations and
server state. They add no polling timer. Existing Queue/Dashboard polling remains shared.

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

## Phase 08 provider boundary

StorageService owns a provider registry and put/exists/delete/get_metadata dispatch.
LocalStorageProvider preserves managed-root path checks. GoogleDriveStorageProvider
owns folder/upload/metadata/deletion; DriveConnection owns official SDK OAuth and
private credential files. StorageAccountRepository handles non-secret persistence.
Routes only adapt requests/responses. Downloader/adapters never see Google APIs.
Worker chooses storage after probe, retaining account lease through atomic completion
and compensation. Reads/submission use local snapshots without waiting for upload.
Library deletion is provider-neutral; remote list state is cached and explicit targeted
refresh runs outside DB transactions. Storage Pinia owns configuration/actions; no new
polling timer, cloud queue or multi-process coordination is introduced.

## Phase 09 source and batch boundary

Thin source routes call SourceService, which owns capability validation, bounded preview
cache, normalization/filter orchestration, one-query history flags and pre-job dedup.
SourceAdapterRegistry selects exact source URL policies independently of the single-video
registry. YouTubeSourceAdapter projects safe candidate fields and frozen capabilities;
SourceYtDlp isolates the restricted metadata-only YoutubeTab integration. No Generic
extractor, full single-video resolution per candidate, media transfer or DB transaction
spans source network enumeration. Two previews may enumerate concurrently; requests,
entries, result count, source/selected-ID sizes and cached snapshots are bounded.

Submission revalidates the cached membership/options/provider and fresh identity history,
then uses the existing QueueService atomic transaction. No batch worker type or bypass
of claim/state/cancel/retry/recovery, worker dedup, storage or library recording is added.
The preview lock serializes short submissions and single-use consumption; no source or
Google I/O happens while holding it. Preview is transient and read-only. Existing
SQLite constraints and migration head remain unchanged. Batch Pinia handles stale/aborted
reads, backend-authoritative flags and explicit actions with no polling or persisted
browser state. Future broader sorting requires an adapter contract with explicit
ordering/filter scope and evidence before any capability is enabled.
