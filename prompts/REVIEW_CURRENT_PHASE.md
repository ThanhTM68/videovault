# Review Current Phase

Use GPT-6.1 Sol, reasoning High.

Review the current implementation against the active phase ExecPlan.

Do not add features from later phases.

Steps:
1. inspect git status and diff;
2. inspect acceptance criteria;
3. run relevant tests/typechecks/build;
4. identify correctness, security, data-integrity, error-handling, architecture, and test gaps;
5. fix issues that are inside current phase scope;
6. rerun verification.

Pay special attention to:
- destructive operations;
- DB uniqueness/FKs/transactions;
- queue state transitions and restart recovery;
- path traversal and unsafe filenames;
- command injection around ffmpeg/yt-dlp;
- secrets/logging;
- unsupported platform capability reporting;
- accidentally relying on live websites in tests.

Finish with:
- PASS/FAIL for each criterion;
- fixes performed;
- remaining risks;
- deferred work.
