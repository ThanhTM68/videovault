# Focused Bug Fix Prompt

Recommended: GPT-6.1 Sol High for difficult bugs, Luna Medium for obvious isolated bugs.

A bug exists in the current VideoVault implementation.

Do not start by rewriting the subsystem.

1. Reproduce or identify the failing behavior.
2. Inspect relevant tests/logs/code.
3. Identify the smallest root cause.
4. Add a regression test that fails before the fix when practical.
5. Implement the minimal maintainable fix.
6. Run relevant tests and inspect the diff.
7. Do not expand product scope.

Report:
- root cause;
- changed files;
- regression test;
- commands run;
- remaining risk.
