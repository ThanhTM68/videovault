# Storage Design - Phase 08

## Contract and ownership

`services/storage/contracts.py` defines put, exists, delete, get_metadata and availability
checks. `StorageService` selects LocalStorageProvider or GoogleDriveStorageProvider.
Downloader only creates validated temporary media; Google SDK calls live in storage.
No Google request is made at startup, submission, Library list or preview.
`STORAGE_PROVIDER=local` is the default; explicit `storage_target` overrides it.
Unavailable Drive fails explicitly; it never silently falls back to local.

Local keys remain relative managed-root paths. Drive keys are opaque stable file IDs,
never paths or URLs. Public file summaries contain provider, basename, size, SHA-256
and state, but no storage key, absolute path, token or credential file location.
SHA-256 covers validated local bytes; equal hashes never merge video identities.

## Media lifecycle and failures

Download -> process/probe TEMP -> provider put -> atomic MediaFile + successful Download
+ completed Job commit -> discard successful TEMP. Drive adds `uploading` between
processing and completion; progress remains below 100 until the DB commit.

Local puts exclusively create a unique file, copy in chunks, fsync and hash, preserving
Phase 07 containment, symlink/reparse rejection and Windows-safe filename behavior.
Drive streams resumable 1 MiB chunks using the official SDK with 30-second transport
and OAuth exchange timeouts. Transient 408/429/5xx, rate-limit 403 and transport errors
retry at most four attempts, with 1/2/4-second cancellable waits. Permanent permissions
fail immediately. Cancellation is checked before/between chunks and after upload.
No DB transaction spans provider I/O. An account lease covers upload through DB
commit/compensation, serializing root changes/disconnect; read-only status and job
submission do not wait for this lease. Use one backend process only.

A fresh pre-generated Drive ID identifies only this upload's output, including a lost
final response. Failure/cancel/DB rollback best-effort deletes that owned output before
terminal acknowledgement and temp cleanup. Cleanup failure logs a safe orphan warning;
it never fabricates completion. Failed attempts discard TEMP after recovery/cleanup
has been attempted; retry downloads anew. Hard crashes may leave remote or local orphans.
Resumable sessions and OAuth pending state do not survive restart; normal stale-job
recovery applies. There is no persistent upload-resume journal or orphan sweeper.

## Google setup and credentials

Install dependencies from backend/pyproject.toml. Enable Drive API in a Google Cloud
project, configure the OAuth consent screen/test users, and create a **Web application**
OAuth client. Register exactly `http://127.0.0.1:8000/api/v1/storage/google-drive/callback`
(or your configured loopback backend port) as an authorized redirect URI. It must be
the backend callback, not Vite or a wildcard. Set GOOGLE_DRIVE_CLIENT_ID,
GOOGLE_DRIVE_CLIENT_SECRET and GOOGLE_DRIVE_REDIRECT_URI only in ignored local `.env`.
Leave all Google values blank for local-only operation. Partial configuration is
reported as not configured and never triggers automatic authorization.

Open Storage -> Connect Google Drive -> Continue to Google. Backend authorization uses
`drive.file` only, offline access, consent, PKCE and random one-use state (10-minute TTL,
at most 32 pending flows). Backend exchanges the code and redirects to the configured
frontend with only a fixed success/error indicator. UI trusts fresh status, not that
query parameter. Restart invalidates pending states. Callback queries are removed
from application-managed access logs; OAuth SDK debug logs are suppressed. Configure
any external reverse proxy to omit callback query strings too.

Tokens (including refresh token and OAuth client secret) are stored only in an atomic
private file: PRIVATE_AUTH_ROOT/google-drive.json, default data/private-auth. It is not
served by the app, placed in SQLite or browser storage, or committed. Writes use fsync,
replace, 0700 directory/0600 file on POSIX and reject symlink/reparse chains. Windows
chmod does not establish a private ACL: keep this directory under an account-private
location and restrict it to the backend user with Windows ACLs. Backups of this file
are credentials. If overriding the path, keep it outside Git or add an explicit ignore.
The runtime directory and client_secret*.json are ignored in Git.

Expired tokens refresh via the official SDK and are atomically persisted. Revoked/invalid
authorization removes the private file and reports disconnected; temporary network
failure preserves it. Connection status is a local snapshot, not a live Google probe.
Disconnect clears pending flows/private tokens only; it does not revoke Google's grant
or remove media/history. Revoke consent separately in Google account permissions.

One account per database is supported. StorageAccount retains the non-secret Google
permission ID/display name and root folder ID. Reconnecting a different account is
rejected even after disconnect, preventing old file IDs from being used under a new
account. Multi-account switching and automatic binding reset are deliberately absent.

## Root and organization

Explicitly create/reuse a VideoVault folder from Storage, or enter an accessible folder
ID. Optional GOOGLE_DRIVE_ROOT_FOLDER_ID is validated on first connection when no saved
root exists. Root selection checks folder MIME, not trashed, and canAddChildren. It never
creates a root at startup. The `drive.file` scope only grants per-file/app-created access;
an arbitrary existing folder ID may be invisible. No Google Picker or broad Drive scope
is implemented. Prefer creating the app-owned VideoVault root.

Under the root, use platform / sanitized creator_name_creator_id / YYYY / MM, taking
source upload date or UTC completion date if absent. Exact escaped name + parent queries
exclude trashed folders. Reuse the oldest then smallest-ID match in a bounded first page
of 100; account serialization prevents in-process duplicate creation. A failed ambiguous
folder-create is not retried blindly. External concurrent changes remain outside this
single-process guarantee. Media filenames are bounded/sanitized and include a unique
suffix. Fresh media objects carry an app-private managed-media marker.

## Presence and deletion

Local detail checks the filesystem. Drive list/detail uses `stored` (last-known) or
`missing`, with no remote request per row. Explicit POST video refresh checks that video's
files: 404/trashed marks missing, auth/network/permission failure reports unavailable
without changing missing_at. Filters use persisted last-known presence. No bulk scan.
Drive deletion validates opaque ID and app media marker; it cannot delete a root folder
or unrelated Drive object. Reliable missing/trashed is idempotent success.

| Action | Media | Download history |
|---|---|---|
| Delete file | Delete active managed objects through their providers; mark each success | Keep |
| Remove history | Keep all objects and MediaFile rows | Remove; normal download eligible again |
| Delete everything | Validate all targets/config first, delete each, persist partial success | Remove only after every delete succeeds |

All actions preserve Video metadata, tags and collections. Mixed local/Drive partial
failure retains history and truthful per-file deletion markers. Force always adds a new
file/event, even across providers. Library Force redownload uses the configured default target; Quick Download can override it.
Successful identity history controls normal duplicate
skips independently of provider, file existence or hash.

## Verification / references

Deterministic SDK doubles exercise the real providers/worker/OAuth/API with generated
local MP4 media. No test requires Google credentials or live platform access. Optional
real Google smoke must use explicit private local credentials and is not an acceptance gate.

Official references: [drive.file scope](https://developers.google.com/workspace/drive/api/guides/api-specific-auth),
[resumable upload and pre-generated IDs](https://developers.google.com/workspace/drive/api/guides/manage-uploads),
[OAuth Flow/PKCE](https://google-auth-oauthlib.readthedocs.io/en/latest/reference/google_auth_oauthlib.flow.html).
