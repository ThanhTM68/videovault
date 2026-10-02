# Codex Prompt — Phase 08: Storage + Google Drive

Recommended model: `gpt-6.1-sol`
Recommended reasoning: `high`

Copy the prompt below into a fresh Codex thread.

---

You are implementing **Phase 08: Storage + Google Drive** of VideoVault.

First inspect the current repository and git status.

Follow:
- `AGENTS.md`
- `.agent/PLANS.md`
- `docs/exec-plans/phase-08-storage-drive.md`

Read only other project documentation that is relevant to this phase.

Rules:
1. Work only on Phase 08. Do not implement later phases.
2. Preserve the modular-monolith architecture.
3. Do not bypass DRM, private content, authentication restrictions, or access controls.
4. Do not commit secrets, cookies, OAuth tokens, downloaded media, or local credential files.
5. Prefer the smallest maintainable implementation that satisfies the active ExecPlan.
6. Add or update tests for important behavior and failure paths.
7. Do not make CI tests depend on live social-media websites.
8. If the repository state differs from assumptions in the ExecPlan, adapt the plan before making a large architectural change.
9. Keep unrelated files unchanged.
10. Run the relevant tests, type checks, lint/build commands available in the repository.

Implementation workflow:
- inspect;
- summarize the current state briefly;
- implement the phase incrementally;
- run tests;
- inspect the final diff;
- fix issues found by review.

Before finishing, verify every acceptance criterion in:
`docs/exec-plans/phase-08-storage-drive.md`

Final response must contain:
- acceptance criteria: PASS/FAIL per item;
- changed files;
- tests/commands run and results;
- architecture/data/API decisions made;
- known risks;
- deferred items;
- exact next phase, but do not implement it.

If something external is unavailable, finish all deterministic local work and clearly identify the blocked integration instead of inventing a successful result.
