# Architecture and limits

HTTP requests enter server.py, which parses JSON and calls ExpenseService.
service.py owns validation and state transitions. store.py owns schema setup
and connection creation. SQLite persists expenses and append-only-by-convention
audit events. No agent or model is used by this application.

Submission and its audit event share a transaction. Decisions use BEGIN IMMEDIATE
so competing writers cannot both transition the same pending expense. Each
operation uses a separate connection; the server can handle concurrent requests.

Keyed submissions (H001) store one row per Idempotency-Key in the
idempotency_keys table: the key (primary key), a SHA-256 fingerprint of the
normalized payload, the expense id, and the original 201 response body. The key
lookup and the expense, audit event and key inserts share one BEGIN IMMEDIATE
transaction, so concurrent retries are serialized by SQLite rather than by
process memory, and any failure rolls back all three inserts. Keys and payloads
are validated before the transaction, so rejected requests never reserve a key.
initialize() only adds missing tables, so baseline databases upgrade in place.

There is no deployment pipeline, SSO, authorization, encryption setup, receipt
storage, multi-tenancy, database migration framework, monitoring, or production
HTTP hardening. The application is deliberately small enough for one developer
to understand while exposing realistic changes across routes, rules, persistence,
tests, CI, and documentation. It is unsuitable for real expense processing.

Persisted audit rows are useful business evidence but are not tamper-proof or
independently secured. Instructions in AGENTS.md are not enforced controls.
