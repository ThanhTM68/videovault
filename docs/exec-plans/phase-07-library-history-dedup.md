# Phase 07 — Library, History & Dedup

## Goal
Make downloaded state reliable and user-manageable.

## Non-goals
No Drive/provider registry, batch/profile crawling, editing, discovery, similarity,
watchlists, multi-process workers, media-serving API or automatic orphan sweeping.
No authentication/access-control bypass or new third-party dependencies.

## Relevant docs
AGENTS.md, .agent/PLANS.md, PHASE_CHECKLIST.md, docs/product-spec.md,
docs/architecture.md, docs/database.md, docs/api-contract.md, docs/downloader.md,
README.md and prompts/REVIEW_CURRENT_PHASE.md.

## Inspected state and scope
Clean phase/07-library-history-dedup fast-forwarded from main (a099b20). Read AGENTS,
PLANS, checklist, product/architecture/database/API/downloader docs and Phase 02–06
models, repositories, queue/worker/downloader and frontend contracts. Existing distinct
Video/Download/MediaFile schema has identity constraints and SET NULL download linkage.
At phase start the worker completed validated temporary media without library/history
writes; force was false-only. Library/History were disabled navigation placeholders.

## Decisions and data/API changes
- Identity dedup occurs after worker resolve, never during submission. Successful
  history means Download.status=completed, independent of file existence. History
  removal hard-deletes events; FK SET NULL preserves media. All three destructive
  actions preserve Video metadata, tags and collections.
- Add 0003_library: nullable Download.attempt_number plus unique (job_id,attempt_number)
  index and nullable MediaFile.missing_at. Old rows remain valid; no old migration edits.
  One Download event per actual execution attempt; resolution failures/skips have none.
  Stale execution events become failed/cancelled on recovery. Store options in the
  existing requested_quality string as a documented compact JSON object.
- Bounded identity lock stripes shared by worker/finalization and destructive actions
  serialize same-video work in the existing single backend process. Waiting workers
  check cancellation; no DB transactions during downloads/copy/hash/delete.
- Copy validated output to exclusive unique managed filenames under LOCAL_STORAGE_ROOT,
  stream SHA-256, then atomically commit MediaFile + completed Download + fenced Job.
  Rollback/cancel deletes only owned finalized output; success consumes temp workspace.
  Crash between filesystem and DB commit can leave an orphan; no automatic sweeping.
- Reject traversal, Windows absolute/drive paths, symlinks/reparse points and paths
  outside the resolved managed root. No shell deletion, no absolute public paths.
- Library paginated search (title/creator), platform/history/file/tag/collection filters;
  detail reports history/files/hash. Bounded page/detail checks reconcile missing files;
  persisted file filter uses last-known state. History is separately paginated events.
  Add collection/tag list/create/attach/remove, forced asynchronous redownload and
  explicit delete-file/remove-history/delete-everything routes.
- Strict typed frontend clients/stores, Library/History routes, details/organization,
  clear confirmations, real Quick Download force. Keep existing Queue terminal skip.
  Preview may report actual DB state without creating metadata rows.

## Implementation sequence / files
1. Models and 0003 migration; focused library/organization repositories and schemas.
2. LocalFiles and LibraryService; worker/queue completion/recovery and preview wiring.
3. Transport routes and regression/API/FS/race/migration tests.
4. Frontend library/history types/clients/stores/views, navigation and force controls.
5. Full tests/typecheck/build/Ruff; deterministic local workflow; senior data-safety
   review using prompts/REVIEW_CURRENT_PHASE.md; fix and rerun affected checks.
6. Update README/API/database/architecture/downloader docs. Commit implementation,
   update checklist only afterward, commit checklist, push only Phase 07 and verify SHA.

## Test plan
Mandatory successful/skip/force/history-remove/file-delete/delete-all sequences; exact
hash and equal bytes distinct identities; missing/permission/path/symlink safety;
copy/hash/commit/cancel failure cleanup; attempt/retry/recovery and same-video race;
metadata merge/creator reuse; collection/tag/search/filter/pagination; migration
0002→0003/down/re-up/parity; frontend rendering/confirmations/actions/errors/reload.

## Rollback / limitations
Back up DB before migration rollback. Downgrade drops attempt/missing markers only;
durable media is never removed by migrations. Filesystem and DB cannot be one atomic
transaction; crash or failed cleanup can leave owned orphans. Single-process locks
are not a multi-process/distributed guarantee. No cloud/crawling/editor work.

## Deferred Work
Phases 08 Storage/Drive, 09 Batch, 10 Editor, 11 Hardening/Release and V2 12–14.

## Model
gpt-6.1-sol high.

## Deliverables
- primary dedup `(platform, platform_video_id)`
- successful-download history
- SHA-256 exact file hash after completed media
- Library API/UI
- History API/UI
- search/filter basics
- collections
- personal tags
- force redownload
- delete file
- remove history
- delete everything

## Critical semantics
Operations must not accidentally conflate:
video metadata, history records, and physical files.

## Tests
Every destructive operation needs tests.
Force-redownload needs regression test.

## Acceptance
Previously successful video is skipped by normal download,
but can be downloaded after history removal or via explicit force policy.

## Explicit acceptance criteria

| Criterion | Result / evidence |
|---|---|
| Identity dedup (platform, platform_video_id) | PASS - identity upsert/URL variant/equal-bytes tests |
| Successful-download history | PASS - actual events and transaction rollback tests |
| Normal duplicate skip | PASS - one transfer/no fake event; browser Queue badge |
| Force redownload | PASS - distinct files/events; Quick Download and detail browser actions |
| History removal enables normal download | PASS - SET NULL linkage and real browser workflow |
| Delete file preserves history | PASS - idempotence/missing and subsequent skip tests/browser |
| Delete everything safe | PASS - metadata/organization retained; failure and browser confirmation |
| Durable local Library media | PASS - managed file persistence and temporary cleanup |
| SHA-256 exact file hash | PASS - known digest, chunked read, distinct equal-byte identities |
| Library API | PASS - filters/detail/destructive/404/validation tests |
| Library UI | PASS - real records, confirmations, errors, browser desktop/mobile/reload |
| History API | PASS - attempts/options/forced/status/pagination tests |
| History UI | PASS - rendering/filters/errors, browser reload |
| Basic search/filter | PASS - literal title/creator search and platform/file/history/organization |
| Collections | PASS - create/idempotent membership/add/remove and browser |
| Personal tags | PASS - normalization/unique membership, distinct from source hashtags |
| Destructive operation tests | PASS - every operation, delete failure and active-download race |
| Filesystem containment tests | PASS - corrupt DB, traversal/drive/absolute and real junction |
| Previous-phase regressions | PASS - full backend/frontend suites |
| No Drive implementation | PASS - actual diff review |
| No Batch implementation | PASS - actual diff review |
| No Editor implementation | PASS - actual diff review |

## Final review and verification (2026-10-03)

Performed the senior backend/data-safety self-review required by
prompts/REVIEW_CURRENT_PHASE.md on actual routes, services, repositories, models,
migration, worker state fences, frontend actions and tests. Reviewed Video/Download/
MediaFile separation, FK/unique constraints, atomic completion, cancellation/recovery,
destructive paths, exception privacy, scope and transaction boundaries.

In-scope fixes: preserve creator names without invented IDs; keep detail reads responsive
during media work; reset route filter forms consistently; use readable requested options;
reset strong confirmation input; defer failed/cancelled acknowledgement until owned
file cleanup finishes. Regression tests cover cancellation after validated return,
cancellation waiting for identity lock, DB commit failure, active-download deletion,
duplicate event uniqueness and no open DB sessions during download/hash.

Final full backend run passed 389 tests with one Windows symlink privilege skip;
focused Library run passed all 33 runnable tests including the new data-integrity
regressions. The equivalent real Windows junction/reparse escape test passed. Ruff check
and format check passed (101 files); pip check passed; Alembic head is 0003_library.
Migration tests verify fresh head, populated 0002 upgrade/downgrade/re-upgrade, preserved
data/FKs and schema/model parity. Frontend passed 63 tests, vue-tsc and Vite build.

Deterministic local browser workflow passed against the real app/API, isolated SQLite
and generated FFmpeg media, without public-site requests: normal/duplicate/force,
delete-file/remove-history/delete-all, tag/collection create/add/remove, search/filter,
Library/History reload, offline cached rows and recovery. No page errors or horizontal
overflow at 390px. Desktop/mobile screenshots were visually inspected. Browser plugin
bootstrap failed on missing kernel assets; an isolated headless Edge fallback performed
the browser checks. Helpers/test DB/media/screenshots are not included in Git; owned
local servers were stopped. git diff --check passed. No new dependencies, secrets or
unrelated changes. Docs updated: README, API, database, architecture, downloader,
configuration comments and this plan.

Remaining limitations: single-process striped locks; partial progress on multi-file
delete failure; abrupt-crash/cleanup-failure orphans; last-known SQL file filters and
page/detail-driven missing reconciliation; detail returns at most 100 files/events;
local-only storage. Future phases remain deferred.

Implementation and review are complete; checklist remains unchecked until the actual
implementation commit exists. Commit implementation, update checklist, commit docs,
push only phase/07-library-history-dedup and verify local/remote SHA equality. Do not
merge main or create a Phase 08 branch.
