"""H001 regression tests: idempotent expense submission."""
import http.client
import json
import socket
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

from expense_app.server import handler_for
from expense_app.service import DomainError, ExpenseService, validate_idempotency_key
from expense_app.store import connect, initialize

PAYLOAD = dict(employee="alice", amount_cents=12500, category="travel",
               description="Synthetic train ticket")

# Schema exactly as shipped before H001, used to test upgrading old databases.
BASELINE_SCHEMA = '''
CREATE TABLE expenses (
    id TEXT PRIMARY KEY,
    employee TEXT NOT NULL,
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending','approved','rejected')),
    reviewer TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_id TEXT NOT NULL REFERENCES expenses(id),
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TEXT NOT NULL
);
'''


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "idempotency.db")
        initialize(self.path)
        self.service = ExpenseService(self.path)

    def count(self, table, where="1=1"):
        with connect(self.path) as db:
            return db.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]

    def counts(self):
        return (self.count("expenses"), self.count("audit_events"), self.count("idempotency_keys"))


class KeyValidationTests(unittest.TestCase):
    def test_valid_keys(self):
        for key in ["a", "x" * 100, "A-z_0.9", "-", "...", "ABC123"]:
            with self.subTest(key=key):
                self.assertEqual(validate_idempotency_key(key), key)

    def test_invalid_keys(self):
        for key in ["", " ", " a", "a ", "a\t", "a\n", "x" * 101, "a b", "a/b", "a:b",
                    "café", "ａ", "a+b", None, 123, b"abc"]:
            with self.subTest(key=key), self.assertRaises(DomainError) as error:
                validate_idempotency_key(key)
            self.assertEqual(error.exception.status, 400)


class ServiceIdempotencyTests(DatabaseCase):
    def test_submit_without_key_is_unchanged(self):
        first = self.service.submit(PAYLOAD)
        second = self.service.submit(PAYLOAD)
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(set(first), {"id", "employee", "amount_cents", "category", "description",
                                      "status", "reviewer", "created_at"})
        self.assertEqual(self.counts(), (2, 2, 0))

    def test_first_request_creates_and_replay_returns_original(self):
        created, replayed = self.service.submit_idempotent(PAYLOAD, "key-1")
        self.assertFalse(replayed)
        self.assertEqual(created["status"], "pending")
        again, replayed = self.service.submit_idempotent(PAYLOAD, "key-1")
        self.assertTrue(replayed)
        self.assertEqual(again, created)
        self.assertEqual(self.counts(), (1, 1, 1))
        with connect(self.path) as db:
            row = db.execute("SELECT * FROM idempotency_keys").fetchone()
        self.assertEqual((row["key"], row["expense_id"], row["response_status"]), ("key-1", created["id"], 201))
        self.assertEqual(json.loads(row["response_body"]), created)

    def test_replay_after_decisions_and_new_service_instance(self):
        for decision in ["approved", "rejected"]:
            with self.subTest(decision=decision):
                key = f"decided-{decision}"
                created, _ = self.service.submit_idempotent(PAYLOAD, key)
                self.service.decide(created["id"], dict(reviewer="bob", decision=decision))
                replay, replayed = ExpenseService(self.path).submit_idempotent(PAYLOAD, key)
                self.assertTrue(replayed)
                self.assertEqual(replay, created)
                self.assertEqual(replay["status"], "pending")
                self.assertEqual(self.service.get(created["id"])["status"], decision)
                self.assertEqual(self.count("audit_events", f"expense_id='{created['id']}'"), 2)

    def test_different_payload_conflicts_without_writes(self):
        created, _ = self.service.submit_idempotent(PAYLOAD, "conflict")
        changes = [("employee", "Alice"), ("employee", "bob"), ("amount_cents", 12501),
                   ("category", "meals"), ("description", "Synthetic train ticket!")]
        for field, value in changes:
            with self.subTest(field=field, value=value), self.assertRaises(DomainError) as error:
                self.service.submit_idempotent({**PAYLOAD, field: value}, "conflict")
            self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.counts(), (1, 1, 1))
        self.assertEqual(self.service.submit_idempotent(PAYLOAD, "conflict"), (created, True))

    def test_normalization_ignores_order_whitespace_and_unknown_fields(self):
        created, _ = self.service.submit_idempotent(PAYLOAD, "normal")
        variant = {"description": "\t Synthetic train ticket \n", "category": "travel",
                   "amount_cents": 12500, "employee": "  alice  ", "unknown": [1, 2]}
        self.assertEqual(self.service.submit_idempotent(variant, "normal"), (created, True))
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_keys_are_case_sensitive(self):
        upper, _ = self.service.submit_idempotent(PAYLOAD, "Key")
        lower, replayed = self.service.submit_idempotent(PAYLOAD, "key")
        self.assertFalse(replayed)
        self.assertNotEqual(upper["id"], lower["id"])
        self.assertEqual(self.counts(), (2, 2, 2))

    def test_invalid_payload_does_not_reserve_key(self):
        for bad in [{**PAYLOAD, "amount_cents": 0}, {**PAYLOAD, "category": "other"}, [], "text"]:
            with self.subTest(bad=bad), self.assertRaises(DomainError):
                self.service.submit_idempotent(bad, "retry")
        self.assertEqual(self.counts(), (0, 0, 0))
        created, replayed = self.service.submit_idempotent(PAYLOAD, "retry")
        self.assertFalse(replayed)
        self.assertEqual(self.service.submit_idempotent(PAYLOAD, "retry"), (created, True))

    def test_invalid_key_writes_nothing(self):
        with self.assertRaises(DomainError):
            self.service.submit_idempotent(PAYLOAD, "bad key")
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_database_rejects_invalid_key_directly(self):
        expense, _ = self.service.submit_idempotent(PAYLOAD, "ok")
        for key in ["", "bad key", "x" * 101, "é"]:
            with self.subTest(key=key), self.assertRaises(sqlite3.IntegrityError), connect(self.path) as db:
                db.execute("INSERT INTO idempotency_keys VALUES (?,?,?,?,?,?)",
                           (key, "h", expense["id"], 201, "{}", "t"))


class AtomicWriteTests(DatabaseCase):
    """A test-only trigger makes one insert fail; nothing from the request may remain."""

    @contextmanager
    def failing_inserts_into(self, table):
        """Make inserts into `table` fail; the trigger is always removed afterwards."""
        with connect(self.path) as db:
            db.execute(f"CREATE TRIGGER fail_{table} BEFORE INSERT ON {table} "
                       "BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
        try:
            yield
        finally:
            with connect(self.path) as db:
                db.execute(f"DROP TRIGGER IF EXISTS fail_{table}")

    def test_rollback_when_any_insert_fails(self):
        for table in ["expenses", "audit_events", "idempotency_keys"]:
            with self.subTest(failing=table), self.failing_inserts_into(table):
                with self.assertRaises(sqlite3.DatabaseError):
                    self.service.submit_idempotent(PAYLOAD, f"atomic-{table}")
                self.assertEqual(self.counts(), (0, 0, 0))

    def test_key_is_reusable_after_rollback(self):
        with self.failing_inserts_into("idempotency_keys"):
            with self.assertRaises(sqlite3.DatabaseError):
                self.service.submit_idempotent(PAYLOAD, "after-failure")
        created, replayed = self.service.submit_idempotent(PAYLOAD, "after-failure")
        self.assertFalse(replayed)
        self.assertEqual(self.counts(), (1, 1, 1))


class ConcurrencyTests(DatabaseCase):
    WORKERS = 8

    def run_together(self, payloads, keys):
        """Start all submissions at the same moment using a barrier."""
        barrier = threading.Barrier(len(payloads))

        def attempt(args):
            payload, key = args
            barrier.wait()
            try:
                body, replayed = ExpenseService(self.path).submit_idempotent(payload, key)
                return ("replayed" if replayed else "created"), body["id"], payload["amount_cents"]
            except DomainError as exc:
                return exc.status, None, payload["amount_cents"]

        with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
            return list(pool.map(attempt, zip(payloads, keys)))

    def test_same_key_same_payload_creates_once(self):
        for round_number in range(3):
            with self.subTest(round=round_number):
                key = f"parallel-{round_number}"
                results = self.run_together([PAYLOAD] * self.WORKERS, [key] * self.WORKERS)
                outcomes = sorted(result[0] for result in results)
                self.assertEqual(outcomes, ["created"] + ["replayed"] * (self.WORKERS - 1))
                self.assertEqual(len({result[1] for result in results}), 1)
                expense_id = results[0][1]
                self.assertEqual(self.count("audit_events", f"expense_id='{expense_id}' AND action='submitted'"), 1)
        self.assertEqual(self.counts(), (3, 3, 3))

    def test_same_key_different_payloads_creates_once(self):
        payloads = [PAYLOAD if i % 2 else {**PAYLOAD, "amount_cents": 999} for i in range(self.WORKERS)]
        results = self.run_together(payloads, ["mixed"] * self.WORKERS)
        winners = [result for result in results if result[0] == "created"]
        self.assertEqual(len(winners), 1)
        winning_amount = winners[0][2]
        for outcome, _, amount in results:
            if outcome != "created":
                self.assertEqual(outcome, "replayed" if amount == winning_amount else 409)
        self.assertEqual(self.counts(), (1, 1, 1))

    def test_distinct_keys_each_create(self):
        results = self.run_together([PAYLOAD] * self.WORKERS, [f"k{i}" for i in range(self.WORKERS)])
        self.assertEqual([result[0] for result in results], ["created"] * self.WORKERS)
        self.assertEqual(self.counts(), (self.WORKERS,) * 3)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "baseline.db")
        db = sqlite3.connect(self.path)
        with db:
            db.executescript(BASELINE_SCHEMA)
            db.execute("INSERT INTO expenses VALUES ('old-1','alice',500,'meals','Synthetic lunch',"
                       "'approved','bob','2026-01-01T00:00:00+00:00')")
            db.execute("INSERT INTO expenses VALUES ('old-2','carol',700,'supplies','Synthetic pens',"
                       "'pending',NULL,'2026-01-02T00:00:00+00:00')")
            db.executemany("INSERT INTO audit_events(expense_id,action,actor,created_at) VALUES (?,?,?,?)",
                           [("old-1", "submitted", "alice", "2026-01-01T00:00:00+00:00"),
                            ("old-1", "approved", "bob", "2026-01-01T01:00:00+00:00"),
                            ("old-2", "submitted", "carol", "2026-01-02T00:00:00+00:00")])
        db.close()

    def snapshot(self):
        with connect(self.path) as db:
            return ([tuple(row) for row in db.execute("SELECT * FROM expenses ORDER BY id")],
                    [tuple(row) for row in db.execute("SELECT * FROM audit_events ORDER BY id")])

    def tables(self):
        with connect(self.path) as db:
            return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def test_upgrade_keeps_data_and_adds_table(self):
        before = self.snapshot()
        self.assertNotIn("idempotency_keys", self.tables())
        initialize(self.path)
        initialize(self.path)  # running again must be harmless
        self.assertEqual(self.snapshot(), before)
        self.assertIn("idempotency_keys", self.tables())

    def test_upgraded_database_supports_old_and_new_operations(self):
        initialize(self.path)
        service = ExpenseService(self.path)
        self.assertEqual(service.decide("old-2", dict(reviewer="dave", decision="rejected"))["status"], "rejected")
        created, _ = service.submit_idempotent(PAYLOAD, "after-upgrade")
        self.assertEqual(service.submit_idempotent(PAYLOAD, "after-upgrade"), (created, True))
        self.assertEqual(len(service.list()), 3)


class HttpIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = str(Path(self.temp.name) / "http.db")
        initialize(self.path)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(ExpenseService(self.path)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def post(self, payload=PAYLOAD, keys=(), raw=None, content_type="application/json"):
        """POST /expenses with full control of headers, including repeated ones."""
        body = raw if raw is not None else json.dumps(payload).encode()
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            conn.putrequest("POST", "/expenses")
            conn.putheader("Content-Type", content_type)
            conn.putheader("Content-Length", str(len(body)))
            for key in keys:
                conn.putheader("Idempotency-Key", key)
            conn.endheaders(body)
            response = conn.getresponse()
            return response.status, response.getheader("Idempotency-Replayed"), json.loads(response.read())
        finally:
            conn.close()

    def count(self):
        with connect(self.path) as db:
            return db.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]

    def test_keyless_submission_reports_not_replayed(self):
        first = self.post()
        second = self.post()
        self.assertEqual((first[0], first[1]), (201, "false"))
        self.assertEqual((second[0], second[1]), (201, "false"))
        self.assertNotEqual(first[2]["id"], second[2]["id"])

    def test_created_then_replayed(self):
        created = self.post(keys=["http-1"])
        replay = self.post(keys=["http-1"])
        self.assertEqual(created[:2], (201, "false"))
        self.assertEqual(replay[:2], (200, "true"))
        self.assertEqual(replay[2], created[2])
        self.assertEqual(self.count(), 1)

    def test_conflict_returns_409_without_replay_header(self):
        self.post(keys=["http-conflict"])
        status, replayed, body = self.post({**PAYLOAD, "amount_cents": 1}, keys=["http-conflict"])
        self.assertEqual((status, replayed), (409, None))
        self.assertIn("error", body)
        self.assertEqual(self.count(), 1)

    def test_duplicate_headers_rejected(self):
        for keys in [["a", "b"], ["same", "same"]]:
            with self.subTest(keys=keys):
                status, _, body = self.post(keys=keys)
                self.assertEqual(status, 400)
                self.assertIn("at most once", body["error"])
        self.assertEqual(self.count(), 0)

    def test_invalid_header_values_rejected(self):
        for key in ["", "has space", "trailing ", "trailing\t", "x" * 101, "a/b", "a,b"]:
            with self.subTest(key=key):
                self.assertEqual(self.post(keys=[key])[0], 400)
        self.assertEqual(self.count(), 0)

    def test_parser_drops_leading_whitespace(self):
        # Documents http.server behaviour: leading spaces/tabs never reach the app.
        created = self.post(keys=["lead"])
        self.assertEqual(self.post(keys=["  lead"])[:2], (200, "true"))
        self.assertEqual(self.post(keys=["\tlead"])[2], created[2])
        self.assertEqual(self.count(), 1)

    def post_body_after_pause(self, key_lines, body):
        """Send headers, wait, then send the body.

        Returns (bytes_received_before_body, status, json_reply). If the server
        answers before the body is sent, returns early with status None.
        """
        sock = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=5)
        with sock:
            head = ("POST /expenses HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n" + "".join(key_lines) + "\r\n")
            sock.sendall(head.encode("latin-1"))
            sock.settimeout(0.3)
            try:
                early = sock.recv(1)
            except TimeoutError:
                early = b""
            if early:
                return early, None, None
            sock.settimeout(5)
            sock.sendall(body)
            chunks = []
            while chunk := sock.recv(65536):
                chunks.append(chunk)
        head, _, reply = b"".join(chunks).partition(b"\r\n\r\n")
        return early, int(head.split(b" ", 2)[1]), json.loads(reply)

    def test_bad_key_headers_answered_only_after_body_is_read(self):
        # Regression: replying before reading the body let the OS reset the
        # connection, so clients could get a socket error instead of the 400.
        body = json.dumps(PAYLOAD).encode()
        cases = {"invalid": ["Idempotency-Key: bad key\r\n"],
                 "empty": ["Idempotency-Key: \r\n"],
                 "duplicate": ["Idempotency-Key: a\r\n", "Idempotency-Key: b\r\n"]}
        for name, lines in cases.items():
            with self.subTest(case=name):
                early, status, reply = self.post_body_after_pause(lines, body)
                self.assertEqual(early, b"", "server replied before reading the request body")
                self.assertEqual(status, 400)
                self.assertIn("Idempotency-Key", reply["error"])
        self.assertEqual(self.count(), 0)

    def test_bad_key_with_large_body_always_gets_400(self):
        padded = json.dumps({**PAYLOAD, "padding": "x" * 16000}).encode()
        self.assertLessEqual(len(padded), 16384)
        for attempt in range(20):
            for keys in (["bad key"], ["a", "b"]):
                with self.subTest(attempt=attempt, keys=keys):
                    self.assertEqual(self.post(keys=keys, raw=padded)[0], 400)
        self.assertEqual(self.count(), 0)

    def test_rejected_bodies_do_not_reserve_key(self):
        self.assertEqual(self.post(raw=b"{bad", keys=["body-retry"])[0], 400)
        self.assertEqual(self.post(content_type="text/plain", keys=["body-retry"])[0], 415)
        self.assertEqual(self.post({**PAYLOAD, "amount_cents": 0}, keys=["body-retry"])[0], 400)
        self.assertEqual(self.post(keys=["body-retry"])[:2], (201, "false"))
        self.assertEqual(self.post(keys=["body-retry"])[:2], (200, "true"))

    def test_concurrent_http_requests_create_once(self):
        barrier = threading.Barrier(6)

        def attempt(_):
            barrier.wait()
            return self.post(keys=["http-parallel"])

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(attempt, range(6)))
        self.assertEqual(sorted(result[0] for result in results), [200] * 5 + [201])
        self.assertEqual(len({result[2]["id"] for result in results}), 1)
        self.assertEqual(self.count(), 1)


if __name__ == "__main__":
    unittest.main()
