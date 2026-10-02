# VideoVault

Local-first short-video research, downloader, library, storage, and lightweight processing app.

This repository is intended to be built phase-by-phase with Codex.

Start with:
`START_HERE.md`

Codex workflow:
`CODEX_SETUP.md`

Project agent rules:
`AGENTS.md`

Phase plans:
`docs/exec-plans/`

Phase prompts:
`prompts/`

## Important

Only download/store media you are authorized to use.
This project must not implement DRM/access-control/private-content bypasses.

## Local development

Requirements: Python 3.12+, Node 22.12+ (Node 24 LTS recommended), npm, and Git.
FFmpeg and ffprobe must be globally installed and available on PATH for downloads and
real local-media integration tests. Docker is not required.
Run the following PowerShell commands from the repository root.

### First-time setup

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e './backend[dev]'
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
Set-Location ..
Set-Location frontend
npm ci
Set-Location ..
```

Copy `.env.example` only if you do not already have a `.env` file. Do not commit
local configuration or credentials. Virtual environment activation is optional;
these commands use its Python executable directly to avoid PowerShell policy issues.

### Start the backend

In the first terminal, from the repository root:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m app.main
```

The default API is http://127.0.0.1:8000. Health is available at
http://127.0.0.1:8000/api/v1/health and returns `{"status":"ok"}`.
Interactive API docs are at http://127.0.0.1:8000/docs.
`APP_HOST`, `APP_PORT`, and `APP_ENV` load from the root `.env` regardless of
the working directory; process environment variables take precedence.
Development mode enables automatic reload.

### Start the frontend

In a second terminal, from the repository root:

```powershell
Set-Location frontend
npm run dev
```

Open http://127.0.0.1:5173. The shell checks backend connectivity and offers a
retry button. Vite proxies `/api` to `APP_HOST`/`APP_PORT` from the root `.env`,
defaulting to `127.0.0.1:8000`. Restart Vite after configuration changes.
The development proxy avoids the need for cross-origin browser permissions.
Health requests time out after five seconds.

### Verification

Backend, from the repository root:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m ruff format --check .
```

Frontend, from the repository root:

```powershell
Set-Location frontend
npm run typecheck
npm test
npm run build
```

Frontend dependencies are locked in `frontend/package-lock.json`; use `npm ci`
for repeat installs. Python dependency bounds live in `backend/pyproject.toml`.
The production build is a compilation check; production API serving/routing
will be designed in the release phase. `npm run preview` has no API proxy.

Phases 03–04 add the internal download engine and five platform adapters, isolated yt-dlp
integration, capped format selection, temporary downloads, and ffprobe validation.
Phase 05 adds durable download submission, polling, cancellation, retry and pause/resume
APIs with a SQLite queue and in-process workers. Outputs remain temporary; history,
dedup and storage/library integration are deferred.
Phase 06 adds Dashboard, Quick Download and Queue, with typed API calls, optional
single-video metadata preview, job progress/actions and authoritative pause state.
The next planned phase is **Phase 07 — Library, History & Dedup**.

### Frontend workflow

Open Quick Download, paste 1–100 URLs (one per line), choose a maximum height
(1080p by default), container and audio setting, then create jobs. Blank lines and
identical repeated lines are removed within the paste; this does not check history.
Preview is optional and available for one URL. Missing metadata/thumbnail is normal.
Storage and force controls are deferred; successful outputs remain temporary.

Queue shows paginated jobs, status filters, progress, timestamps and safe errors.
Cancel queued/running jobs; running cancellation waits for worker acknowledgement.
Retry failed jobs only while attempts remain. Pause stops new claims and leaves
active jobs running; reload reads the backend flag, while backend restart resets it.
Dashboard shows global job counts and five recent jobs, not library/history counts.

Dashboard and Queue share one polling owner: two seconds with queued/active work,
ten seconds when idle or unavailable. Global counts refresh every ten seconds and
after actions/manual refresh; separate queries may briefly reflect different moments.
Navigation stops polling. Failed reads preserve loaded data and offer Refresh.
The connection indicator offers a health retry when the backend is unavailable.

### Backend foundation configuration

All settings load from the root `.env`, with process environment variables taking
precedence. Invalid settings fail during application creation; diagnostic text
does not include submitted configuration values. `create_app(settings)` accepts
explicit validated settings, and `app.api.dependencies.get_settings` supports
normal FastAPI dependency overrides without a global settings cache.

| Variable | Default | Validation/behavior |
|---|---|---|
| `APP_ENV` | `development` | `development`, `test`, or `production` |
| `APP_HOST` | `127.0.0.1` | IP address or hostname |
| `APP_PORT` | `8000` | 1–65535 |
| `DATABASE_URL` | `sqlite:///./data/videovault.db` | SQLite path resolved against repository root |
| `LOCAL_STORAGE_ROOT` | `./data/downloads` | Nonempty path |
| `TEMP_STORAGE_ROOT` | `./data/temp` | Nonempty path |
| `THUMBNAIL_STORAGE_ROOT` | `./data/thumbnails` | Nonempty path |
| `DOWNLOAD_MAX_HEIGHT` | `1080` | 1–1080; download selection and final probe ceiling |
| `DOWNLOAD_CONCURRENCY` | `3` | Positive integer; in-process download worker count |
| `FRONTEND_ORIGIN` | `http://127.0.0.1:5173` | One HTTP(S) origin, no credentials/path/query/fragment |

Relative storage/database paths resolve against the repository root; absolute paths
remain absolute. App construction is lazy; normal startup opens the migrated database
for recovery, but does not migrate or create storage directories. `STORAGE_PROVIDER`
and Google Drive placeholders in `.env.example` remain unused.

Application log level is DEBUG in development and INFO in test/production, using
timestamp, level, module, and message. Unexpected errors log their exception class
and stack locations without exception text, request content, or local variables.
Public errors are defined in the API contract. CORS allows only `FRONTEND_ORIGIN`
and does not enable credentials. Its protocol-level rejected preflight response
is the standard middleware response rather than an application error envelope.

### Database migrations

From the repository root:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m alembic current
..\.venv\Scripts\python.exe -m alembic check
```

The default database is `<repository>/data/videovault.db`, regardless of the working
directory. For another SQLite file, set `DATABASE_URL` in the root `.env` to a relative
path or an absolute path such as `sqlite:///D:/VideoVault/data/videovault.db`.
Its parent directory must exist. URL query options/SQLite URI filenames are unsupported.
Application startup does not run migrations; health remains process-only.

After changing model definitions, create and review a development migration:

```powershell
..\.venv\Scripts\python.exe -m alembic revision --autogenerate -m 'Describe schema change'
..\.venv\Scripts\python.exe -m ruff format alembic
..\.venv\Scripts\python.exe -m ruff check alembic
..\.venv\Scripts\python.exe -m alembic upgrade head
```

Review generated constraints and deletion rules; Alembic autogeneration cannot detect
every semantic change. Never delete/recreate the DB as the normal migration workflow.
The initial `downgrade base` drops all V1 data: use only a temporary test DB or an
explicitly intended rollback with a backup. The tests verify upgrade/downgrade/upgrade,
CLI commands from another cwd, and schema/model parity on isolated temporary DBs.

Repositories receive a Session, flush writes, and never commit. Services own explicit
commit/rollback. The request dependency closes sessions and rolls back unfinished work.
`docs/database.md` documents UTC timestamps, UUIDs, enum checks, and deletion rules.

### Persistent queue (Phase 05)

Run `alembic upgrade head` before starting the app (including existing Phase 02 databases:
0002_queue is additive). Use one backend process; multiple uvicorn workers are unsupported.
The app starts DOWNLOAD_CONCURRENCY worker threads (default 3) after stale-job recovery.
Submission validates the entire batch before one commit and returns quickly without
waiting for network/media operations:

```powershell
$body = '{"urls":["https://www.youtube.com/watch?v=YOUR_PUBLIC_VIDEO_ID"],"max_height":1080}'
$submitted = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/downloads -ContentType application/json -Body $body
$jobId = $submitted.jobs[0].id
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/jobs/$jobId"
```

Replace the example with public content you are authorized to store. Submit 1..100 URLs;
container defaults to mp4 and audio to true. Only storage_target=local and force=false
are accepted. Here local means existing TEMP_STORAGE_ROOT output, not a permanent library.
The 202 response is {jobs:[{id,status:"queued"}]}; poll GET jobs/{id} or GET jobs (optional
status/type/page/page_size). Jobs exclude URLs, internal payloads and result paths.

POST queue/pause stops new claims; active work continues. POST queue/resume resumes;
pause is runtime-only and restart resumes automatically. POST jobs/{id}/cancel immediately
cancels queued jobs; active jobs retain running state with cancel_requested_at until
cooperative execution and safe workspace cleanup finish. Blocking network/FFmpeg can
delay acknowledgement. POST jobs/{id}/retry accepts failed jobs only; attempt_count means
started attempts, with max_attempts=3 total. No automatic retry of download failures.
Unknown jobs return 404, invalid operations 409, invalid/unsupported future options 422.

An independent supervisor writes heartbeats every 5 seconds. At startup and periodically,
orphaned running jobs with heartbeat older than 60 seconds requeue when attempts remain,
otherwise fail with WORKER_LOST. Pending stale cancellation becomes cancelled. Fresh work
stays running until stale; locally executing attempts are never requeued concurrently.
Graceful shutdown stops claims, signals cancellation and joins for up to 5 seconds;
blocked daemons retain supervision/DB ownership until they return. A pending short DB
operation also has SQLite's finite lock timeout. Forced termination uses recovery.

Completed media stays in checked UUID temporary directories. No job output-path API,
permanent storage or history entry is implemented yet. Process crashes may leave orphaned
temporary workspaces; garbage collection is deferred. No live-site tests are required;
queue tests exercise real validation with generated media and controlled fake adapters.

### Download engine and platform adapters (Phases 03–04)

The service is an internal Python interface; calls perform blocking network/media I/O.
From `backend/`, code can construct it using explicit centralized settings:

```python
from app.core.config import Settings
from app.services.downloader.service import DownloaderService

service = DownloaderService(Settings())
# Explicit invocation only, using a public video you are authorized to store:
# request = service.prepare_request(public_video_url)
# result = service.download(request, progress=observe_progress)
# result.path is validated temporary output; the caller owns its lifecycle.
```

Outputs go into UUID directories beneath `TEMP_STORAGE_ROOT`, never directly into the
permanent library. Failed downloads clean up their own workspace. Selection prefers the
highest known height within `DOWNLOAD_MAX_HEIGHT` (default 1080), then fps/bitrate and
compatibility. Separate streams merge and containers remux without forced re-encoding.
Unknown heights, DRM, playlists, live streams, and unsupported URLs fail cleanly.
Authentication-required content has no cookie/login configuration in this phase.

`audio_enabled=False` requires video-only input. Incompatible container/codec remuxes
fail; automatic transcoding is deferred. See `docs/downloader.md` for complete policy.

The downloader tests use mocks and generated local media. They also exercise real
yt-dlp/FFmpeg merge/remux over a loopback server, with no requests to public platforms.
Missing media executables produce a clear integration-test skip; installed but broken
tools fail tests. No live-platform availability is required for CI.

The default registry selects concrete YouTube/Shorts, TikTok, Douyin, Instagram, and
Facebook adapters for supported individual URLs. Each delegates to the same core and
exposes resolve/download as implemented capabilities; profile listing, sorting, filtering
and batch workflows remain unsupported. `service.capabilities()` returns internal reports.
Supported URLs are documented in `docs/downloader.md`; profile/channel/playlist inputs
fail before extraction. Douyin short links and `fb.watch` are not enabled in this phase.

Platform support depends on the public source being resolvable through configured yt-dlp.
No current live-site compatibility was verified. Login, private, age/account restrictions,
cookies and challenge requirements return stable errors without bypass. The existing
yt-dlp dependency is pinned to 2026.8.19 to keep its TikTok challenge-rejection guard
reviewable; upgrades require reviewing that hook and rerunning tests. No cookie/browser
session configuration or new scraping dependencies are introduced.
