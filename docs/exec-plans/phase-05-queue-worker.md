# Phase 05 — Persistent Queue & Worker

## Goal
All download work becomes persistent jobs.

## Implementation decisions (Phase 05)

- Reuse jobs; revision 0002_queue adds only cancel_requested_at and a queue index.
  Existing nonnullable progress uses 0 for unknown/reset. No output/history table;
  successful output stays in the downloader-owned UUID temporary workspace.
- Validate the whole 1..100 URL submission before one atomic commit. Payloads contain
  only URL, height, container and audio flag; revalidate before worker execution.
  Accept local/force=false only; reject Drive, force and unknown options.
- One in-process manager per app, DOWNLOAD_CONCURRENCY blocking worker threads,
  one independent heartbeat/recovery supervisor. Sessions exist only during short
  operations. App startup requires an already migrated DB; tests can explicitly
  disable workers to inspect process-only health without touching a DB.
- Claim with a single UPDATE using a queued-candidate subquery and status/attempt
  conditions, returning the changed row. attempt_count counts started attempts and
  fences every worker write. No SELECT FOR UPDATE or shared Session.
- Truthful path: queued -> resolving -> downloading -> processing -> completed.
  Active states may fail/cancel. Uploading/skipped_duplicate remain reserved, with
  no Phase 05 entry transitions. Only explicit failed -> queued retry; terminal
  completed/cancelled/skipped_duplicate cannot restart. Recovery alone can move
  stale active states to queued, or failed when exhausted.
- Failed retry retains attempt_count (default max_attempts=3), resets other runtime
  state. No automatic failure retry. Cancellation request is durable; running status
  remains active until cooperative downloader checkpoints stop and cleanup finishes.
  No arbitrary PID termination. Blocking extraction/FFmpeg may delay acknowledgement.
- Progress phases persist immediately, otherwise at most once per second for a
  >=1 percentage point change, or once per five seconds. Clamp pre-success to 99;
  completed callback is advisory, only successful return commits completed/100.
  Ignore phase regressions from split-stream hook ordering.
- Heartbeat every 5 seconds regardless of progress; stale threshold 60 seconds.
  Recover before threads start and every 5 seconds so recently orphaned jobs also
  recover later. Stale cancellation requests become cancelled; other stale active
  jobs requeue below max_attempts or fail with WORKER_LOST. Fresh jobs stay active.
- Pause serializes with claims, blocks new claims, active work continues. Runtime
  state only; restart resumes. Shutdown stops claims and signals cooperative stop,
  joins for at most 5 seconds; a still blocked daemon keeps its supervisor/engine
  until it exits. Cancellation is acknowledged only after execution stops; an already
  validated completion may win a concurrent shutdown. Forced exit relies on recovery.
- SQLite file-backed, single application process only. No cloud/distributed queue.
- Review refinement: periodic recovery excludes locally owned executing jobs, even
  if heartbeat persistence fails. Signal their stop and wait for execution to return;
  never start a replacement while the local invocation still owns resources.
  Start the supervisor before execution threads so partial thread-start failure is
  supervised and cleaned up. Shutdown has a five-second join budget; a pending short
  SQLite operation can additionally wait for SQLite's finite lock timeout.

## Relevant docs / boundaries
AGENTS.md, .agent/PLANS.md, product-spec.md, architecture.md, database.md,
downloader.md and api-contract.md. Downloader owns paths/extraction/probe; routes
delegate to QueueService; repositories own queries, never commit.

## Data/API changes
0002_queue; POST downloads, GET jobs/list/detail, POST jobs cancel/retry,
POST queue pause/resume. Sanitized views exclude payload and filesystem paths.

## Rollback / recovery
Migrate before app startup. Back up populated databases before downgrade. 0002
downgrade removes cancellation requests/index only; 0001 is unchanged. Interrupted
temporary workspaces are not durable library files; garbage collection is deferred.

## Deferred work
Phase 06 frontend, history/dedup/library, storage/Drive, profile batch, editor,
discovery, similarity and automation. No new queue dependency or distributed lease.

## Model
gpt-6.1-sol high.

## Deliverables
- SQLite-backed jobs
- queue service
- worker loop
- configurable concurrency
- progress persistence throttling
- cancel
- retry
- pause/resume
- restart recovery
- status API

## State machine
queued -> resolving -> downloading -> processing -> completed

Queued may cancel; any running state may fail/cancel. Uploading remains reserved
for later handlers; no upload or skipped_duplicate entry is implemented here.
Failed -> queued is explicit retry only. Active -> queued is stale recovery only.

Other terminal/intermediate:
failed, cancelled, skipped_duplicate

Invalid transitions must be rejected.

## Recovery
On app restart, stale running jobs must not remain permanently running.
Define deterministic recovery/requeue policy.

## Tests
- transition tests
- retry limits
- concurrent claim test as practical with SQLite
- stale job recovery
- cancellation behavior

## Acceptance
A multi-URL request creates multiple durable jobs and survives process restart semantics.

## Current state assumptions / implementation steps
Inspected clean phase/05-queue-worker branch. Phase 02 jobs had basic CRUD and UTC
timestamps; no claim/cancellation/worker. Phase 03/04 downloader was synchronous with
normalized progress and isolated temporary output. Application owned a lazy engine.
1. Record queue, cancellation, recovery and storage ownership decisions above.
2. Add additive migration, atomic repository operations and centralized transitions.
3. Add validated QueueService, progress bridge, workers and lifecycle ownership.
4. Add transport-only endpoints and document their supported subset.
5. Verify migrated-file concurrency, failures, API workflow and all prior regressions.

## Verification record
Completed on 2026-10-02. All criteria below verified. Full backend pytest: 349 passed
(one existing Starlette/httpx deprecation warning), including all 300 prior tests.
Ruff check and format check passed (87 Python files). pip check passed; app import
passed. Frontend typecheck, 7 Vitest tests and production build passed, source unchanged.
Migration tests cover empty upgrade, populated 0001 upgrade, 0002 downgrade/re-upgrade,
full downgrade/base/re-upgrade, CLI/offline behavior and model/schema parity.
Final standalone local API smoke used a migrated temporary DB, controlled adapter,
generated media and real ffprobe: 202 queued -> paused queued -> downloading ->
completed/100; shutdown left no live workers. No external platform requests.
Diff reviewed: 0001 unchanged; no tracked media, DB, credentials or worker artifacts.

| Acceptance requirement | Verification |
|---|---|
| Durable independent multi-URL jobs and atomic submission | durable observer + forced rollback tests |
| Worker execution and configurable concurrency | real service with controlled local adapter; limit=2 |
| No duplicate claims | eight claimers against one migrated SQLite file |
| Throttled progress and truthful completion | fake-clock callback flood and invalid-media failure |
| Pause/resume | active attempts finish; queued rows wait; resume drains |
| Queued and running cancellation | durable request, delayed checkpoint, workspace cleanup |
| Retry limits | three started attempts, invalid states, old-attempt fencing |
| Restart recovery | stale/fresh/exhausted/cancelled rows, racing heartbeat/cancel |
| Failure isolation | failed job followed by successful job on same worker |
| APIs and stable errors | submission/list/detail/cancel/retry/pause/resume, 404/409/422 |
| Lifecycle | startup recovery, thread startup failure, bounded stop, no session leaks |
| Security and phase boundaries | payload revalidation, query stripping, safe logs; no later phase |
