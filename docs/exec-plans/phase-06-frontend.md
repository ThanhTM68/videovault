# Phase 06 — Frontend Shell, Quick Download & Queue

## Goal
Build usable V1 UI around existing APIs.

## Relevant docs and inspected state
AGENTS.md, .agent/PLANS.md, product-spec.md, architecture.md, api-contract.md,
downloader.md. Clean phase/06-frontend branch; Home route, health Pinia store,
native fetch, plain CSS. Backend has durable submission/jobs/actions but no metadata
preview or authoritative read of runtime pause. Existing job API deliberately hides
payload/URL/path, orders oldest first and supports pagination/status filters.

## Implementation decisions / data and API changes
- Keep Vue/Pinia/Router, native fetch and CSS; no new runtime dependencies.
- Add GET /queue (paused only) and POST /videos/resolve as narrow public metadata
  projection of existing DownloaderService.resolve through a preview service.
  No extraction in routes, media transfer, DB writes, history flags or migration.
  Preview input uses existing URL validation/query sanitation. Thumbnail is optional.
- Dashboard (/ and /dashboard), Quick Download (/download), Queue (/queue).
  Disabled future navigation only. Input/options stay local; submission/preview
  state in download store, shared jobs/actions/pause/counts in queue store.
- Optional explicit single-URL preview; multiple URLs show count/list and submit
  directly. Trim lines/ignore blanks, remove identical duplicate lines within this
  paste (not history dedup), enforce 1..100 and basic HTTP(S) feedback only.
- Use typed /api/v1 client with safe normalized HTTP/network/invalid response errors,
  finite timeout, AbortSignal support. No raw payload dumps or v-html.
- One page-owned polling loop in shared queue store; 2 seconds while active/queued,
  10 seconds idle/error. Abort reads and clear timer on navigation/unmount; no
  overlapping cycles. Global dashboard counts use filtered list totals (not just
  one page), refreshed every 10 seconds and on manual refresh/actions. Recent jobs
  use last backend page(s), reversed; Queue uses paginated server ordering.
- Mutations wait for server truth, track per-job busy state, refresh after conflicts,
  preserve loaded data on failure. Pause is read from backend each cycle, not local
  storage or inferred from buttons. Cancel requested stays running/Cancelling until
  backend terminal status. Retry only failed with attempts remaining.
- Existing backend 0 is unknown/reset progress; show phase instead of claiming known
  0%. Null progress also indeterminate. Completion comes only from completed status.
- No downloaded-state flag exists; defer history/dedup/library to Phase 07. Output
  remains temporary, no file-open/download-path UI. No Drive, batch or editor.

## Planned files
Frontend types/api.ts + jobs.ts; api/client.ts, downloads.ts, jobs.ts, queue.ts;
stores/downloads.ts + queue.ts; composables/useQueuePolling.ts;
components/JobCard.vue + StatusBadge.vue; utils/jobs.ts + download.ts;
views/DashboardView.vue, DownloadView.vue, QueueView.vue; App/router/style and health
client; API/store/form/job/poll/router tests. Backend preview schema/service/route,
queue read route/schema, application wiring, endpoint tests and route-contract test.
README, architecture, API contract and this plan only.

## Implementation steps / test plan
1. Record boundaries and additive APIs; test preview/read-only pause.
2. Build typed HTTP boundary, strict types and store state/mutation/polling behavior.
3. Build accessible shell and three views, real counts, safe optional preview.
4. Verify fake-timer cleanup/races, validation/failure paths, status/action eligibility,
   routing, existing health regressions, full typecheck/build/backend regression.
5. Run local deterministic real-app browser workflow and offline/reload checks;
   review artifacts/scope and record acceptance evidence.

## Rollback / recovery
No schema change. Remove additive APIs/UI to roll back; durable Phase 05 jobs remain.
Browser reload reads jobs and pause from server; forms are not a persistence store.

## Deferred work
Phase 07 Library/History/Dedup, Phase 08 Storage/Drive, Phase 09 Batch,
Phase 10 Editor, discovery, similarity and automation. No new auth or credentials.

## Model
gpt-6.1-sol medium.

## Pages
- Dashboard
- Quick Download
- Queue
- placeholder navigation for later pages

## Deliverables
- Vue Router
- Pinia
- typed API client
- URL input supporting multiple URLs
- resolve preview
- download options
- downloaded-state indication when API reports it
- queue polling/progress
- retry/cancel controls
- clear error states

## Non-goals
No complex visual editor.

## Acceptance
User can paste URLs, create jobs, watch state, and retry/cancel through UI.

## Implementation discoveries
- Full regression runs exposed two existing timestamp-order assumptions: the queue
  cleanup test assumed submission order despite UUID tie-breaking, and the download
  repository test assumed distinct automatic timestamps. Tests now identify failed
  output explicitly and use explicit chronological fixtures, respectively. No worker,
  repository or schema behavior changed.
- The in-app browser runtime could not initialize (kernel assets path error).
  An isolated Edge/Playwright fallback exercised the real frontend and backend with
  a deterministic local adapter and generated media, without live platform requests.
  Screenshots were visually reviewed at desktop and 640px widths; no horizontal
  overflow or browser page errors were observed.
- Automatic approval review rejected the remaining offline-browser check with
  "blocked by policy" and no detailed reason. Offline/recovery rendering is covered
  by a deterministic App integration test; it was not verified in the browser.

## Verification record (2026-10-03)
- npm ci: passed, 200 packages installed, audit reported zero vulnerabilities.
- Frontend: 49 tests in seven files passed, including existing health/shell tests,
  malformed responses/network errors, form limits/options/escaping, cancellation,
  retry limits/conflicts, authoritative pause, polling timers/cleanup, routing,
  pagination/global counts and offline/recovery rendering.
- npm run typecheck and npm run build: passed; no frontend lint script configured.
- Browser workflow passed: Dashboard/health/counts, single-video optional preview,
  multiple URLs, visible progress, failed retry, active cancellation, pause/resume,
  browser reload restoring jobs/pause, navigation and narrow layout. Local test
  adapter only; no claim of live-platform verification.
- Temporary browser backend and Vite server stopped after verification. Tooling,
  fixture DB/media and screenshots remained outside the repository; dependencies,
  migration files, local credentials and downloaded media were not added to Git.
- Backend final regression: 356 passed; one existing Starlette/httpx deprecation
  warning. Ruff check and format check passed (91 files); pip check and application
  imports passed. Alembic head remains 0002_queue. Migration tests verified fresh
  upgrade, downgrade/reupgrade, foreign keys and metadata parity on isolated DBs.
- Final diff reviewed; git diff --check passed. Completed on phase/06-frontend.

## Explicit acceptance criteria
| Criterion | Result / evidence |
|---|---|
| Usable application shell | PASS — browser desktop/narrow, App/router tests |
| Dashboard | PASS — global totals/latest-five tests and browser |
| Quick Download | PASS — form tests and browser |
| Queue | PASS — pagination/filter/card tests and browser |
| Typed API client | PASS — runtime response guards, API tests, typecheck |
| One or multiple URLs submitted | PASS — 1..100 validation/options tests, browser |
| Real options map to backend | PASS — typed submission payload assertions |
| Created jobs observed | PASS — returned IDs and browser Queue workflow |
| Progress/status updates | PASS — card/status/timer tests and browser |
| Failed jobs retried | PASS — failed-only/attempt-limit tests and browser |
| Cancellable jobs cancelled | PASS — queued/active semantics tests and browser |
| Pause/resume usable | PASS — authoritative GET/read/actions tests and browser |
| API/network errors clear | PASS — API/store/App offline-recovery tests |
| Refresh/reload recovers durable jobs | PASS — backend persistence tests, browser reload |
| No fake Library/history/dedup/Drive state | PASS — disabled navigation/scope review |
| Frontend tests pass | PASS — 49 tests |
| Typecheck passes | PASS — vue-tsc |
| Build passes | PASS — Vite production build |
| Backend regressions pass | PASS — 356 tests and Ruff |
| Phase 07+ not implemented | PASS — final scope review |

Phase 06 implementation complete. Offline-browser verification remains limited as
recorded above; deterministic UI coverage passed. Next: Phase 07, not implemented.

## Commit-readiness review (2026-10-03)
- Per the follow-up request, equivalent deterministic offline/recovery coverage
  satisfies the behavioral requirement despite the blocked manual browser check.
  App integration covers proxy failure/recovery rendering; API tests cover rejected
  network requests; queue tests cover cached data and automatic recovery cadence.
  This does not claim that the missing manual browser check was performed.
- Added regressions for real Router navigation with an unfinished old read and
  repeated Dashboard/Queue transitions: exactly one polling timer remains, stale
  results are discarded and navigation to Quick Download clears all polling timers.
- No browser-specific crash/recovery defect was identified in implementation review.
- GET /queue reads only runtime pause; POST /videos/resolve validates/sanitizes input
  and projects resolver metadata without DB/media writes or history/library scope.
  Seven endpoint tests cover state read, projection, failures and invalid input.
- Cancel/retry eligibility matches backend states/attempt limits; cooperative cancel
  stays active until acknowledgement, and mutation conflicts refresh server truth.
  No fake downloaded/library/history state is presented.
- Review validation: 49 frontend tests, typecheck/build, 59 targeted backend tests,
  Ruff check/format and diff checks passed. Prior full backend run remains 356 passed;
  backend implementation did not change during this review.
- READY TO COMMIT. PHASE_CHECKLIST.md remains unchanged and unchecked; no commit
  was created and no later-phase functionality was added.
