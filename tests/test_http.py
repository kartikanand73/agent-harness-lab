import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from expense_app.server import handler_for
from expense_app.service import ExpenseService
from expense_app.store import initialize


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "api.db")
        initialize(self.path)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(ExpenseService(self.path)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        request = Request(self.base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            response = urlopen(request, timeout=3)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_full_http_workflow(self):
        status, expense = self.request("/expenses", dict(employee="alice", amount_cents=500,
                                                        category="meals", description="Synthetic lunch"))
        self.assertEqual(status, 201)
        status, result = self.request(f'/expenses/{expense["id"]}/decision', dict(reviewer="bob", decision="approved"))
        self.assertEqual((status, result["status"]), (200, "approved"))
        self.assertEqual(self.request("/expenses")[1]["items"], [result])
        self.assertEqual(self.request(f'/expenses/{expense["id"]}'), (200, result))

    def test_malformed_and_nonobject_json(self):
        for raw in [b"{bad", b"[]", b'"text"', b"\xff"]:
            with self.subTest(raw=raw):
                self.assertEqual(self.request("/expenses", raw=raw)[0], 400)

    def test_health_and_missing_route(self):
        self.assertEqual(self.request("/health"), (200, {"status": "ok"}))
        self.assertEqual(self.request("/missing")[0], 404)
