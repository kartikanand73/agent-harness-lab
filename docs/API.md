# Baseline HTTP API

Base URL: `http://127.0.0.1:8000`. All data is synthetic. This local lab trusts
caller-supplied names; there is no user authentication or manager authorization.

| Method/path | Request | Success |
| --- | --- | --- |
| GET /health | none | 200, `{"status":"ok"}` |
| POST /expenses | JSON submission | 201, expense object |
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
409 already reviewed, 415 unsupported content type. Unexpected database/server
failures are not given a production error-handling contract in this lab.

Baseline list order is created_at then id ascending. It is unbounded and query
parameters are ignored; H002 changes that contract. Baseline submission has no
idempotency support; H001 adds it. Audit events are persisted internally; there
is no audit retrieval route yet. H003 and H004 are not implemented.
