# Architecture and limits

HTTP requests enter server.py, which parses JSON and calls ExpenseService.
service.py owns validation and state transitions. store.py owns schema setup
and connection creation. SQLite persists expenses and append-only-by-convention
audit events. No agent or model is used by this application.

Submission and its audit event share a transaction. Decisions use BEGIN IMMEDIATE
so competing writers cannot both transition the same pending expense. Each
operation uses a separate connection; the server can handle concurrent requests.

There is no deployment pipeline, SSO, authorization, encryption setup, receipt
storage, multi-tenancy, database migration framework, monitoring, or production
HTTP hardening. The application is deliberately small enough for one developer
to understand while exposing realistic changes across routes, rules, persistence,
tests, CI, and documentation. It is unsuitable for real expense processing.

Persisted audit rows are useful business evidence but are not tamper-proof or
independently secured. Instructions in AGENTS.md are not enforced controls.
