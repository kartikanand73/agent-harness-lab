# H002 — filters and pagination (backlog)

Activate only after H001 is reviewed and merged. Change Task.md to this task.

Customer: a manager needs a bounded, searchable expense list.

- `GET /expenses` accepts optional `status` (pending/approved/rejected), `employee`
  (exact match), `limit` (1–100, default 25), `offset` (nonnegative, default 0).
- Apply filters before pagination. Sort by created_at, then id ascending.
- Response: `items`, `total` (matching rows before pagination), `limit`, `offset`.
- Invalid/unknown query parameters and repeated parameters return 400.
- Return an empty items list for offsets beyond the matching result count.
- Validate empty status/employee and noninteger pagination values as 400.
- Use parameterized SQL; do not load the whole table merely to paginate it.
- Preserve expense creation, decision, persistence, and H001 behavior.
- Add HTTP and service tests for combined filters, stable ordering, empty
  results, boundaries, invalid parameters, and SQL metacharacters in employee.
- Update API docs and PR evidence; do not implement CSV export in this task.
