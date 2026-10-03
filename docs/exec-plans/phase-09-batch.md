# Phase 09 — Batch Channel/Profile

## Goal
Create a capability-aware batch workflow.

## Non-goals
No Editor, Discover, saved sources, subscriptions, schedules, generic crawler or auth bypass.
No new dependency, migration or batch execution engine.

## Starting state / relevant docs
Read AGENTS, PLANS, checklist, product/architecture/database/API/downloader/storage docs.
Clean phase/09-batch starts at 07afd40 with merged Phase 08. Existing immutable
AdapterCapabilities, restricted yt-dlp single-video wrapper, QueueService atomic
submission, identity-based worker dedup and Local/Drive storage remain authoritative.

## Decisions / API and architecture
- Focused SourceService -> SourceAdapterRegistry -> YouTubeSourceAdapter; controlled
  flat metadata listing lives inside the downloader integration boundary. Single-video
  URL validation and adapter contract remain unchanged.
- Exact supported sources: youtube.com/www.youtube.com/m.youtube.com /@ASCII_HANDLE
  (3-30 letters/digits/underscore/dot/hyphen) or /channel/UC + 22 identity characters,
  optionally /videos and trailing slash. Canonicalize to HTTPS www /videos. No playlists,
  shorts/live tabs, search, feeds, arbitrary subdomains or Generic fallback.
- Pinned YoutubeTabIE exposes duration from lengthSeconds/lengthText; dates are absent
  unless approximate_date is enabled and view counts may be rounded public summaries.
  Therefore source/default order and inclusive duration filtering are supported.
  Newest/oldest/views sort and date/view filters stay false and reject explicit requests.
  Source order is never advertised as guaranteed newest or whole-channel ranking.
- Scan first 100 flat entries; N strictly 1-100 limits returned eligible candidates after
  normalization/dedup/filtering. Unknown duration is excluded only when duration filter
  requested and counted. Other nullable metadata remains unknown. Total channel size null.
- Source resolve is read-only, no per-item full resolve, format extraction or DB writes.
  Batch identity flags are one batched DB query, provider-neutral and last-known.
- Bounded in-memory previews (32, ten-minute TTL, random IDs), no raw extractor blobs.
  Submission uses preview ID + stable selected video IDs, verifies membership/canonical
  URLs/options/availability and re-queries successful history before QueueService.submit.
  Consume preview after successful atomic submission (including zero eligible jobs).
  Failed submission can retry; restart/expiry requires new preview. This keeps submission
  free of source network I/O and rejects arbitrary client candidate metadata/URLs.
- Worker dedup remains authoritative for races after pre-dedup. Force permits known
  history but duplicate selected identities still create at most one ordinary job.
- No schema change. Reuse DownloadOptions extracted from existing submission schema.
  POST /sources/resolve and /sources/batch-download only; Batch Pinia has no polling.
  Source/criteria changes invalidate preview; option changes do not re-enumerate.

## Implementation steps
Source URL policy, schemas/errors/adapter/registry and bounded yt-dlp wrapper; batched
repository state query, SourceService and thin routes/app wiring; typed Batch API/store/
view/navigation; deterministic wrapper/API/worker/storage/frontend regressions; docs,
full verification, browser fixture workflow, senior review/fixes, implementation commit,
checklist/evidence commit, branch push and SHA verification, stop.

## Test plan
Strict URL/N/ranges, extractor allowlist, metadata-only bounded iterator, malformed/outside
source candidates, source-order/duplicate identity/duration boundaries and unknowns,
unsupported capability errors, read-only preview and query efficiency, cache expiry/replay/
membership tampering, pre-job history dedup/stale preview/worker race, force, atomic
submission/Drive unavailable, ordinary independent jobs and pause/cancel/retry semantics.
Frontend capabilities, stale/aborted reads, selection/force/options, summary/errors,
network recovery and responsive browser workflow with generated media and fake Drive.

## Rollback / recovery
No schema rollback. Existing jobs are ordinary downloads and keep working. Pending
previews are transient and invalid after process restart, eviction or expiration.
Enumeration uses existing finite socket/retry limits plus 12 transport requests and a
90-second request-start deadline (a current request may use its 30-second timeout).
Two concurrent enumerations maximum; no persistent crawl or resume.

## Deferred work
Phase 10 Editor, 11 Hardening/release, 12 Discover, 13 Similarity/quality, 14 Watchlists/rules.
Broader sources, reliable alternative sort/metadata providers and multi-process previews.

## Model
gpt-6.1-sol high.

## Input
- profile/channel/source URL
- N
- ordering requested
- optional min/max views
- optional date range
- optional duration range

## Deliverables
- source resolve endpoint
- adapter capability reporting
- preview candidate videos
- batch selection
- dedup before job creation
- enqueue selected videos
- clear unsupported-filter messages

## Rule
Do not fake sorting if source metadata/API does not support it reliably.

## Tests
Use deterministic source fixtures.
Test N limits, filtering, duplicate skipping, unsupported capability.

## Acceptance
At least one strong adapter (YouTube first) supports complete preview-to-batch workflow.
Other adapters degrade honestly according to capabilities.

## Final review and fixes (2026-10-03)

Performed the senior backend/integration/security review equivalent to
prompts/REVIEW_CURRENT_PHASE.md against actual staged code, schemas, routes, source
wrapper/adapter, QueueService/worker/library/storage boundaries, frontend lifecycle,
tests and documentation. No remaining in-scope correctness/security/data-integrity gap.

Review-driven fixes and regressions:
- Vue number inputs coerce N to number; use a string-or-number ref and explicit String
  conversion to avoid a browser crash after changing N. Invalid/fractional/blank cases pass.
- Reject numeric timestamp dates; require YYYY-MM-DD. Bound each selected ID to exactly
  11 safe characters, as well as the 100-selection limit and cached membership check.
- Bound transport attempts and request-start deadline to prevent empty continuation
  pages from producing an unbounded scan. Real pinned extractor allowlist/renderer tests
  verify YoutubeTab-only loading, flat duration and absent approximate dates/formats.
- Preserve source-channel identity when canonical metadata uses a handle URL, while
  rejecting mismatched handles/channel IDs and outside-source candidates.
- Suppress stale read/submission results across criteria changes/navigation; abort reads
  on unmount, block duplicate pending actions and never synthesize completed/history state.
- Wrap long channel titles; show explicit Already downloaded badge and backend history
  flags. Force toggles eligibility without enumerating again or overwriting old files.
- Verify one-query history lookups, rollback after a second job insert, concurrent preview
  replay, maximum 100-job batch, delete-file/remove-history independence, failed-only retry,
  cancellation and failure isolation, including concurrent fake-Drive worker completion.

Security/diff review PASS: exact source host/path recognition, restricted extractor family,
no Generic/search/feed/crawler/login/cookie/credential additions; candidate canonical URL
and known-source identity validation; bounded safe metadata without raw formats/headers/
stream leakage; SQLAlchemy bound queries, no shell or Google logic in source services;
escaped Vue text and safe image handling. All eligible jobs use existing atomic submit,
state machine, worker race dedup and storage. No migration/dependency or Phase 10+ changes.
Staged credential signature scan and forbidden artifact scan both returned zero matches.
All 32 staged files are current-phase implementation/tests/docs; no DB, media, cache,
temporary helper, build output, secrets or unrelated changes. Owned local servers stopped.

## Final acceptance

| Criterion | Result / evidence |
|---|---|
| Source resolve | PASS - exact URL policy, thin real API, safe stable errors |
| Capability reporting | PASS - frozen capabilities; truthful listing/duration only |
| YouTube source workflow | PASS - preview -> jobs -> worker -> Local/Drive -> Library/History |
| Candidate preview | PASS - read-only, nullable safe metadata, bounded snapshots |
| N limit | PASS - strict 1-100; 100-entry scan/result/selection bounds |
| Supported ordering | PASS - unchanged source order explicitly labeled |
| Unsupported ordering rejection | PASS - newest/oldest/views reject before I/O |
| Supported filters | PASS - inclusive duration, zero bounds and unknown exclusion |
| Unsupported filter rejection | PASS - views/date reject before I/O |
| Candidate identity dedup | PASS - stable identity, repeated entries/selections collapse |
| History pre-dedup | PASS - one fresh query before jobs, independent of file presence |
| Force batch | PASS - real new events/files, duplicate selection still collapses |
| Batch selection | PASS - cached membership, strict IDs, expired/replayed/tampered errors |
| Queue integration | PASS - atomic ordinary jobs; pause/cancel/failed-only retry/race tests |
| Local storage regression | PASS - full prior tests and generated-media browser workflow |
| Drive storage regression | PASS - deterministic provider worker tests and browser workflow |
| Frontend Batch UI | PASS - typed API/store, capability controls, stale/offline/reload guards |
| Phase 10+ excluded | PASS - no Editor/V2, schedules, subscriptions or future branch |

## Final verification evidence

Commands from backend use `..\.venv\Scripts\python.exe`; frontend commands use npm:
- `python -m pytest -q`: **533 passed, 1 skipped**, 86.50 seconds. The existing Windows
  symlink-creation skip requires developer mode/privilege; deterministic containment
  regressions pass. One existing Starlette/httpx deprecation warning.
- `python -m pytest tests/test_sources.py -q`: **100 passed** (deterministic, no live sites).
- `python -m ruff check .`: PASS; `python -m ruff format --check .`: **125 files** formatted.
- `python -m pip check`: no broken requirements. Application factory/OpenAPI import PASS,
  29 actual API paths; only two source routes added.
- `python -m alembic heads`: **0003_library**. Fresh isolated temporary DB with
  `alembic upgrade head`, `alembic current`, `alembic check`: PASS, no schema differences.
  Full tests also cover upgrade/downgrade/reupgrade, FKs and earlier data preservation.
- `npm run typecheck`, `npm test`, `npm run build`: PASS; **102 frontend tests** across
  11 files. No lint script is configured; no dependency/lockfile changes.
- `git diff --check` and `git diff --cached --check`: PASS.

Deterministic browser workflow PASS against real Vite/FastAPI/SQLite/worker/provider
code with injected source/downloader and fake Drive, generated FFmpeg media, and an
existing successful history fixture. Verified duration preview changes, history-disabled
selection, ordinary job counts, Queue pause/resume, 1 Local + 2 Drive + 1 Force jobs,
4 Library videos and 5 History events; Force preserved the earlier local file. Unsupported
ordering bypass requests and unsupported TikTok listing return explicit errors. Offline
preview clears stale candidates, online retry recovers, reload restores no invented
preview/history state. No browser page errors or horizontal overflow at desktop 1440px
or narrow 390px, including long channel title, selection controls and submission summary.
Screenshots visually inspected; runtime DB/media/credentials/screenshots outside Git.

Browser plugin initialization failed before connection with Windows os error 3; installed
standalone Edge/Playwright performed the checks. Temporary harness fixes corrected its
async job wait and a serial-only fake-Drive global pool assertion that is invalid when
another worker/API owns a different transaction; production code was unaffected. Helpers
were removed. Final screenshots: temporary videovault-phase09-ui-D4l6eU directory.
Live YouTube/real Google smoke: **NOT RUN - deterministic fixtures are acceptance evidence**.

Known limitations: /videos-only YouTube listing, first-100 scope, nullable metadata,
rounded public views unsuitable for filtering, no guaranteed date/view ordering,
single-process transient previews, finite request-start rather than hard wall-clock
deadline. Aborted UI reads may finish their bounded server enumeration. Existing storage
orphan/last-known-state and transport DNS/rebinding limitations remain documented.

All verifiable implementation requirements and final review pass. **READY TO COMMIT**.
Phase 09 remains unchecked until the implementation commit exists; publish only the
current phase branch, verify full local/remote SHA, then stop without merge or Phase 10.
