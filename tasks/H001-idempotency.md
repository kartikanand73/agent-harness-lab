# H001 — idempotent expense submission

## Customer problem
An employee submits an expense, the response is lost, and the client retries.
The baseline creates two expenses. Implement a retry-safe submission mechanism.

## Contract
- `POST /expenses` accepts an optional `Idempotency-Key` header.
- Valid keys contain 1–100 ASCII characters drawn from letters, digits, `_`, `-`,
  and `.`. An explicitly empty or invalid key returns 400 without any writes.
- The first request with a new key returns 201 and creates one expense plus one
  submitted audit event. Successful responses have `Idempotency-Replayed: false`.
- Repeating the same key with the same normalized payload returns 200, the
  original creation response (including original status), and
  `Idempotency-Replayed: true`. It creates no extra expense or audit event, even
  if the expense has since been approved. Persist the original response.
- The normalized payload is exactly employee, amount_cents, category, description
  after existing validation/whitespace trimming. JSON key order is immaterial;
  unknown fields remain ignored as in the baseline.
- Reusing a key with a different valid normalized payload returns 409 with no writes.
- Invalid payloads do not reserve keys. Corrected requests can reuse those keys.
- Without a key, preserve baseline behavior: each valid POST creates an expense.
- Keys are global within this synthetic single-tenant lab; persist them in SQLite
  across restarts. Production identity/tenant scoping is explicitly out of scope.
- Concurrent requests for the same key/payload must create exactly one expense
  and one submitted event. Use database constraints and transactions, not a
  process-local dictionary. One response is 201; other successful replays are 200.
- Existing baseline database files must upgrade without losing expenses or audit
  events. Do not drop existing tables. Document the migration behavior.

## Likely files
`server.py`, `service.py`, `store.py`, tests, docs/API.md, and CI. Investigate
before deciding the design. You may add focused modules and tests.

## Verification
```bash
python -m unittest discover -s tests -v
python -m acceptance.h001
```
The acceptance check covers the external contract, but is not exhaustive.
Add your own concurrency, migration, normalization, and atomic-write tests.
Add the acceptance command as an additional CI step once implemented.

## Deliverables
Feature branch `feat/H001-idempotency`, implementation, meaningful tests,
documentation, and PR with exact verification results. Do not implement H002–H004
or merge. Report limitations; do not claim a production-ready security system.
