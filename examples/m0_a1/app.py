"""A loopback-only shell for one fixed, offline Blender staging operation."""

import json
import signal
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from offline_worker import Blocked, require
from verify import verify

HERE = Path(__file__).resolve().parent
VIEWS = {"/svg": "compare.html", "/depth": "depth.html"}


class Stager:
    def __init__(self, run_fixture=verify):
        self.run_fixture = run_fixture
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = None
        self.closed = False
        self.job = 0
        self.status = "idle"
        self.phase = "Ready to stage the fixed edit"
        self.candidate = None
        self.views = {}

    def state(self):
        with self.lock:
            return {
                "job": self.job,
                "status": self.status,
                "phase": self.phase,
                "candidate": self.candidate,
            }

    def start(self):
        with self.lock:
            if self.closed or self.status == "running":
                return False
            self.job += 1
            self.stop.clear()
            self.status, self.phase = "running", "Starting offline fixture"
            self.thread = threading.Thread(target=self._run)
            self.thread.start()
            return True

    def cancel(self, job):
        with self.lock:
            if self.status != "running" or job != str(self.job) or self.stop.is_set():
                return False
            self.stop.set()
            self.phase = "Cancelling; waiting for worker cleanup"
            return True

    def close(self):
        with self.lock:
            self.closed = True
            self.stop.set()
        if self.thread is not None:
            self.thread.join()

    def view(self, route):
        with self.lock:
            return self.views.get(route)

    def _run(self):
        def check():
            require(not self.stop.is_set(), "app staging cancelled")

        def progress(phase):
            with self.lock:
                check()
                self.phase = phase

        data = views = None
        try:
            # This parent is exclusively owned by this job. The worker cannot write outside stage.
            with tempfile.TemporaryDirectory(prefix="terrain-m0-app-") as name:
                parent = Path(name).resolve()
                work, output = parent / "work", parent / "candidate"
                work.mkdir(mode=0o700)
                manifest = self.run_fixture(work, 1, output, check, progress, probe_storage=False)
                views = {route: (output / file).read_bytes() for route, file in VIEWS.items()}
            data = manifest["artifact_sha256"]["candidate.blend"]
        except Exception as error:
            # This endpoint exposes no process output, local path, or caller-supplied diagnostics.
            if not isinstance(error, Blocked) and not self.stop.is_set():
                print(f"Offline fixture blocked: {type(error).__name__}", file=sys.stderr)
        with self.lock:
            if self.stop.is_set():
                self.status, self.phase = "cancelled", "Cancelled; candidate not published"
            elif data is not None:
                self.status, self.phase = "staged", "Verified candidate staged; nothing accepted"
                self.candidate, self.views = data, views
            else:
                self.status, self.phase = (
                    "blocked",
                    "Offline fixture blocked; candidate not published",
                )


class Shell(ThreadingHTTPServer):
    def __init__(self, stager):
        self.stager = stager
        self.page = (HERE / "shell.html").read_bytes()
        super().__init__(("127.0.0.1", 0), Handler)
        self.host = f"127.0.0.1:{self.server_port}"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def reply(self, status, body=b"", content="text/plain; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.headers.get("Host") != self.server.host:
            self.reply(403)
        elif self.path == "/":
            self.reply(200, self.server.page, "text/html; charset=utf-8")
        elif self.path == "/state":
            state = json.dumps(self.server.stager.state()).encode()
            self.reply(200, state, "application/json")
        elif self.path in VIEWS and (page := self.server.stager.view(self.path)):
            self.reply(200, page, "text/html; charset=utf-8")
        else:
            self.reply(404)

    def do_POST(self):
        if (
            self.headers.get("Host") != self.server.host
            or self.headers.get("Origin") != f"http://{self.server.host}"
            or self.headers.get("X-M0-Action") != "fixed-fixture"
            or self.headers.get("Content-Length") not in (None, "0")
            or "Transfer-Encoding" in self.headers
        ):
            self.reply(403)
        elif self.path == "/run":
            self.reply(202 if self.server.stager.start() else 409)
        elif self.path.startswith("/cancel/"):
            self.reply(
                202 if self.server.stager.cancel(self.path.removeprefix("/cancel/")) else 409
            )
        else:
            self.reply(404)


def main():
    if len(sys.argv) != 1:
        raise SystemExit("This fixed fixture shell takes no options")
    stager = Stager()

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        with Shell(stager) as shell:
            print(f"http://{shell.host}/", flush=True)
            shell.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stager.close()


if __name__ == "__main__":
    main()
