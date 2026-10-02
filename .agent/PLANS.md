# Codex Execution Plans

An ExecPlan is a self-contained implementation contract for a substantial feature.

## Required behavior

When executing a plan:

1. Inspect current repository state before editing.
2. Read only docs referenced by the active plan.
3. Confirm current implementation boundaries.
4. Implement incrementally.
5. Keep the plan updated if discoveries change implementation details.
6. Run acceptance tests.
7. Do not implement later phases.
8. Finish with a review of the diff.

## Required sections

Every ExecPlan should contain:

- Goal
- Non-goals
- Relevant docs
- Current state assumptions
- Deliverables
- Implementation steps
- Data/API changes
- Test plan
- Acceptance criteria
- Rollback/recovery notes where relevant
- Deferred work

## Planning rule

If implementation uncovers a decision that affects:
- database identity,
- queue semantics,
- storage ownership,
- platform abstraction,
- security boundary,
- destructive file operations,

stop implementation long enough to update the active ExecPlan with the chosen behavior,
then continue.

## Completion rule

Do not mark a plan complete because code compiles.
All acceptance criteria must be checked explicitly.
