# Repository instructions

This repository is a learning application with synthetic data, not a production
expense system. Implement only the active task referenced by Task.md.

- First inspect the code and run `python -m unittest discover -s tests -v`.
- Use a task branch (`feat/H001-idempotency` for H001); do not work directly on main.
- Keep money as integer cents and all generated timestamps in UTC.
- Use parameterized SQL and explicit transaction boundaries for related writes.
- Preserve the existing API unless the task explicitly changes it.
- Add tests for success, invalid input, and the feature's important failure modes.
- Do not delete, weaken, skip, or rewrite existing assertions to obtain a green run.
- Treat acceptance checks as read-only. If one is ambiguous or defective, report
  it rather than silently changing the requirement.
- Do not commit secrets, database files, generated logs, or real personal data.
- Do not install dependencies or add external services unless the task requires it.
- Do not implement backlog tasks, auto-merge, or change repository permissions.
- Before handover, provide the diff summary, exact checks and results, known
  limitations, and the branch/commit/PR URL when available.

These instructions guide an agent; enforcement of permissions, execution limits,
protected files, and approvals belongs in the harness and repository settings.
