# Phase Tracking Checklist

## V1

- [x] Phase 00 Bootstrap
- [x] Phase 01 Backend foundation
- [x] Phase 02 Database
- [x] Phase 03 Download engine
- [x] Phase 04 Platform adapters
- [x] Phase 05 Queue/worker
- [x] Phase 06 Frontend
- [x] Phase 07 Library/history/dedup
- [ ] Phase 08 Storage/Drive
- [ ] Phase 09 Batch
- [ ] Phase 10 Editor
- [ ] Phase 11 Hardening/release

## V2

- [ ] Phase 12 Discover
- [ ] Phase 13 Similarity/quality
- [ ] Phase 14 Watchlists/rules

## Completion rule

A phase is checked only after all its acceptance criteria pass, required automated
checks pass, final review passes, documentation is updated, the diff contains no
secrets or unrelated/generated artifacts, and the implementation commit exists.

Commit implementation before checking the current phase. Commit the checklist update
afterward; verify the final Git status and, when authorized, the pushed branch SHA.
Keep future phases unchecked. Repair earlier entries only from committed plans,
test/review evidence and Git history, never from filenames or planned work alone.
