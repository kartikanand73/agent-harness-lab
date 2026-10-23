# H004 — configurable approval limits (backlog)

Activate after H003 is reviewed and merged.

Customer: set per-category maximum amounts eligible for approval.

- Load a JSON policy file at startup with integer cent limits for exactly the
  existing categories. Add a sample: travel 200000, meals 15000, supplies 50000.
- Invalid, missing, extra, boolean, zero, or negative limit values fail startup
  with a useful error. If no file is specified, use documented default limits.
- Submission still accepts over-limit expenses as pending.
- Approval above the category limit returns 422, leaving both status and audit
  unchanged. Exactly at the limit is allowed. Rejection is always allowed for
  an otherwise reviewable expense. Self-review and single-decision rules remain.
- Evaluate policy at decision time. The active policy is fixed for each server
  process; changing a file requires restart. A replayed H001 submission still
  returns its original creation response.
- Add tests for policy validation, per-category behavior, boundary amounts,
  rejected approval atomicity, restart with a changed policy, and regression.
- Document configuration, limitations, and operational ownership. Do not add
  automatic approval or implement identity management in this task.
