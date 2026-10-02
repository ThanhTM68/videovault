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
FFmpeg/ffprobe are needed in later media phases. Docker is not required.
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

Phase 02 adds the V1 database schema, migrations, and persistence repositories.
Media directories remain empty; download/storage operations are later phases.
The next planned phase is **Phase 03 — Download Engine Core**.

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
| `DOWNLOAD_MAX_HEIGHT` | `1080` | 1–1080; reserved for downloader phases |
| `DOWNLOAD_CONCURRENCY` | `3` | Positive integer; reserved for queue phases |
| `FRONTEND_ORIGIN` | `http://127.0.0.1:5173` | One HTTP(S) origin, no credentials/path/query/fragment |

Relative storage/database paths resolve against the repository root; absolute paths
remain absolute. Startup does not create directories or migrate/open a database. `STORAGE_PROVIDER`
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
