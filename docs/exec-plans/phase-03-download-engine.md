# Phase 03 — Download Engine Core

## Goal
Create platform-independent downloader contracts and an isolated yt-dlp core.
The service must resolve and download through a test adapter into temporary storage,
then validate actual media before reporting completion.

## Model
gpt-6.1-sol high.

## Non-goals
No complete platform adapters, crawling, API endpoints, DB writes, queue, library,
Drive, batch, editing, hashing/dedup, or similarity features.

## Relevant docs and current state
Read AGENTS.md, .agent/PLANS.md, product-spec, architecture, database, api-contract,
downloader, and storage docs. Phase 02 is committed; the Phase 03 branch is clean.
FastAPI/AppError, settings, SQLite models/repositories, and migration tests exist.
Services have no downloader/media implementation. FFmpeg and ffprobe are available.

## Decisions recorded before implementation
- Identity: reuse the DB Platform enum. Detection returns `unknown` for other hosts,
  without extending persisted enums. Unknown platforms fail before extraction.
- Security: HTTP(S) URLs only; no credentials, malformed hosts, local paths, or
  custom extractor/options dictionaries. No browser cookies, netrc, authentication,
  DRM, private-content bypass, or playlist traversal. Raw diagnostics use a bounded
  scalar allowlist; signed URLs, headers, tokens, and extractor messages are omitted.
- Platform boundary: a small resolve/get_formats/download protocol with capabilities;
  one generic yt-dlp adapter. Host detection is not a claim of tested site support.
- Storage: output_directory must lie within TEMP_STORAGE_ROOT. Each invocation owns
  a UUID directory and safe bounded filename. Success stays temporary; failure
  removes only that invocation's directory. Never infer history from filenames.
- Quality: highest known video height <= configured/requested maximum (default1080),
  then fps/bitrate, then container/codec compatibility. Unknown heights and DRM
  formats are ineligible. Separate audio/video is merged without re-encoding.
  With audio enabled a usable audio stream is required; disabled audio uses video-only
  formats (no implicit audio stripping/transcode). No fallback above the cap.
- Containers: prefer MP4 at equal quality; merge/remux using yt-dlp/FFmpeg. Failure
  to remux incompatible source codecs is a stable failure; no automatic transcode.
- Validation: isolated ffprobe argv invocation, timeout, positive duration/video
  dimensions/size, final cap and requested audio checks. Completion only after probe.
  Security review additionally requires file-only protocols and supported-container
  demuxers so a disguised playlist cannot trigger ffprobe network requests.
- Progress: typed events; finished download hooks mean processing, not completion.
  Callback failures are isolated. Cancellation remains a future boundary extension.
- Errors: extend AppError with safe fixed messages; inherit its existing API envelope
  behavior (400 for these domain errors). No new API status contract in this phase.
- Network: finite 30-second socket timeout, one retry; fresh yt-dlp instance per call.
  CLI/user config is never loaded. CI never contacts supported sites.

## Deliverables and implementation steps
1. Add bounded yt-dlp dependency; normalized models/errors/URL classification.
2. Add protocol, deterministic selector, sanitized metadata, filenames and progress.
3. Implement yt-dlp wrapper and isolated ffprobe; compose a synchronous service.
4. Add fixture/mocked tests, real locally generated media/fake-adapter integration.
5. Run dependency check, pytest, Ruff/format, import and frontend regression checks.
6. Review diff and security boundaries; update relevant docs and acceptance evidence.

## Data/API changes
None. Reuse Platform only; no migration or persistence/route integration.

## Tests
URLs/host boundaries, metadata omissions/redaction, capped quality, split streams,
auth/unavailable/network/postprocess errors, hook isolation, traversal/reserved names,
temp confinement/cleanup, missing tools, invalid files, real local ffprobe/download.

## Acceptance (verified complete)
- [x] Normalized domain types and validated requests: nullable fields, bounded diagnostic
  subset, shared Platform identity, strict capped height/audio/container options.
- [x] URL classification and adapter contract: all target hosts, unknown/spoofed hosts,
  malformed/local/credential-bearing URLs, injectable small protocol/capabilities.
- [x] Isolated yt-dlp metadata/download and stable domain errors: mock extraction/error
  cases and existing API envelope, no imports in routes/repositories/unrelated services.
- [x] Deterministic <=1080 selection and merge support: progressive/split formats,
  no above-cap/unknown-height/DRM fallback, real merge and MKV-to-MP4 remux integration.
- [x] Safe temporary files and normalized progress: traversal/reserved names, UUID
  collision isolation, configured boundaries, failed/invalid/escaped output cleanup,
  callback failure isolation, service-owned completion after validation.
- [x] Real ffprobe validation and fake-adapter end-to-end download: generated MP4,
  missing/empty/non-media, malformed/timeout/missing-tool failures, final height/audio,
  cover-art rejection, disguised playlist rejected without embedded HTTP requests.
- [x] Deterministic tests, dependency check, Ruff/format, imports, frontend regression:
  results recorded below.
- [x] Security/diff review; no Phase 04+ implementation or tracked secrets/media.

## Verification evidence
- Backend editable install succeeded; yt-dlp 2026.8.19 with bounded dependency only.
- `python -m pip check`: no broken requirements.
- Full `pytest -q`: **219 passed**, 1 existing Starlette TestClient HTTPX deprecation
  warning, 18.63 seconds; no skipped local-media integration tests.
- `ruff check .`: passed. `ruff format --check .`: 65 files formatted.
- Application, downloader, and probe imports passed from repository root.
- Frontend `npm test`: **7 passed** across 2 files.
- Frontend `npm run build`: Vue/TypeScript typecheck and Vite build passed.
- Real locally generated media/fake adapter, yt-dlp loopback merge/remux, and ffprobe
  embedded-network rejection all ran. No public-platform requests or live check.
- `git diff --check`, final diff/status, dependency/import/subprocess/path/secret audit
  passed. Data directories retain only .gitkeep; no secrets/media/artifacts tracked.

## Known limitations
Unknown heights are rejected; audio disabled requires video-only formats; incompatible
codec/container remuxes fail without transcode. Per-stream percentage may reset. Successful
temporary output must be consumed/deleted by the caller; failed cleanup is logged safely.
Extractor auth/availability message classification is heuristic where structured errors
are absent. Platform-specific and live-site behavior is not certified in this phase.

## Rollback
Revert only Phase 03 files/dependency/docs. No database migration or data change.
Successful temporary output is caller-owned; no automatic production storage move.

## Deferred Work
Phase 04 platform adapters; profile/channel discovery; Phase 05 persistent queue,
cancellation/concurrency; history/dedup; Drive; batch; editor; similarity; live-site
certification; cookie/session configuration; codec normalization and unknown heights.

## Progress
- Inspected current repository and recorded decisions above before code changes.
- Implemented downloader contracts, wrapper, selection, temp handling, progress, and probe.
- Added shared generated-media fixture in tests/conftest.py, synthetic metadata/helper,
  and three test modules; no test-only adapter enters production selection.
- Completed deterministic/local integration, backend/frontend verification and review.
- Phase 03 complete. Next: Phase 04 — Platform Adapters; not implemented here.
