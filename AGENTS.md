# VideoVault Repository Instructions

## Mission

VideoVault is a local-first short-video research, download, media-library,
storage, and lightweight editing application.

Primary V1 goal: reliable workflow, not maximum platform count.

Supported-target priority:
1. YouTube / Shorts
2. TikTok
3. Douyin
4. Instagram / Reels
5. Facebook / Reels

## Safety and scope

The application may work with public content or content the user is authorized to store.

Do not implement:
- DRM circumvention
- private-content bypass
- login/access-control bypass
- credential stealing
- CAPTCHA bypass
- platform abuse or evasion systems

Authentication/session support, if ever needed for content the user is authorized to access,
must use explicit user-provided configuration and must never commit credentials.

## V1 stack

Frontend:
- Vue 3
- TypeScript
- Vite
- Pinia
- Vue Router

Backend:
- Python 3.12+
- FastAPI
- SQLAlchemy 2
- Alembic
- Pydantic v2
- SQLite

Media:
- yt-dlp
- FFmpeg
- ffprobe

Testing:
- pytest
- Vitest

## Architecture

Use a modular monolith.

Do not introduce without an explicit later ExecPlan:
- microservices
- Redis
- Celery
- Kafka
- Kubernetes
- PostgreSQL
- cloud LLM dependencies

Important boundaries:
- API routes: transport only.
- Services: business orchestration.
- Repositories: persistence queries.
- Platform adapters: platform/extractor-specific behavior.
- Storage providers: local/Drive-specific behavior.
- Media service: ffmpeg/ffprobe behavior.
- Workers: queued job execution.

Never put yt-dlp calls directly in API route handlers.

Never put Google Drive API logic directly in downloader services.

Never infer download history only from filenames.

## Documentation routing

Read only relevant docs for the task:
- Product behavior: `docs/product-spec.md`
- Architecture boundaries: `docs/architecture.md`
- Database/schema changes: `docs/database.md`
- API changes: `docs/api-contract.md`
- Downloader/platform behavior: `docs/downloader.md`
- Storage behavior: `docs/storage.md`
- Multi-step implementation: `.agent/PLANS.md` and the active file in `docs/exec-plans/`

Do not read every document for a trivial edit.

## ExecPlans

For complex features or significant refactors, follow `.agent/PLANS.md`.
Each implementation phase has an ExecPlan in `docs/exec-plans/`.

Stay inside the active phase.
If you discover future work, document it under Deferred Work rather than implementing it.

## Coding rules

Python:
- Type hints on public functions.
- Use async only where it provides real I/O benefit.
- Keep subprocess execution isolated behind services.
- Do not construct shell command strings from untrusted input.
- Prefer argument arrays for subprocesses.
- Normalize paths with pathlib.
- Explicit error types for domain failures.

TypeScript:
- strict mode.
- Avoid `any` unless justified.
- API response types live in a shared frontend types layer.
- Pinia stores orchestrate UI state; components should not contain backend business rules.

Database:
- migrations required for schema changes.
- SQLite foreign keys enabled.
- uniqueness constraints for identity/dedup keys.
- timestamps stored in UTC.

## Tests

Before completion:
- run backend unit/integration tests relevant to change;
- run frontend tests relevant to change;
- run type checks/lint if configured;
- add regression test for bug fixes;
- test failure paths, not only success paths.

External platform tests must not make the entire test suite depend on live websites.
Use fixtures/mocks for deterministic CI tests.

## Secrets

Never commit:
- OAuth tokens
- cookies
- browser profiles
- API keys
- downloaded private media

Use `.env` locally and maintain `.env.example`.

## Git discipline

One phase per branch:
`phase/NN-short-name`

Do not rewrite unrelated code.
Do not silently change architecture.
At completion, summarize:
- changed files
- tests run
- acceptance criteria
- known risks
- deferred work
