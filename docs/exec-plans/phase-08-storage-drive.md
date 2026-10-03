# Phase 08 — Storage Providers & Google Drive

## Goal
Finalize storage abstraction and add Drive as optional provider.

## Non-goals
No Batch, Editor, Drive import/sync/crawler, multi-account switching or distributed workers.
Real Google smoke is optional; deterministic mocked Google tests gate acceptance.

## Relevant docs and inspected starting state
Read AGENTS, PLANS, checklist, product, architecture, database, API, downloader and storage
docs. Clean phase/08-storage-drive starts at 14d807e, containing merged Phase 07.
LocalFiles owns validated-temp copy/fsync/hash/containment/deletion. Library invokes it
directly; MediaFile already has local/google_drive enum and opaque-capable storage_key.
StorageAccount has non-secret identity/config only; config permits root_path/root_folder_id.
Submission is local-only and strips storage_target before persistence. No Google SDK exists.

## Decisions / data and API changes
- One StorageService registry and provider contract. Move LocalFiles implementation to
  LocalStorageProvider; retain an import alias for existing internal regression callers,
  never two implementations. Worker/Library use provider-neutral operations.
- No migration: keep relative local keys, use Drive file IDs. One persisted Drive account
  binding; reconnecting a different account is rejected even after disconnect, preventing
  old files being interpreted under another account. No automatic account reset/switch.
- Official Google clients; drive.file scope only. Explicit create-app-root or validated
  accessible folder-ID entry. Arbitrary pre-existing folders may require per-file grant;
  no broad Drive scope or Picker/file-manager expansion in V1.
- OAuth state is random, one-use, ten-minute TTL with bounded in-process storage and PKCE.
  Private atomic token file under data/private-auth (ignored), no DB/frontend secrets.
  Loopback callback validation; safe fixed frontend redirects; suppress OAuth SDK debug
  logs and callback query material in access logs. Restart discards pending OAuth only.
- Connection/refresh/root/disconnect and Drive execution use an account RLock. Worker
  retains an operation lease through DB completion/compensation, so disconnect cannot
  invalidate cleanup credentials mid-finalization. No SQLite transaction during Google I/O.
- Drive hierarchy platform/creator identity/year/month with sanitized bounded names;
  parent-constrained exact folder reuse, deterministic duplicate resolution. Resumable
  chunks, finite network timeout, bounded transient retries/backoff and cancellation.
- Hash validated local bytes; never redownload Drive media for hashing. Provider put
  precedes the existing atomic MediaFile/Download/Job commit; successful temp cleanup
  follows commit. On failure/cancel, compensate only the newly owned object; safe orphan
  warning if compensation fails. No silent fallback to local.
- Drive files carry app-managed media markers; validate opaque IDs and ownership before
  destructive operations. Reliable 404/trashed means missing; auth/network errors do not.
- Library list/preview/mutations use cached Drive state without remote row-by-row calls.
  Explicit targeted refresh reconciles Drive existence. Local presence checks stay intact.
  Delete-all validates targets, records partial progress, retains history until all succeed.
- Typed storage status/connect/disconnect/root APIs, Storage page, Quick Download target
  selector/default and file-level provider display. No tokens in browser persistence.

## Implementation steps / files
1. services/storage contracts/local/Drive/OAuth/credentials/service; repositories/storage;
   config, logging, schemas/storage, api/v1/routes/storage and application wiring.
2. Queue payload/validation, provider-neutral worker completion, library projections and
   deletion, MediaFile persistence and uploading transition. Existing schema preserved.
3. Mock SDK/provider/OAuth/security/worker/cleanup/mixed-provider regression tests.
4. frontend types/api/stores/storage, StorageView, DownloadView, VideoDetails, router/App;
   storage/form/provider-display tests. No frontend dependency additions.
5. README, storage/API/database/architecture/downloader docs, .env.example/.gitignore,
   backend dependency install/pip check; full tests/Ruff/typecheck/build/migration checks.
6. Deterministic real-app/browser flow with mock Drive; final senior review/fixes/reruns;
   clean diff/credential review. Commit implementation, then checklist/evidence commit,
   push only phase/08-storage-drive, fetch/verify full SHAs, stop without merge/Phase 09.

## Test plan
Provider contracts; folder reuse/create/duplicate/root rejection/query escaping; OAuth
state/expiry/replay/denial/refresh/revocation/account binding/private file/log secrecy;
upload success/bounded retries/permanent failure/cancel checkpoints/commit ordering;
DB failure compensation including cleanup failure; both/mixed providers' Phase 07
dedup/force/delete/history semantics; no remote list I/O or open DB during Google calls;
local containment regressions; uploading fences/recovery; strict API/default targets;
frontend real status, unavailable options, actions/errors, provider labels and navigation.

## Rollback / recovery limitations
No schema rollback required. Keep existing local data. Reverting code cannot operate on
new Drive media until Phase 08 is restored. Tokens remain private runtime files; local
disconnect removes credentials, retains DB/files, does not revoke remote Google consent.
Single process/account; pending OAuth and resumable sessions are not restart-persistent.
Compensation failure/crash may leave remote orphan; no sweeper or background reconciliation.

## Deferred work
Phases 09 Batch, 10 Editor, 11 Hardening/Release, 12 Discover, 13 Similarity/Quality,
14 Watchlists/Rules. Multi-account, Drive import/sync and background reconciliation deferred.

## Model
gpt-6.1-sol high.

## Deliverables
- StorageProvider interface
- LocalStorageProvider
- GoogleDriveStorageProvider
- connection/config status
- Drive root folder selection/config
- nested folder organization
- resilient upload flow
- media_files storage key abstraction
- safe temp cleanup only after successful commit

## Security
No secrets in Git.
OAuth/token storage must be documented and ignored by Git.
Do not log token values.

## Tests
Mock Drive API for CI.
Test folder resolution, upload success/failure, cleanup semantics.

## Acceptance
Same completed download pipeline can target local or Drive without downloader knowing provider details.

## Final review and manual evidence (2026-10-03)

Reviewed the actual staged implementation against prompts/REVIEW_CURRENT_PHASE.md:
provider boundaries, queue fences, DB/physical lifecycle, OAuth state/PKCE/token secrecy,
root ownership, retry/cancel, mixed deletion and frontend authority. No remaining
in-scope correctness/security/data-integrity finding after the fixes below.

Review fixes:
- Removed the upload/account lock from local status snapshots, so submission cannot
  wait for an active upload; added a concurrent lease/submission regression.
- Preserved the account lease through completion/compensation so disconnect cannot
  invalidate credentials in that critical interval; added concurrency coverage.
- Sanitized callback query material in access/client logs and public file basenames;
  tested code/state secrecy and credential atomic failure/reparse rejection.
- Made Drive last-known state explicit in Library/preview; remote permission/auth
  errors do not mark files missing. Cached UI status is disabled after offline errors.
- Fixed narrow navigation wrapping after the Storage link introduced horizontal overflow.
- Corrected an existing cleanup assertion to join the worker: successful completion
  must commit before TEMP cleanup, so observing completed alone cannot assert cleanup.
- The lost-upload-response test uses real bounded backoff; replacing global Event.wait
  interfered with Windows subprocess reader-thread startup, so that test shortcut was
  removed. This was test isolation, not a provider failure.

Manual deterministic workflow passed twice against the real FastAPI/Vite/worker app
with generated media and mocked Google SDK boundaries, using isolated temporary DB,
media and obvious fake credentials. Verified local upload, Drive connection callback,
root create/reuse/select, cross-provider skip, forced Drive download, hash/provider
file display, explicit presence refresh, delete file, remove history, delete everything,
reload and disconnect. Checked desktop 1440px and narrow 390px; no horizontal overflow
or browser page errors after the navigation fix. Offline Storage read preserved cached
state with an error, then recovered after reconnect. Unconfigured UI was checked with
one explicit status-response interception; all download/deletion flows used real APIs.

Browser plugin initialization failed before connection with Windows os error 3;
standalone installed Edge/Playwright performed the checks. Temporary helper scripts
were removed; screenshots and test runtime data were outside the repository.
Real Google smoke: NOT RUN - no local credentials configured (verified as a boolean
only). Live Google access is optional, not a phase gate.

Diff/security inspection: no credentials, cookies, OAuth cache, DB, media, dist, logs,
node_modules or unrelated changes staged. Credential signature scan returned zero
matches. Source references to token/secret fields and clearly fake test values were
reviewed. Private token directory is ignored; Windows ACL limitation is documented.
No new migration: 0003_library remains head. Fresh migration/schema parity, data
preservation and downgrade/reupgrade are exercised by the full backend suite.

## Final acceptance and verification

| Criterion | Result / evidence |
|---|---|
| StorageProvider abstraction | PASS - typed put/exists/delete/get_metadata contract and registry |
| LocalStorageProvider | PASS - single moved implementation; Phase 07 containment/lifecycle regressions |
| GoogleDriveStorageProvider | PASS - official SDK boundary with deterministic doubles |
| Provider-neutral worker pipeline | PASS - local/Drive/cross-provider force/dedup worker tests |
| Google Drive configuration status | PASS - local snapshot, no Google or upload-lock wait |
| OAuth connection | PASS - real SDK PKCE URL, state expiry/replay/denial and mocked callback |
| Token secrecy | PASS - private atomic file, callback/log tests, no DB/frontend secrets |
| Drive root folder | PASS - explicit create/reuse/select and missing/trashed/permission validation |
| Nested folder organization | PASS - exact parent/name queries, reuse and duplicate choice |
| Resilient upload | PASS - bounded retries, cancellation, ambiguous-response compensation |
| Safe temp cleanup | PASS - provider success + atomic completion before successful discard |
| Drive deletion/existence | PASS - ownership, missing vs unavailable, mixed partial deletion |
| Local regression | PASS - full backend and frontend suites |
| Mock Drive tests | PASS - 42 storage/OAuth/API/worker test cases, no live Google dependency |
| Phase 09+ excluded | PASS - no Batch/Editor/later implementation or branch |

Final post-fix commands/results:
- Backend `python -m pytest -q`: **433 passed, 1 skipped**, 64.42 seconds. Only skip is
  real Windows symlink creation without developer-mode/privilege; deterministic reparse
  protection and other containment tests pass. One existing Starlette/httpx deprecation
  warning; no unhandled-thread warning in the final run.
- `python -m ruff check .`: PASS; `python -m ruff format --check .`: 115 files formatted.
- Frontend `npm test`: **71 passed** across 9 files. `npm run build`: PASS, including
  vue-tsc typecheck; no new frontend runtime dependency.
- `python -m pip check`: no broken requirements. Official Google SDKs installed from
  declared compatible bounds (google-api-python-client 2.201.0, google-auth 2.59.1,
  google-auth-oauthlib 1.5.0, google-auth-httplib2 0.4.4, httplib2 0.32.0).
- `alembic heads`: **0003_library**, no new revision. Full suite verifies fresh upgrade,
  metadata parity, foreign keys, earlier data preservation and downgrade/reupgrade.
- Manual Edge workflow PASS as documented above; no real Google credentials required.
- Final staged whitespace/artifact/credential review PASS; documentation updated.

All verifiable implementation acceptance criteria are satisfied; final senior review
passed. Implementation committed as `6fb7255720cb664bbfa5d6d62a4ec3ae3d53841c`
(`feat: complete phase 08 storage providers and drive`). With tests, review, docs,
clean diff and the implementation commit verified, Phase 08 is marked complete in
PHASE_CHECKLIST.md in the following documentation commit. Existing completed Phases
00-07 remain checked; Phases 09-14 remain unchecked. No merge or Phase 09 branch.
