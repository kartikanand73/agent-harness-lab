# Agent Harness Lab — Expense Approval

A realistic target repository for practicing harness engineering with Claude.
This is an **existing application to change**, not an implementation of a coding
harness. Bring your own Claude workflow to clone, inspect, implement, test,
push a feature branch, and open a pull request.

## Working baseline

- Submit expenses, list them, retrieve one, approve or reject a pending expense.
- SQLite persistence; integer US dollar cents; UTC timestamps.
- Input validation, prevention of self-review, one decision per expense.
- Atomic decision plus audit event, including concurrent-decision protection.
- Service and real HTTP integration tests; GitHub Actions configuration.
- Four enhancement briefs with precise acceptance criteria.

**Training scope:** synthetic data only. No authentication or authorization is
implemented; `employee` and `reviewer` are caller-supplied demo identities.
Self-review prevention is a business rule, not a security boundary. Run locally.
Do not expose this server or use it for real employee or financial data.

## Run (Python 3.11+, no third-party dependencies)

From the repository root:

```bash
python -m unittest discover -s tests -v
python -m expense_app.server --db expenses.db --port 8000
```

In a second terminal:

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/expenses \
  -H 'Content-Type: application/json' \
  -d '{"employee":"alice","amount_cents":12500,"category":"travel","description":"Synthetic train ticket"}'
curl http://127.0.0.1:8000/expenses
```

See [docs/API.md](docs/API.md) for the decision route and error contract.
The SQLite database is created automatically and excluded from Git.

## Start your first harness run

Read [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md), and [Task.md](Task.md).
The active task is **H001: idempotent expense submission**. H002–H004 remain
backlog; do not implement them during H001.

Suggested Claude instruction:

> Read AGENTS.md, CLAUDE.md, and Task.md. Inspect the repository and run the
> baseline tests. Implement only H001 on a feature branch. Add meaningful
> tests and preserve existing behavior. Run the regression suite and the
> H001 acceptance check. Commit the changes, push the branch, and open a
> pull request with test evidence and limitations. Do not merge it.

That instruction authorizes your local harness workflow; this repository does
not itself provide GitHub credentials, tool execution, a retry loop, or a PR bot.
See [docs/HARNESS-RUNBOOK.md](docs/HARNESS-RUNBOOK.md) for the seven-stage exercise.

## Repository map

| Path | Purpose |
| --- | --- |
| `expense_app/server.py` | Local HTTP routes and JSON validation |
| `expense_app/service.py` | Expense business rules and transactions |
| `expense_app/store.py` | SQLite schema and connections |
| `tests/` | Passing baseline regression and HTTP tests |
| `acceptance/h001.py` | Independent H001 HTTP acceptance check |
| `Task.md` | Active task entry point |
| `tasks/` | Enhancement briefs H001–H004 |
| `docs/` | API, architecture, handover, and harness workflow |
| `.github/workflows/ci.yml` | Baseline CI on push and pull request |

## Exercise progression

1. **H001:** Idempotency—retry a submission without creating duplicate expenses.
2. **H002:** Validated filters and pagination for the expense list.
3. **H003:** CSV export with spreadsheet formula-injection protection.
4. **H004:** Category approval limits driven by configuration.

The baseline suite should be green before your harness changes anything. The
separate H001 acceptance check intentionally fails against the original
application. It is not part of baseline CI. Make it pass as part of H001 and
add it to CI in that feature branch. Later tasks require the harness to write
their tests from the supplied criteria; their implementation is not included.

## Clone this lab

```bash
git clone https://github.com/kartikanand73/agent-harness-lab.git
cd agent-harness-lab
python -m unittest discover -s tests -v
```

Use your existing harness to read `Task.md`, implement H001 on a feature branch,
run the regression and acceptance checks, and open a pull request for review.
The harness itself remains separate from this target application.
