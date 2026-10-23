"""H001 external API checks. Intentionally fail on the starter baseline.

Run separately: python -m acceptance.h001
Keep this check unchanged during H001. Add further tests under tests/.
"""
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from expense_app.server import handler_for
from expense_app.service import ExpenseService
from expense_app.store import connect, initialize


class IdempotencyAcceptance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "acceptance.db")
        initialize(self.path)
        self.payload = dict(employee="alice", amount_cents=12500,
                            category="travel", description="Synthetic train ticket")
        self.start()
        self.addCleanup(self.stop)

    def start(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(ExpenseService(self.path)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, path="/expenses", payload=None, key=None):
        headers = {"Content-Type": "application/json"}
        if key is not None:
            headers["Idempotency-Key"] = key
        data = None if payload is None else json.dumps(payload).encode()
        request = Request(self.base + path, data=data, headers=headers)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, dict(response.headers), json.loads(response.read())

    def test_replay_and_single_audit_event(self):
        first = self.request(payload=self.payload, key="expense-001")
        second = self.request(payload=self.payload, key="expense-001")
        self.assertEqual((first[0], second[0]), (201, 200))
        self.assertEqual(first[1].get("Idempotency-Replayed"), "false")
        self.assertEqual(second[1].get("Idempotency-Replayed"), "true")
        self.assertEqual(first[2], second[2])
        with connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM expenses").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], 1)

    def test_different_payload_conflicts(self):
        self.request(payload=self.payload, key="conflict")
        result = self.request(payload={**self.payload, "amount_cents":25000}, key="conflict")
        self.assertEqual(result[0], 409)
        self.assertEqual(len(self.request()[2]["items"]), 1)

    def test_no_key_preserves_baseline(self):
        first = self.request(payload=self.payload)
        second = self.request(payload=self.payload)
        self.assertEqual((first[0], second[0]), (201, 201))
        self.assertNotEqual(first[2]["id"], second[2]["id"])

    def test_invalid_keys_create_nothing(self):
        for key in ["", "contains space", "slash/key", "x" * 101]:
            with self.subTest(key=key):
                self.assertEqual(self.request(payload=self.payload, key=key)[0], 400)
        self.assertEqual(self.request()[2]["items"], [])

    def test_invalid_payload_does_not_reserve_key(self):
        self.assertEqual(self.request(payload={**self.payload, "amount_cents":0}, key="retry")[0], 400)
        self.assertEqual(self.request(payload=self.payload, key="retry")[0], 201)
        self.assertEqual(self.request(payload=self.payload, key="retry")[0], 200)

    def test_normalization_and_json_order(self):
        first = self.request(payload=self.payload, key="normal")
        reordered = dict(reversed(list(self.payload.items())))
        reordered.update(employee=" alice ", description=" Synthetic train ticket ", ignored="extra")
        second = self.request(payload=reordered, key="normal")
        self.assertEqual(second[0], 200)
        self.assertEqual(first[2], second[2])

    def test_original_response_after_decision_and_restart(self):
        first = self.request(payload=self.payload, key="durable")
        self.assertEqual(first[0], 201)
        decided = self.request(path=f'/expenses/{first[2]["id"]}/decision',
                               payload=dict(reviewer="bob", decision="approved"))
        self.assertEqual(decided[0], 200)
        self.stop()
        self.start()
        replay = self.request(payload=self.payload, key="durable")
        self.assertEqual(replay[0], 200)
        self.assertEqual(replay[2], first[2])
        self.assertEqual(self.request(path=f'/expenses/{first[2]["id"]}')[2]["status"], "approved")

    def test_concurrent_same_key_has_one_creation(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: self.request(payload=self.payload, key="parallel"), range(4)))
        self.assertEqual(sorted(result[0] for result in results), [200, 200, 200, 201])
        self.assertEqual(len({result[2]["id"] for result in results}), 1)
        with connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM expenses").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
