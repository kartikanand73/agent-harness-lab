# H003 — CSV export (backlog)

Activate after H002 is reviewed and merged.

Customer: finance needs downloadable expense records.

- `GET /expenses/export.csv` returns UTF-8 CSV and Content-Type
  `text/csv; charset=utf-8`, plus an attachment filename.
- Support H002 status/employee filters, but not limit/offset. Reject unknown,
  duplicate, and invalid query parameters. Export all matching rows in H002 order.
- Columns: id, employee, amount_cents, category, description, status, reviewer,
  created_at. Keep amount_cents an integer; null reviewer becomes an empty cell.
- Use the standard csv writer for commas, quotes, and newlines.
- Neutralize text cells whose first non-whitespace character is `=`, `+`, `-`,
  or `@`, or which begin with a tab/carriage return, by prefixing a single quote
  to the original cell. Do not alter data stored in SQLite.
- No matches returns a header-only CSV. The export route must not be mistaken
  for an expense ID. Keep JSON endpoints and H001 behavior working.
- Add tests for headers, filters, quoting, newlines, injection inputs, and
  unchanged source data. Document that spreadsheet applications differ and
  this is a lab export policy, not a universal file-safety guarantee.
