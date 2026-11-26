"""Host side of a Codex App Server-shaped NDJSON session. Drives only the local stub here."""

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass
from itertools import count
from pathlib import Path

STUB = Path(__file__).resolve().parent / "synthetic_app_server.py"
STUB_OPTIONS = {"--ignore-term"}
TOOL = "stage_frame"
TOOL_FIELDS = {"component_id", "base_revision"}
MAX_LINE = 64 * 1024
EOF_MARK = object()


class ProtocolError(RuntimeError):
    """The peer sent or omitted something the host does not accept."""


class WorkerExited(ProtocolError):
    """The worker closed its output before the awaited message arrived."""


class WorkerCleanupFailed(RuntimeError):
    """The host could not confirm that the worker process group is gone."""


class RecoveryFailed(RuntimeError):
    """Native resume was unavailable; accepted state is unchanged and no turn was started."""


@dataclass(frozen=True)
class Accepted:
    """App-owned accepted scene state. Tool calls can only stage against it."""

    digest: str
    preview: str


class NativeHost:
    def __init__(self, accepted, state_dir, stub_options=()):
        # The worker is always the bundled synthetic stub. No caller-chosen executable.
        if not set(stub_options) <= STUB_OPTIONS:
            raise ValueError("unsupported stub option")
        self.accepted = accepted
        self.state_dir = Path(state_dir)
        self.stub_options = tuple(stub_options)
        self.process = None
        self.thread_id = None
        self.ids = count(1)
        self.reset_session()
        self.staged = []
        self.tool_log = []
        self.server_requests = []
        self.reaps = []

    def reset_session(self):
        self.inbox = queue.Queue()
        self.pending = {}
        self.responses = {}
        self.notifications = []
        self.violations = []
        self.active_turn = None
        self.fenced = set()
        self.completed = {}

    def connect(self, timeout=5):
        if self.process is not None:
            raise ProtocolError("worker already running")
        self.reset_session()
        self.process = subprocess.Popen(
            [sys.executable, "-I", str(STUB), "--state", str(self.state_dir), *self.stub_options],
            cwd=self.state_dir,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", "HOME": str(self.state_dir)},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        self.reader = threading.Thread(
            target=self._read, args=(self.process.stdout, self.inbox), daemon=True
        )
        self.reader.start()
        info = {"clientInfo": {"name": "terrain-m0-b2", "title": None, "version": "0"}}
        result = self.request("initialize", info, timeout)
        self.notify("initialized")
        return result

    def _read(self, stream, inbox):
        try:
            while line := stream.readline(MAX_LINE + 1):
                if len(line) > MAX_LINE or not line.endswith(b"\n"):
                    inbox.put({"_violation": "oversized_line"})
                    while line and not line.endswith(b"\n"):
                        line = stream.readline(MAX_LINE + 1)
                    continue
                try:
                    message = json.loads(line)
                except ValueError:
                    message = {"_violation": "invalid_json"}
                inbox.put(message if isinstance(message, dict) else {"_violation": "not_object"})
        finally:
            inbox.put(EOF_MARK)

    def _send(self, message):
        try:
            self.process.stdin.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
            self.process.stdin.flush()
        except (OSError, ValueError) as error:
            raise WorkerExited("worker input closed") from error

    def notify(self, method, params=None):
        self._send({"method": method} | ({"params": params} if params is not None else {}))

    def request(self, method, params, timeout=5):
        request_id = next(self.ids)
        self.pending[request_id] = method
        self._send({"id": request_id, "method": method, "params": params})
        try:
            self._pump(lambda: request_id in self.responses, timeout, method)
        except ProtocolError:
            # A reply that arrives after we gave up must be flagged, not silently accepted.
            self.pending.pop(request_id, None)
            raise
        response = self.responses.pop(request_id)
        if "error" in response:
            raise ProtocolError(f"{method} error {response['error'].get('code')}")
        return response.get("result")

    def _pump(self, done, timeout, waiting_for):
        deadline = time.monotonic() + timeout
        while not done():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProtocolError(f"timed out waiting for {waiting_for}")
            try:
                message = self.inbox.get(timeout=min(remaining, 0.1))
            except queue.Empty:
                continue
            if message is EOF_MARK:
                self.pending.clear()
                raise WorkerExited(f"worker exited while waiting for {waiting_for}")
            self._dispatch(message)

    def _dispatch(self, message):
        if "_violation" in message:
            self.violations.append({"kind": message["_violation"]})
        elif "method" in message and "id" in message:
            self._send({"id": message["id"], **self._serve(message)})
        elif "method" in message:
            self._notification(message["method"], message.get("params") or {})
        elif "id" in message and ("result" in message) != ("error" in message):
            if self.pending.pop(message["id"], None) is None:
                self.violations.append({"kind": "unmatched_response", "id": message["id"]})
            else:
                self.responses[message["id"]] = message
        else:
            self.violations.append({"kind": "malformed_message"})

    def _notification(self, method, params):
        turn = params.get("turn") or {}
        self.notifications.append(method)
        if method == "turn/started" and params.get("threadId") == self.thread_id:
            self.active_turn = turn.get("id")
        elif method == "turn/completed" and params.get("threadId") == self.thread_id:
            self.completed[turn.get("id")] = turn.get("status")
            if turn.get("id") == self.active_turn:
                self.active_turn = None

    def _serve(self, message):
        method, params = message["method"], message.get("params") or {}
        self.server_requests.append(method)
        if method == "item/tool/call":
            return {"result": self._tool_call(params)}
        if method.endswith("/requestApproval"):
            return {"result": {"decision": "decline"}}
        return {"error": {"code": -32601, "message": "method not supported by host"}}

    def _refusal(self, params):
        arguments = params.get("arguments")
        if params.get("threadId") != self.thread_id:
            return "thread_mismatch"
        turn = params.get("turnId")
        if turn is None or turn != self.active_turn or turn in self.fenced:
            return "stale_turn"
        if params.get("tool") != TOOL:
            return "unregistered_tool"
        if not isinstance(arguments, dict) or set(arguments) != TOOL_FIELDS:
            return "invalid_arguments"
        if arguments["component_id"] != "frame":
            return "out_of_scope"
        if arguments["base_revision"] != self.accepted.digest:
            return "stale_base"
        return None

    def _tool_call(self, params):
        reason = self._refusal(params)
        entry = {"callId": params.get("callId"), "tool": params.get("tool")}
        if reason is None:
            # Fixed receipt only. The real A1 worker and any Blender edit are out of scope here.
            text = f"staged frame from {self.accepted.digest[:12]}"
            self.staged.append({"turnId": params["turnId"], "base": self.accepted.digest})
            self.tool_log.append(entry | {"verdict": "allowed"})
        else:
            text = f"refused: {reason}"
            self.tool_log.append(entry | {"verdict": "refused", "reason": reason})
        return {"contentItems": [{"type": "inputText", "text": text}], "success": reason is None}

    def start_thread(self, timeout=5):
        result = self.request("thread/start", {"ephemeral": False}, timeout)
        self.thread_id = result["thread"]["id"]
        return self.thread_id

    def start_turn(self, text, timeout=5):
        if self.active_turn is not None:
            raise ProtocolError("a turn is already active")
        params = {"threadId": self.thread_id, "input": [{"type": "text", "text": text}]}
        turn_id = self.request("turn/start", params, timeout)["turn"]["id"]

        def started():
            return self.active_turn == turn_id or turn_id in self.completed

        self._pump(started, timeout, "turn/started")
        return turn_id

    def wait_turn(self, turn_id, timeout=5):
        self._pump(lambda: turn_id in self.completed, timeout, "turn/completed")
        return self.completed[turn_id]

    def run_turn(self, text, timeout=5):
        turn_id = self.start_turn(text, timeout)
        return turn_id, self.wait_turn(turn_id, timeout)

    def interrupt(self, timeout=5):
        turn_id = self.active_turn
        if turn_id is None:
            raise ProtocolError("no active turn to interrupt")
        self.fenced.add(turn_id)
        self.request("turn/interrupt", {"threadId": self.thread_id, "turnId": turn_id}, timeout)
        return self.wait_turn(turn_id, timeout)

    def close(self, grace=2):
        process, self.process = self.process, None
        if process is None:
            return None
        how = "exited"
        with suppress(OSError):
            process.stdin.close()
        try:
            try:
                process.wait(timeout=grace)
            except subprocess.TimeoutExpired:
                how = "sigterm"
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    how = "sigkill"
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=grace)
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                pass
            else:
                raise WorkerCleanupFailed("worker process group still present")
        except (OSError, subprocess.SubprocessError) as error:
            raise WorkerCleanupFailed("worker reap not verified") from error
        finally:
            self.reader.join(timeout=grace)
            with suppress(OSError):
                process.stdout.close()
        reap = {"how": how, "returncode": process.returncode}
        self.reaps.append(reap)
        return reap

    def recover(self, last_completed_turn, timeout=5):
        """Reopen the same thread natively; otherwise fail without starting new work."""
        thread_id = self.thread_id
        self.close()
        try:
            self.connect(timeout)
            self.thread_id = thread_id
            thread = self.request("thread/resume", {"threadId": thread_id}, timeout)["thread"]
            turns = {turn["id"]: turn["status"] for turn in thread.get("turns", [])}
            if thread.get("id") != thread_id or turns.get(last_completed_turn) != "completed":
                raise ProtocolError("resumed thread does not match app-owned journal")
        except (ProtocolError, OSError, KeyError, TypeError, AttributeError) as error:
            self.close()
            raise RecoveryFailed(str(error) or type(error).__name__) from error
        return thread_id
