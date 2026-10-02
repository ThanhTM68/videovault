# Phase 04 — Platform Adapters

## Goal
Add adapters for prioritized public-content sources.

## Model
gpt-6.1-sol high.

## Priority
1. YouTube
2. TikTok
3. Douyin
4. Instagram
5. Facebook

## Non-goals
No queue/workers, persistence/history/dedup/library, crawling/profile listing, batch,
Drive, editing, discovery, similarity, AI, automation, new API routes or frontend UI.
No authentication, CAPTCHA, anti-bot, signature, DRM or private-content bypass systems.

## Relevant docs and current state
Read AGENTS.md, .agent/PLANS.md, product-spec, architecture, downloader, database,
api-contract. Phase 03 is committed and merged; phase/04-platform-adapters is clean.
Existing DownloaderAdapter contract: resolve/get_formats/download plus capabilities.
Generic YtDlpAdapter, normalized domain types, capped selection, temp workspaces,
progress/error handling, and ffprobe are implemented. The service maps all platforms
to one generic adapter; there are no platform policies yet. No schema change is needed.

## Decisions before implementation
- Keep the Phase 03 adapter protocol unchanged. Add only an internal immutable
  ExtractionPolicy (allowed extractor names and metadata-normalizer callback) for the
  shared wrapper. No API-facing extractor/options dictionary is introduced.
- Add five thin adapters using a shared implementation and central AdapterRegistry.
  Preserve explicit injected adapter mappings for test/custom integration. Default
  service routing now uses concrete adapters; capabilities are available internally.
- URL shape/host allowlists belong to adapters; reject profile/channel/playlist/tag/
  search/story inputs before network work. Watch URLs with a video ID and playlist
  query are treated as that single video, never a playlist. No new generic HTTP client.
- Narrow supported hosts to actual platform hosts. Core HTTP(S) syntax validation and
  hostname classification remain unchanged. Localhost/IP/private/link-local inputs
  cannot select a production adapter; no DNS-rebinding gateway is attempted.
- Limit yt-dlp extractor selection per platform; reject foreign/generic extractor
  results and cross-platform canonical pages. Short TikTok links use its native
  redirect extractor. Douyin short links and fb.watch are not enabled where the
  installed extractor requires Generic; detection alone is not supported extraction.
  Redirects/CDN requests remain yt-dlp-owned; this is not complete DNS/IP enforcement.
- Reuse centralized normalization/redaction. Adapter normalization preserves exact
  string IDs (integer IDs converted without float coercion), canonical video pages,
  UTC timestamp-to-date fallback, nullable counts/duration/dimensions/creator fields.
  YouTube favors stable channel identity; TikTok/Douyin prefer display creator name
  and uploader ID; Instagram/Facebook keep their own independent identity policies.
  A resolved TikTok short link with only a numeric video ID uses the native
  /share/video/ID canonical form; no username or creator identity is invented.
- All multi-entry/playlist/live/DRM results fail; no carousel unwrapping or recursion.
  Policy validation runs again on refreshed metadata immediately before downloading.
- Installed TikTok extractor contains an automatic challenge-cookie solver. A small
  guarded extractor in the yt-dlp wrapper blocks that hook with AuthenticationRequiredError
  when the TikTok adapter requests it. It does not solve challenges or load credentials.
  The unconfigured generic core also installs the guard so explicit core callers cannot
  accidentally retain the old challenge path. Other platform policies do not load TikTok.
  This library hook is version-sensitive and receives an explicit regression test.
  Pin the existing yt-dlp dependency to the installed/tested 2026.8.19 release because
  the guard depends on its challenge hook; future upgrades require review and tests.
- Keep max-height selection, temp ownership/cleanup, progress and probing entirely in
  the core/service. No platform-specific quality or filesystem code is added.
- Extend centralized stable error classification for age/account restrictions and
  common removed-video failures. No raw extractor error reaches callers/logs.
- Phase 03 loopback core integration will explicitly inject YtDlpAdapter: its synthetic
  Fixture extractor is intentionally not a production YouTube extractor. Preserve all
  its existing media/progress assertions; add separate concrete-adapter integration.

## Deliverables and implementation steps
1. Add extraction policy seam, restricted extractor selection and challenge guard.
2. Add common adapter, five URL/normalization policies, registry and service capabilities.
3. Add small sanitized fixtures per platform; routing, metadata, security/failure tests.
4. Verify adapters through the existing download/probe flow with local generated media.
5. Run full backend checks and frontend regression; inspect fixtures and final diff.
6. Update relevant docs and explicitly check acceptance with actual evidence.

## Data/API changes
None; existing Platform identities and internal model fields remain compatible.
No DB records, new dependency packages, new settings, API endpoints, or frontend changes.
The existing yt-dlp dependency is pinned to the verified version for the safety guard.

## Test plan
Fixture normalization for all platforms; common URL variants; precise IDs, dates,
nullable counts/creator fields; registry/capabilities; cross-platform/generic extractor
rejection; profile/playlist blocking; local/unsafe URL rejection; restriction and changed
extractor errors; no mutable shared state; challenge guard; refreshed-metadata policy;
quality/probe/temp integration using synthetic extractor responses and local media.
CI never contacts public platforms. Optional metadata-only live checks are separate.

## Acceptance (verified complete)
- [x] Five concrete adapters with correct platform identity and unchanged common contract.
- [x] Supported individual URL forms select exactly one adapter; unsafe/unknown inputs
  and profile/channel/tag/story/search/playlist pages fail before extractor construction.
- [x] Fixtures normalize consistently with precise string IDs, integer counts, UTC dates,
  canonical pages, source-specific creator fields, nullable optional data and bounded redaction.
- [x] Shared yt-dlp delegation and internal service capabilities; no duplicated format,
  temp/progress/probe logic or FastAPI/persistence coupling inside adapters.
- [x] Profile/playlist/multi-entry protection; resolve/download only, with all listing,
  sorting and filter capabilities false. Refresh checks prevent extractor/identity changes.
- [x] Restrictions fail safely; real TikTok library challenge path rejected without cookies,
  stable auth/unavailable/network/postprocess errors, no credential loading or message leakage.
- [x] Deterministic tests including all Phase 03 regressions and real local probe/merge/remux
  validation pass. Each platform runs through the service with mocked transfer and real probe.
- [x] Dependency, Ruff/format, application/adapter imports and frontend regression pass.
- [x] Fixtures/security/diff reviewed; no Phase 05+ work or tracked media/secrets.

## Verification evidence
- Backend editable install succeeded; existing yt-dlp package pinned to **2026.8.19**.
- `python -m pip check`: no broken requirements.
- Full `pytest -q`: **300 passed**, 1 existing Starlette TestClient HTTPX deprecation
  warning, **20.42 seconds**, no skips. Includes 81 platform tests and 219 existing tests.
- `ruff check .`: passed. `ruff format --check .`: **74 files** formatted.
- Application, service and AdapterRegistry imports passed from repository root;
  default internal capability report has all five platforms.
- Frontend `npm test`: **7 passed** across 2 files. `npm run build` (runs
  `npm run typecheck`/vue-tsc first): TypeScript check and Vite build passed.
- Real local-media integration, core loopback merge/remux, missing-tool/failure paths,
  extractor allowlisting, and real TikTok challenge-path rejection ran without public-site
  requests. Optional live checks were not performed for any platform.
- Manually inspected all five synthetic metadata fixtures: small, no credentials,
  sensitive query parameters, auth headers, real account data, or huge extractor dumps.
- Final source/diff review confirmed yt-dlp imports stay in its wrapper, no new direct
  HTTP client/subprocess path, no DB/API/frontend implementation, and no Generic production
  fallback. `git diff --check` passed; data directories retain only .gitkeep files.

## Known limitations
- Live extractor compatibility is unverified for all platforms; support is conditional on
  publicly resolvable content through the pinned downloader, not permanent availability.
- Douyin short links and fb.watch remain unsupported; recognized host labels do not imply
  implemented extraction for every path. Photos/carousels/live streams are not supported.
- TikTok challenge rejection depends on a version-sensitive library hook. Review before
  upgrading the pinned version; restricted sources fail instead of attempting a workaround.
- Error-text classification remains heuristic where yt-dlp lacks structured restriction
  types; source changes can affect categories without exposing raw failures.
- Allowlisting/extractor checks do not enforce all redirect/CDN DNS/IP destinations or
  prevent DNS rebinding; stronger transport enforcement is intentionally outside this phase.
- Phase 03 unknown-height, audio-disabled/video-only, remux compatibility, and temporary
  output ownership constraints remain. The existing TestClient deprecation warning remains.

## Rollback/recovery
Revert Phase 04 adapter/policy/service/tests/docs changes. No migration or data cleanup
is needed; temporary storage ownership and cleanup remain the Phase 03 contract.

## Deferred work
Persistent queue; batch/profile listing; history/dedup; library; Drive; editor; discovery;
similarity; automation; live-site certification; authenticated sessions; broader URL forms,
safe short-link handling where native extraction is absent; transport/DNS enforcement.

## Progress
- Inspected repository, installed extractor behavior, and recorded decisions before code.
- Implemented five adapters, shared policy normalization, registry, internal capabilities,
  restricted yt-dlp selection and challenge rejection without replacing core contracts.
- Added synthetic platform fixtures and targeted routing/metadata/failure/security tests;
  retained core-only loopback integration via explicit adapter injection and all assertions.
- Reviewed nullable short-link metadata and added canonical native share/video fallback.
- Completed backend/frontend verification, fixture/security review and documentation.
- Phase 04 complete. Next: Phase 05 — Persistent Queue & Worker; not implemented here.
