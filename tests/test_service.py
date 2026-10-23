import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from expense_app.service import DomainError, ExpenseService
from expense_app.store import connect, initialize


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "test.db")
        initialize(self.path)
        self.service = ExpenseService(self.path)
        self.payload = dict(employee="alice", amount_cents=12500,
                            category="travel", description="Synthetic train ticket")

    def test_submit_get_and_list(self):
        expense = self.service.submit(self.payload)
        self.assertEqual(expense["status"], "pending")
        self.assertEqual(self.service.get(expense["id"]), expense)
        self.assertEqual(self.service.list(), [expense])

    def test_amount_validation(self):
        for amount in [0, -1, True, 1.5, "100", None, 100_000_001]:
            with self.subTest(amount=amount), self.assertRaises(DomainError):
                self.service.submit({**self.payload, "amount_cents": amount})
        self.assertEqual(self.service.list(), [])

    def test_category_and_required_text_validation(self):
        for field, value in [("category", "other"), ("category", []),
                             ("employee", " "), ("description", None)]:
            with self.subTest(field=field, value=value), self.assertRaises(DomainError):
                self.service.submit({**self.payload, field: value})

    def test_approve_and_audit(self):
        expense = self.service.submit(self.payload)
        result = self.service.decide(expense["id"], dict(reviewer="bob", decision="approved"))
        self.assertEqual(result["status"], "approved")
        with connect(self.path) as db:
            actions = [row[0] for row in db.execute("SELECT action FROM audit_events ORDER BY id")]
        self.assertEqual(actions, ["submitted", "approved"])

    def test_reject(self):
        expense = self.service.submit(self.payload)
        self.assertEqual(self.service.decide(expense["id"], dict(reviewer="bob", decision="rejected"))["status"], "rejected")

    def test_self_review_forbidden(self):
        expense = self.service.submit(self.payload)
        with self.assertRaises(DomainError) as error:
            self.service.decide(expense["id"], dict(reviewer="ALICE", decision="approved"))
        self.assertEqual(error.exception.status, 403)
        self.assertEqual(self.service.get(expense["id"])["status"], "pending")

    def test_second_decision_conflicts(self):
        expense = self.service.submit(self.payload)
        decision = dict(reviewer="bob", decision="approved")
        self.service.decide(expense["id"], decision)
        with self.assertRaises(DomainError) as error:
            self.service.decide(expense["id"], decision)
        self.assertEqual(error.exception.status, 409)

    def test_concurrent_decisions_have_one_winner(self):
        expense = self.service.submit(self.payload)
        def attempt(reviewer):
            try:
                self.service.decide(expense["id"], dict(reviewer=reviewer, decision="approved"))
                return 200
            except DomainError as exc:
                return exc.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ["bob", "charlie"]))
        self.assertEqual(sorted(results), [200, 409])

    def test_missing_expense(self):
        with self.assertRaises(DomainError) as error:
            self.service.get("missing")
        self.assertEqual(error.exception.status, 404)

    def test_persistence_across_service_instances(self):
        expense = self.service.submit(self.payload)
        self.assertEqual(ExpenseService(self.path).get(expense["id"]), expense)
