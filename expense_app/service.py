"""Business rules shared by HTTP routes and tests."""
from datetime import datetime, timezone
from uuid import uuid4

from .store import connect

CATEGORIES = {"travel", "meals", "supplies"}


class DomainError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat()


def text(value, field, maximum=500):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise DomainError(f"{field} must be nonempty text of at most {maximum} characters")
    return value.strip()


class ExpenseService:
    def __init__(self, database):
        self.database = database

    def submit(self, data):
        if not isinstance(data, dict):
            raise DomainError("request must be a JSON object")
        employee = text(data.get("employee"), "employee", 100)
        amount = data.get("amount_cents")
        if type(amount) is not int or not 0 < amount <= 100_000_000:
            raise DomainError("amount_cents must be an integer from 1 to 100000000")
        category = data.get("category")
        if not isinstance(category, str) or category not in CATEGORIES:
            raise DomainError("category must be travel, meals, or supplies")
        description = text(data.get("description"), "description")
        expense = dict(id=str(uuid4()), employee=employee, amount_cents=amount,
                       category=category, description=description, status="pending",
                       reviewer=None, created_at=now())
        with connect(self.database) as db:
            db.execute("INSERT INTO expenses VALUES (:id,:employee,:amount_cents,:category,"
                       ":description,:status,:reviewer,:created_at)", expense)
            db.execute("INSERT INTO audit_events(expense_id,action,actor,created_at) VALUES (?,?,?,?)",
                       (expense["id"], "submitted", employee, expense["created_at"]))
        return expense

    def get(self, expense_id):
        with connect(self.database) as db:
            row = db.execute("SELECT * FROM expenses WHERE id=?", (expense_id,)).fetchone()
        if row is None:
            raise DomainError("expense not found", 404)
        return dict(row)

    def list(self):
        with connect(self.database) as db:
            return [dict(row) for row in db.execute("SELECT * FROM expenses ORDER BY created_at, id")]

    def decide(self, expense_id, data):
        if not isinstance(data, dict):
            raise DomainError("request must be a JSON object")
        reviewer = text(data.get("reviewer"), "reviewer", 100)
        decision = data.get("decision")
        if decision not in ("approved", "rejected"):
            raise DomainError("decision must be approved or rejected")
        with connect(self.database) as db:
            # Serialize concurrent decisions so exactly one transition succeeds.
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM expenses WHERE id=?", (expense_id,)).fetchone()
            if row is None:
                raise DomainError("expense not found", 404)
            if reviewer.casefold() == row["employee"].casefold():
                raise DomainError("employees cannot review their own expense", 403)
            if row["status"] != "pending":
                raise DomainError("expense has already been reviewed", 409)
            db.execute("UPDATE expenses SET status=?,reviewer=? WHERE id=?",
                       (decision, reviewer, expense_id))
            db.execute("INSERT INTO audit_events(expense_id,action,actor,created_at) VALUES (?,?,?,?)",
                       (expense_id, decision, reviewer, now()))
            result = dict(row)
            result.update(status=decision, reviewer=reviewer)
        return result
