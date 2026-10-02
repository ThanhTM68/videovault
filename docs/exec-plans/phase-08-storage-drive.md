# Phase 08 — Storage Providers & Google Drive

## Goal
Finalize storage abstraction and add Drive as optional provider.

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
