# Stabilization gate for Phases 00-09

## Goal and starting state

Make the existing Dashboard, Quick Download, Queue, Library, History, Storage and
Batch workflows reliable in a real browser before Phase 10. Start from clean
stabilize/00-09-demo at 8070393dff1505289871b155bfd8cdad690d0afb, equal to current
main and fetched origin/main. Phases 00-09 are historically checked; keep them so.
No Editor/Phase 10+, redesign, distributed services, credentials or user-data changes.

## Relevant documents and boundaries

Read AGENTS.md, .agent/PLANS.md, checklist, README, product/architecture/database/API/
downloader/storage docs and Phase 05-09 ExecPlans. Audit actual frontend stores/API/
views/composables and backend app/routes/queue/workers/library/storage/sources.
Routes stay transport-only; services own orchestration, repositories queries,
providers I/O, workers execution. No migration unless a proven schema defect needs it.

## Initial stability assessment

- One shared Queue Pinia polling owner, self-scheduling timeout (2s active / 10s
  idle/error), pending read coalescing, per-read fresh AbortController and version
  fences. Dashboard/Queue mount start and unmount stop. Other stores do not poll.
- Pinia survives navigation. Download/Batch preview reads abort on criteria/unmount;
  Library list/detail and History reads have cancellation. Organization and Storage
  reads currently lack full lifecycle ownership. Mutations use finally/busy guards.
- Risk: Promise.all rejects before sibling reads finish; Queue releases controller
  without aborting siblings. Inactive cached jobs also influence active-work cadence.
  Mutation completion can start a fresh read after its page has unmounted.
- WorkerManager owns configured download threads plus one independent supervisor,
  5s heartbeat/recovery, 60s orphan threshold, 5s cooperative shutdown budget. SQLite
  sessions normally short and scoped; media/provider I/O runs outside transactions.
  Risk: read-then-write organization transactions can fail upgrade against a worker
  write; manager state waits behind SQLite claim locks. Reproduce before changing.
- Storage has provider/account upload leases and private credential lifecycle. Local
  needs no Drive configuration; explicit Drive operations may take network time.
- Source previews: at most32, TTL600s, semaphore2 enumeration, single-use submit,
  no preview polling. UI abort may leave a finite server enumeration finishing.
- 'Queue running' labels every unpaused queue, including completed/idle; old-first
  pagination can leave new work on later pages. Neither proves a main-thread freeze.

## Implementation and verification steps

1. Verify dependency/toolchain versions and branch origin. Create owned temporary
   demo roots outside repo; never reset or migrate the user's normal database.
2. Fresh isolated migration upgrade/current/check/heads. Start the exact documented
   backend and Vite commands; check health from another process, Console/Network/logs.
3. Reproduce polling/navigation/failure and organization DB contention before fixes;
   failing regressions precede code changes. Track actual browser symptoms separately
   from tests and external live-site limitations.
4. Fix proven lifecycle, busy-state, truthful metadata/pagination, concurrency and UI
   wording defects with tests. Preserve Queue states, identity dedup and deletion rules.
5. Add a maintained explicit deterministic demo runner, no production endpoints or
   feature dependency. It uses real FastAPI/services/worker/SQLite/media/provider code
   with isolated generated media and injected external adapter/Drive doubles. Support
   slow/cancel/fail-once, safe persisted test root and graceful restart.
6. Real-browser full workflows: seven-route navigation loops/hard reload/back-forward,
   completed Queue interactivity across several polling intervals, all actions, local
   and fake Drive downloads, hashes/files/history, dedup/force/deletion/tag/collection/
   filtering/pagination/missing-file reconciliation, Batch, offline/recovery, actual
   backend and frontend restarts, desktop and390px. Inspect Console/Network/backend logs.
7. Senior reliability review against actual diff and running behavior. Rerun targeted
   regressions then full backend/frontend suites and quality/migration/secret/artifact
   checks. Update this record and only affected documentation.
8. Commit only after gate PASS, push only stabilize/00-09-demo, fetch and compare full
   SHA and clean status. No automatic merge or Phase10 branch. Stop for user demo review.

## Acceptance gates

Automated suites, app startup/migrations, repeated real navigation and completed Queue
interaction, correct physical media/hash/history/dedup/delete semantics, Local without
Google, deterministic Drive and Batch, offline/restart recovery all must pass. No
uncaught JS/unhandled promises/reactivity spam, unexplained500/database-lock errors,
runaway polls, abandoned reads or permanently busy actions. Desktop/390px no overflow.
Final working tree clean and pushed SHA equality. Tests alone do not establish readiness.

## Recovery and deferred work

Demo scripts require explicit isolated roots and never reset/remove arbitrary paths.
Runtime DB/media/token doubles/logs/screenshots stay outside Git. Production schema
and existing data remain intact. Roll back only stabilization code if needed; no old
migrations edited. Real Google credentials absent and live platform availability do
not invalidate deterministic gates; report checks honestly. Existing single-process,
provider orphan/last-known-state and bounded source limitations remain. Phase10 blocked
until user reviews demo; Phase11+ features remain deferred.

## Progress / results

### Data/API changes and decisions

No schema, migration, endpoint or JSON contract changes. SQLite membership and Drive
account/root mutations reserve the writer before snapshot reads using conditional
unchanged-value UPDATEs. Reads and provider I/O retain their existing boundaries.
No global engine locking/WAL change. Queue keeps oldest-first pagination and the
backend state machine; idle wording changes to Ready for jobs. Counts remain a set
of separate snapshots. Library deletion reconciles actual per-file partial success.

Polling reads now own sibling cancellation, one timer and only active-page snapshots.
Route generation fences prevent late mutations/conflict reads from restarting work
after navigation. Storage gets a shared page-owner lease; its pending remote mutation
disables Drive submission while Local stays usable. Library/History pagination falls
back to the last valid page. Body-read aborts retain cancellation/timeout classification;
remote deletion receives the same 120s UI budget as explicit provider checks.

The demo runner is development-only. It ignores normal environment configuration,
requires an owned empty/marked root, rejects linked runtime paths and foreign Drive
credentials/accounts, never contacts Google for mock refresh, and skips seeding on
existing databases. Generated media goes through the normal worker/probe/hash/provider
pipeline. Synthetic metadata, source listing, fail-once and SDK boundaries are explicit.

### Reproduction and automated evidence

Pre-fix: 7 SQLite race tests failed (four membership, three account/root), Queue three
lifecycle/cadence regressions failed, and Library/History pagination/partial snapshot
regressions failed. Follow-up review reproduced late 409 recovery, uncancelled Storage
reads/late OAuth URL, stale connection indicators and pending Drive readiness. Five
runner safety tests failed before its fixes. All remain regression coverage.

Actual Edge browser pre-fix: a completed 100% Queue remained interactive, but failed
Promise.all left the jobs request un-aborted even after navigation. An external SQLite
RESERVED writer plus tag attachment returned HTTP500/database-is-locked. Post-fix the
same browser contention returns200 and failure aborts its sibling. No general browser
main-thread freeze was reproduced; misleading Queue running and stale active cache
were corrected rather than attributing a freeze without evidence.

Final automated checks after senior review: backend559 PASS,1 Windows symlink privilege
SKIP, existing Starlette/httpx warning; frontend121 PASS in11files; TypeScript/build
PASS (70 modules); Ruff check/format PASS128Pythonfiles; pipcheck PASS;95appmodules
imported. Seven SQLite and19safe-runner/media/fault regressions pass. Migration head
remains 0003_library; fresh and existing isolated upgrade/current/check/heads PASS.
Python editable reinstall/pipcheck PASS; clean npm ci PASS,201packages/zero reported
vulnerabilities. Initial Windows native-module file lock cleared by stopping Vite
before reinstall; dependencies/lockfile unchanged.

### Real environment and browser evidence

Windows/Python3.12.9/Node25.2.1/npm11.2.0/Git2.47.1/FFmpeg8.0/ffprobe8.0 verified.
Started exact documented python -m app.main and npm run dev with isolated database/
storage and checked health from another process. All seven empty routes loaded; a
favicon404 was corrected with an intentional SVG asset. Final deterministic runner
and real Vite then exercise actual persisted media workflows in installed Edge154
via standalone Playwright (in-app kernel initialization unavailable).

Fresh final browser pass verified three navigation loops, all route reloads and
back/forward with one Queue timer and none on other pages; completed Queue responsive
over31s/three idle intervals; real download/hash/history, dedup/force, all deletion
semantics, tags/collections, Library/History filters/pagination. Earlier actual-browser
passes verified pause/queued cancel/running cancel and Retry attempt2 with failure
history; health requests during slow transfer peaked at5ms. Missing-file reconciliation
and concurrent tag write were separately tested against running API/browser. Final
health requests during transfer peaked at76ms. A browser-only Storage console error
was reproduced: HTML pattern's Unicode v flag rejects the unescaped hyphen. Escaping
it fixed actual Edge validation and a red-to-green allowed/forbidden-ID regression.

Batch handle/channel ID, N40/source ordering, unsupported capabilities, inclusive
duration/unknown exclusion, history eligibility/Force, Local/fake-Drive jobs and single-
use preview PASS. Actual source enumeration delayed11s succeeded; accelerated demo
clock expiry20s gave stable SOURCE_PREVIEW_EXPIRED (production600s unchanged). Criteria
changes invalidated preview and backend restart invalidated the transient token.

Browser offline preserved records, released busy flags and recovered with a fresh
controller. Library navigation over11s had zero Queue requests/timers. All seven
routes at390px with long title, IDs and detailed SHA-256 had no horizontal overflow.
Actual local-first/Drive-less empty startup PASS. Fake OAuth/root/upload/availability/
delete/disconnect PASS; ordinary Drive details remain last-known, explicit disconnected
check reports unavailable, disconnected deletion validates all targets before touching
files. Real-provider fake-SDK permission faults verify partial local deletion reflected
in UI with history/Drive retained; upload failure/Retry reaches attempt2 and empty temp.
Double-click submit produced one HTTP POST; no page error or unhandled rejection.

Actual graceful active shutdown145ms and idle shutdown PASS. Runtime isolated stale
fixtures recovered eligible attempts to real completion at attempt2 (one media/event),
exhausted attempts to WORKER_LOST, pending cancellation to cancelled; fresh queue is
unpaused. Queue/Library hard reload and restart recovered persisted data; stale Batch
token returned400 and a clear expiry/re-preview state. Vite restart after npm ci works.
No unexplained application500, SQLite lock error, uncaught JS, reactivity warning or
runaway polling remains. Expected diagnostics: deliberately injected offline/503,
permission/expired-source400 and Vite upstream errors while backend intentionally stops.
Worker count3 plus supervisor stays bounded; observed OS threads10-12 /120-124MB without
obvious accumulation. Test-driver selector assumptions were corrected to match existing
last-known Drive, validation-before-delete, error status and UI labels; no product
semantics changed to make those assumptions true.

Final physical audit:36 Local files and2 fake-Drive byte objects verify size/SHA-256/
ffprobe;8 deleted objects absent,1 externally missing file recognized;0 active jobs,
empty temp, SQLite quick_check/fkcheck PASS. Runtime evidence/logs/screenshots/DB/media/
mock credentials stay in the owned external temporary root; no user DB was modified.

### Dedicated final review and acceptance

Backend and frontend senior reliability reviews PASS after challenging timer/read
ownership, late409 rejection, mutation navigation, Drive leases/readiness, SQL writer
ordering, historical state, response validation, browser pattern and safe demo restart.
Their fixes were rerun through relevant regressions and final full suites above. Root
reviewed the actual diff and running behavior. No API/schema expansion, Editor changes,
credentials/access-control bypass or unrelated refactor was introduced.

Functional/browser, failure/recovery, automated, documentation and migration gates
PASS. Additional final browser checks verify actual last-page shrink (26tagged videos
to25, Page2of2 recovers Page1of1), unsupported TikTok Batch with a clear Quick Download
message, restarted frontend after clean install, and valid connected Drive folder
pattern at390px. Only expected unsupported-source400 appears in that console capture;
no regex warning/page error remains. All owned demo servers stopped and ports8000/
8001/5173 were verified free; persisted runtime evidence remains outside the checkout.

Final staged artifact/diff scan PASS:34intended text files; no media/DB/cache/logs/
screenshots/environment files or real secrets. Secret-key matches are only explicit
known fake test markers. Implementation commit
`fb2ece54feb7d19a61406e6acf751edd1140f248` exists, was pushed only to
`stabilize/00-09-demo`, fetched, and matched the complete remote SHA with a clean
working tree. This follow-up records that evidence; its final head will be fetched
and compared again after the documentation commit. No merge or Phase10 work.

## Final acceptance record

| Real browser workflow | Result | Evidence |
|---|---|---|
| Navigation | PASS | Three loops over seven routes; reload and back/forward |
| Dashboard | PASS | Counts/recent jobs load; one polling owner |
| Quick Download | PASS | Preview/options/real job/media/hash/event |
| Queue | PASS | Status filters, pages, details, refresh and actions |
| Queue after completion | PASS | 31s/three idle intervals; 100% and responsive controls |
| Pause / Resume | PASS | Claims pause, active work continues, queued work resumes |
| Cancel | PASS | Queued and running acknowledgement; no fake successful file/event |
| Retry | PASS | Same job attempt2; failed/completed events preserved |
| Library | PASS | Search/all filters, pagination, details and last-page recovery |
| History | PASS | Actual success/failure/forced events, status/platform/pages |
| Dedup | PASS | Skip creates no extra transfer/media/history event |
| Force | PASS | New file/event, original file and hash preserved |
| Delete file | PASS | Physical removal, history retained, normal duplicate still skipped |
| Remove history | PASS | Files kept; normal download executes again |
| Delete everything | PASS | Confirmation; files/history removed, metadata/organization kept |
| Tags | PASS | Create/attach/filter/reload/remove; concurrent writer succeeds |
| Collections | PASS | Create/attach/filter/reload/remove persists |
| Storage Local | PASS | Real local media; no Drive connection needed |
| Storage without Drive configuration | PASS | Documented stock app startup; Local available, Drive disabled |
| Batch | PASS | Handle/channel, limits/filters, Local/fake Drive, history/Force/cache |
| Offline / Recovery | PASS | Actual offline snapshot/busy cleanup/controller recovery |
| Backend restart | PASS | Persisted views, cache invalidation, stale/cancel/exhausted recovery |
| Responsive 390px | PASS | Seven routes, long titles, details/hash; no horizontal overflow |

Frontend restart after clean npm install, browser-only pattern regression, provider
permission faults/partial-deletion reconciliation and double-click submission also PASS.
Final senior reviews, all automated checks, documentation, artifact and implementation
commit gates PASS. Verdict: **DEMO READY** for the documented deterministic application
demo, with live-site/real-Google limitations below. Checklist inspected: historical
Phases00-09 remain[x] from their committed evidence; Phases10-14 remain[ ]. No checklist
change is needed. Phase10 awaits user demo review and has not started.

### External limitations

Live yt-dlp public smoke returned stable DOWNLOAD_UNAVAILABLE, not a successful live
transfer. Real Google smoke NOT RUN: no local configuration/credentials. These are
external limitations; neither is substituted with a false live-integration claim.
