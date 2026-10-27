"""Business rules shared by HTTP routes and tests."""
import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from .store import connect

CATEGORIES = {"travel", "meals", "supplies"}
# ASCII only: [A-Za-z0-9] rather than \w, which also matches non-ASCII letters.
IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9_.-]{1,100}")


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


def validate_idempotency_key(key):
    """Accept 1-100 ASCII letters, digits, '_', '-' or '.'; nothing is trimmed."""
    if not isinstance(key, str) or not IDEMPOTENCY_KEY.fullmatch(key):
        raise DomainError("Idempotency-Key must be 1-100 characters from A-Z, a-z, 0-9, '_', '-', '.'")
    return key


def normalize_submission(data):
    """Validate a submission and return exactly the four fields that define it."""
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
    return dict(employee=employee, amount_cents=amount, category=category, description=description)


def request_fingerprint(normalized):
    """SHA-256 of the normalized fields as canonical JSON (sorted keys, no spaces).

    Keep this format stable: changing it would make old keys report 409.
    """
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("ascii")).hexdigest()


def new_expense(normalized):
    return dict(id=str(uuid4()), **normalized, status="pending", reviewer=None, created_at=now())


def insert_expense(db, expense):
    db.execute("INSERT INTO expenses VALUES (:id,:employee,:amount_cents,:category,"
               ":description,:status,:reviewer,:created_at)", expense)
    db.execute("INSERT INTO audit_events(expense_id,action,actor,created_at) VALUES (?,?,?,?)",
               (expense["id"], "submitted", expense["employee"], expense["created_at"]))


class ExpenseService:
    def __init__(self, database):
        self.database = database

    def submit(self, data):
        """Baseline submission without a key: always creates a new expense."""
        expense = new_expense(normalize_submission(data))
        with connect(self.database) as db:
            insert_expense(db, expense)
        return expense

    def submit_idempotent(self, data, key):
        """Submit with an Idempotency-Key. Returns (response_body, replayed).

        The key and payload are validated before any database access, so an
        invalid request never reserves a key. The lookup and all three inserts
        run in one BEGIN IMMEDIATE transaction: concurrent requests for the
        same key wait for each other, and a failure rolls everything back.
        """
        validate_idempotency_key(key)
        normalized = normalize_submission(data)
        fingerprint = request_fingerprint(normalized)
        with connect(self.database) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT request_hash, response_body FROM idempotency_keys WHERE key=?",
                             (key,)).fetchone()
            if row is not None:
                if row["request_hash"] != fingerprint:
                    raise DomainError("Idempotency-Key was already used with a different request", 409)
                return json.loads(row["response_body"]), True
            expense = new_expense(normalized)
            insert_expense(db, expense)
            db.execute("INSERT INTO idempotency_keys(key,request_hash,expense_id,response_status,"
                       "response_body,created_at) VALUES (?,?,?,?,?,?)",
                       (key, fingerprint, expense["id"], 201, json.dumps(expense), expense["created_at"]))
        return expense, False

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
