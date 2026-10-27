"""Small local HTTP adapter. Not a production web server or identity system."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .service import DomainError, ExpenseService, validate_idempotency_key
from .store import initialize


def handler_for(service):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, body, headers=None):
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(encoded)

        def body(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16384:
                    raise DomainError("body must be between 1 and 16384 bytes")
                if self.headers.get_content_type() != "application/json":
                    raise DomainError("Content-Type must be application/json", 415)
                value = json.loads(self.rfile.read(size))
                if not isinstance(value, dict):
                    raise DomainError("request must be a JSON object")
                return value
            except (ValueError, UnicodeDecodeError) as exc:
                raise DomainError("invalid JSON body or Content-Length") from exc

        def submit_expense(self):
            # Read the body (with its usual size and JSON checks) before
            # rejecting a bad key. Responding while the body is still unread
            # lets the OS reset the connection, so the client may never see
            # the 400. Nothing is written to the database until both pass.
            payload = self.body()
            # The header value is used exactly as http.server exposes it. Its
            # parser drops leading spaces/tabs but keeps trailing ones, which
            # then fail validation. No extra trimming happens here.
            keys = self.headers.get_all("Idempotency-Key")
            if keys is None:
                return 201, service.submit(payload), {"Idempotency-Replayed": "false"}
            if len(keys) != 1:
                raise DomainError("Idempotency-Key header must be sent at most once")
            key = validate_idempotency_key(keys[0])
            body, replayed = service.submit_idempotent(payload, key)
            return (200 if replayed else 201), body, {"Idempotency-Replayed": "true" if replayed else "false"}

        def dispatch(self):
            path = urlsplit(self.path).path
            parts = path.strip("/").split("/")
            if self.command == "GET":
                if path == "/health":
                    return 200, {"status": "ok"}, None
                if path == "/expenses":
                    return 200, {"items": service.list()}, None
                if len(parts) == 2 and parts[0] == "expenses":
                    return 200, service.get(parts[1]), None
            if self.command == "POST":
                if path == "/expenses":
                    return self.submit_expense()
                if len(parts) == 3 and parts[0] == "expenses" and parts[2] == "decision":
                    return 200, service.decide(parts[1], self.body()), None
            raise DomainError("route not found", 404)

        def run_request(self):
            try:
                status, body, headers = self.dispatch()
            except DomainError as exc:
                status, body, headers = exc.status, {"error": str(exc)}, None
            self.respond(status, body, headers)

        do_GET = run_request
        do_POST = run_request

    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="expenses.db")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    initialize(args.db)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(ExpenseService(args.db)))
    print(f"Expense API: http://127.0.0.1:{server.server_port} (local training only)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
