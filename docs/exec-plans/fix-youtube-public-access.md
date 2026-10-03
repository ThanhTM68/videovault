# Fix anonymous public YouTube extraction

## Goal

Restore official anonymous YouTube extraction where the platform permits it and
truthfully distinguish content access restrictions, anonymous platform blocking,
and missing JavaScript support. Work only on `fix/youtube-public-access`, starting
clean at `503deb17992993d98fd7c56dc30dceb4dface8f4`.

## Non-goals

No Phase 10, schema/queue changes, credentials/cookies/browser sessions, login or
CAPTCHA automation, proxies, custom signatures/PO tokens, Generic fallback, or
remote solver fetching. Preserve TikTok's challenge guard and bounded retries.

## Relevant docs

AGENTS.md, .agent/PLANS.md, README.md, docs/downloader.md, docs/architecture.md,
docs/api-contract.md and docs/exec-plans/stabilization-00-09.md were read before
implementation. Inspect existing wrappers, adapters, metadata and their tests.

## Current state assumptions and demonstrated defects

- The pinned `yt-dlp==2026.8.19` installation lacks `yt-dlp-ejs`. Its own package
  metadata declares `yt-dlp-ejs==0.8.0` in the `default` extra.
- Node 25.2.1 is present. The pinned runtime source requires Node >=22.0.0;
  YoutubeDL defaults to Deno only, and VideoVault never enables Node explicitly.
- The classifier treats `Sign in to confirm you're not a bot` as content auth.
  Metadata private/premium/subscriber/needs_auth guards remain authoritative.
- `VIDEOVAULT_LIVE_TEST_URL` is absent: the user's exact URL/failure cannot be
  claimed reproduced. Use a small authorized public Blender smoke separately.

## Deliverables / implementation steps

1. Reproduce classifier regressions and actual isolated API/standalone extraction
   before fixes. Keep URLs, raw diagnostics, databases and media outside Git.
2. Enable pinned default dependencies; lazily discover/validate Node and the local
   compatible EJS package at single-video YouTube operations. Bound version probes.
   Use official `js_runtimes={'node': {'path': discovered_node}}`; fetch no scripts.
   Flat channel enumeration keeps its existing independent boundary.
3. Add two safe domain codes and narrow ambiguous auth matching. Keep restrictions,
   allowlists, TikTok guard, transport/media retries and worker state semantics.
4. Add effective-options, missing/broken runtime, restrictions, API/queue and UI
   recovery regressions. Preview visibly preserves the backend code and message.
5. Reinstall declared dependencies into a clean isolated venv. Run full backend,
   frontend, quality, migrations, stabilization/source and security reviews.
6. Try actual anonymous metadata and, if possible, one bounded normal download;
   inspect real file/hash/Library/History/temp. If blocked, smoke a second public
   video without escalating credentials, retries or network switching.
7. Update docs and this evidence, commit the reviewed fix, push only its branch,
   fetch and compare full SHAs. Preserve all roadmap checklist ticks.

## Data / API changes

No schema, endpoints or success payload changes. Existing safe HTTP400 envelopes
and failed Job errors add PLATFORM_ACCESS_BLOCKED and EXTRACTOR_RUNTIME_UNAVAILABLE.
Health/startup/other platforms do not require YouTube runtime support. Existing
source enumeration keeps its capabilities and error contract.

## Test plan / acceptance criteria

- [x] Red-to-green bot classification; true private/subscriber restrictions preserved.
- [x] Official effective Node options, missing/old/broken Node and missing/incompatible
      EJS errors are lazy, safe and deterministic; health remains process-only.
- [x] TikTok/Generic/source boundaries and bounded retries unchanged.
- [x] Failed jobs safe/terminal, no invented files/history, existing retry limits.
- [x] Quick Download displays safe code/message, releases busy, retries/navigates.
- [x] Clean dependency install + pip check; full backend/frontend/quality PASS.
- [x] Alembic current/check/heads remains 0003_library; no user database touched.
- [x] Actual browser and live results reported separately and honestly.
- [x] Final review/docs/artifact scan PASS; commit and verified branch push exist.

## Rollback / recovery

Revert only this compatibility fix if necessary; no migrations/data rollback.
Install declared dependencies and restart the backend after EJS/Node setup changes.
Use only newly owned external temporary roots for all live/browser checks.

## Deferred work

Live platform availability beyond anonymous official extraction, authentication,
broader extractor support, Editor and every future roadmap phase remain deferred.

## Progress / results

### Reproduction and root cause

No user-specific live URL was supplied through VIDEOVAULT_LIVE_TEST_URL. The exact
user failure is therefore not claimed reproduced. An isolated real create_app/API
on loopback reproduced the same misleading HTTP400 AUTHENTICATION_REQUIRED on the
public Blender Big Buck Bunny video. Internal failure was DownloadError wrapping
ExtractorError; raw diagnostics were discarded, with only class names and a bot-phrase
Boolean recorded. Same-venv standalone metadata calls with existing options (Deno
only), then explicit official Node options, both received the same bot response.

Demonstrated local defects: EJS absent from the original Python environment; Node
25.2.1 present but not explicitly enabled by VideoVault; broad auth fragments falsely
described an anonymous bot block as a content restriction. Node/EJS omissions alone
are not claimed to have caused the network block: it persists after correct setup.

### Runtime / dependency evidence

Exact installed-release authorities: yt_dlp-2026.8.19.dist-info/METADATA declares the
default extra's yt-dlp-ejs==0.8.0; YoutubeDL.py documents dictionary runtime options
and Deno-only default; utils/_jsruntime.py specifies Node >=22.0.0; EJS vendor VERSION
is 0.8.0. Version/hash checks and local script loading remain owned by official yt-dlp.
Declared default extra installs the matching PyPI EJS package; no stable upgrade,
independent guessed pin, custom solver, remote component or credential was added.

Original venv editable reinstall and a **new venv without system-site packages** both
installed from `pip install -e './backend[dev]'`. Both pip checks PASS; clean environment
reports yt-dlp2026.8.19/EJS0.8.0 and discovers supported Node. A real no-network YoutubeDL
with effective options reports Node25.2.1 supported, enabled runtimes={node}, no remote
components, loaded extractors={youtube}. Python3.12.9 and FFmpeg8.0 verified.

### Regression / final review evidence

Initial new backend tests:6 FAIL/4 PASS, proving bot misclassification, missing Node
without a specific error, and absent Node options. Frontend4 FAIL proved missing visible
stable Preview codes. All are green after the fix. Dedicated review additionally
reproduced a fresh-process partial EJS import escaping as ModuleNotFoundError; guarded
third-party imports fix it with a regression. Precise upstream TikTok private-post and
Instagram registered-follower messages retain auth without restoring broad fragments.
Members-only metadata also remains restricted. No queue/schema/provider changes.

Final clean-venv full backend: **598 PASS,1 SKIP,1 warning**, exit0. The skip needs Windows
symlink privileges; warning is existing Starlette/httpx deprecation. The39 targeted new
backend cases cover runtime/classification/API/actual threaded worker/manual retries,
safe pre-resolution failure and actual failed History events at three download boundaries.
Ruff check PASS; format PASS130backendPythonfiles; pipcheck PASS. Full suite includes
source/Batch, TikTok challenge, SQLite locking, Library/History, Storage and demo regressions.
Frontend **125 PASS/12files**, typecheck/build PASS, including4new typed HTTP/Router
regressions for code/message/busy/navigation/late-response/Retry behavior. No frontend
dependency changes. Alembic current/check/heads on the isolated DB PASS0003_library,
no new operations or migration. Independent backend/frontend final reviews PASS.

### Actual browser / live / physical evidence

Browser plugin kernel could not initialize (missing kernel assets); actual installed
Edge with standalone Playwright exercised the real local Vite/API/worker stack. This
browser controls VideoVault UI only, never YouTube extraction or browser sessions.
Quick Download's real public preview returned HTTP400 PLATFORM_ACCESS_BLOCKED and
displayed the safe code/message; preview busy released, Queue's failed job had attempt1,
Retry enabled, and navigation through Library/History/Quick Download worked. No page
errors or mobile overflow. Selector assumptions in the external test driver were corrected
to match the visible code's separator; no product changes were needed for those assumptions.

Restarted the isolated actual backend with Node's directory removed from its own PATH.
Startup/health/Local remained usable. At390px actual Preview showed the safe runtime
error, released busy, and did not overflow. Actual Queue manual Retry reached failed
attempt2 with EXTRACTOR_RUNTIME_UNAVAILABLE; navigation remained responsive, zero page
errors, zero Library/History records. The user's shell PATH/config/data were not changed.

After correct Node/EJS setup, standalone and real API/browser metadata for Big Buck Bunny,
and a second API metadata smoke for public Caminandes3:Llamigos, received anonymous bot
blocking. The normal public download submission returned queued and the worker went
resolving -> failed PLATFORM_ACCESS_BLOCKED before transfer. There is **no successful
live media download**, completed event, Library file, or SHA-256 to claim. Fixtures/tests
are not substituted for these live outcomes. No retry storm or network switching.

Final isolated physical audit: SQLite quick_check=ok, foreign-key violations0,
3terminal failed jobs, videos/download events/media files0, library files0, temporary
entries0. Owned backend stopped gracefully with workers joined; Vite stopped and ports
8001/5173 freed. Media/DB/logs/screenshots/browser drivers/venv remain outside the checkout.

**PUBLIC YOUTUBE LIVE DOWNLOAD BLOCKED BY PLATFORM/NETWORK**.
Functional verdict: **FIX VERIFIED — CLASSIFICATION/RUNTIME PASS, LIVE NETWORK BLOCKED**.
No exact user URL or general public YouTube transfer success is asserted.

### Git / checklist evidence

Documentation updated. Final root and independent reliability/security reviews PASS.
Artifact/diff scan PASS:16intended UTF-8 text files, no unexpected paths, private keys,
tokens, binary/media/database/log/credential/cache artifacts or checklist diff. Only
explicit fake secret markers exist in tests. Implementation commit
`97855f93e067bce8e0fc2fa2a0247a8ea24bd2fa` (`fix: restore public youtube extraction support`)
exists and was pushed only to `fix/youtube-public-access`; fetching origin confirmed
the full local/remote SHA matched with a clean working tree. This documentation
follow-up records the successful gate; its final HEAD is fetched/compared again before
the final report. All targeted fix acceptance criteria are satisfied, with the explicit
external live-transfer limitation above.
Phases00-09 remain[x], Phase10 and all future phases remain[ ]; targeted compatibility
work does not change the roadmap checklist. No automatic merge.
