# Baseline HTTP API

Base URL: `http://127.0.0.1:8000`. All data is synthetic. This local lab trusts
caller-supplied names; there is no user authentication or manager authorization.

| Method/path | Request | Success |
| --- | --- | --- |
| GET /health | none | 200, `{"status":"ok"}` |
| POST /expenses | JSON submission, optional `Idempotency-Key` header | 201, expense object (200 on replay; see below) |
| GET /expenses | none | 200, `{"items":[...]}` |
| GET /expenses/{id} | none | 200, expense object |
| POST /expenses/{id}/decision | JSON decision | 200, updated expense |

Submission: `{"employee":"alice","amount_cents":12500,"category":"travel","description":"Synthetic train ticket"}`.
Decision: `{"reviewer":"bob","decision":"approved"}` or `rejected`.

An expense has id (UUID), employee, amount_cents (positive integer up to
100000000), category (travel/meals/supplies), description, status
(pending/approved/rejected), reviewer (initially null), and created_at (UTC ISO).
Employee/reviewer are trimmed, nonempty text up to 100 characters. Description
is trimmed, nonempty text up to 500 characters. Unknown JSON fields are ignored.

POST bodies must be JSON objects, Content-Type application/json, 1–16384 bytes
with Content-Length. Chunked requests are unsupported. Errors are JSON
`{"error":"message"}`: 400 invalid input, 403 self-review, 404 not found,
409 already reviewed or idempotency key conflict, 415 unsupported content type.
Unexpected database/server failures are not given a production error-handling
contract in this lab.

## Idempotent submission (H001)

`POST /expenses` accepts an optional `Idempotency-Key` header so a client can
safely retry a submission whose response was lost.

- **Key format:** 1–100 ASCII characters from `A-Z`, `a-z`, `0-9`, `_`, `-`,
  `.`. Keys are case-sensitive (`Key` and `key` are different keys).
- **Whitespace:** the server does not trim keys. Python's HTTP parser
  (`http.server`) already drops spaces and tabs *before* a header value, so
  `Idempotency-Key:   abc` is received as `abc`. Trailing spaces or tabs are kept
  by the parser and make the key invalid (400).
- **Invalid key:** an explicitly empty key, a key outside the format, or more
  than one `Idempotency-Key` header returns 400 and writes nothing.

| Situation | Status | `Idempotency-Replayed` | Effect |
| --- | --- | --- | --- |
| No key | 201 | `false` | New expense every time (baseline behaviour) |
| New key | 201 | `false` | One expense, one `submitted` audit event, key saved |
| Same key, same normalized payload | 200 | `true` | Original creation body returned; nothing written |
| Same key, different normalized payload | 409 | absent | Nothing written |
| Invalid key or invalid payload | 400/415 | absent | Nothing written; the key is not reserved |

The **normalized payload** is exactly `employee`, `amount_cents`, `category`
and `description` after the usual validation and whitespace trimming of
employee/description. JSON key order and unknown fields do not matter. All other
differences, including letter case, count as a different payload.

A replay returns the **saved original creation body** with HTTP 200. That body
is stored when the expense is created, so it still shows `"status":"pending"`
and `"reviewer":null` even after the expense has been approved or rejected. Use
`GET /expenses/{id}` for the current state. Saved responses survive restarts.

Keys are global within this single-tenant lab and never expire. Any caller who
knows a key can replay its original response; there is no per-user or tenant
scoping, which a production system would need.

Concurrent requests with the same key are serialized by a database
transaction: exactly one returns 201 and creates the expense; the others
return 200 replays (or 409 if their payload differs).

### Database upgrade

On startup the server runs `initialize()`, which uses only
`CREATE TABLE IF NOT EXISTS`. A database created before H001 keeps all its
expenses and audit events and gains one new, empty `idempotency_keys` table.
No tables or rows are dropped or rewritten, and running it repeatedly is safe.
Expenses created before the upgrade have no key. Older application versions
ignore the extra table.

Baseline list order is created_at then id ascending. It is unbounded and query
parameters are ignored; H002 changes that contract. Audit events are persisted
internally; there is no audit retrieval route yet. H003 and H004 are not
implemented.
