"""Provisional macOS worker boundary for this fixture only. Never falls back unconfined."""

import json
import os
import platform
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager, suppress
from pathlib import Path

BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")
SANDBOX = Path("/usr/bin/sandbox-exec")
BASE = ["--background", "--factory-startup", "--disable-autoexec", "--threads", "1"]

# dyld bootstrap is an OS-private dependency. This is not a portable/app sandbox.
POLICY = """(version 1)
(deny default)
(import "dyld-support.sb")
(allow file-read-metadata file-test-existence)
(allow sysctl-read)
(allow process-info* (target self))
(allow signal (target self))
(deny network* process-fork)
(allow process-exec (literal "/Applications/Blender.app/Contents/MacOS/Blender"))
(allow file-read* file-map-executable
  (subpath "/usr/lib") (subpath "/System/Library") (subpath "/private/var/db/dyld")
  (subpath "/Applications/Blender.app") (literal "/dev/null") (literal "/dev/urandom"))
(allow file-read* (subpath (param "M0_INPUTS")))
(allow file-read* file-write* (subpath (param "M0_STAGE")))
"""


class Blocked(RuntimeError):
    """A prerequisite or observed safety check failed."""


def require(condition, message):
    if not condition:
        raise Blocked(message)


class OfflineWorker:
    def __init__(self, inputs, stage):
        require(
            platform.system() == "Darwin" and platform.machine() == "arm64",
            "only the macOS arm64 fixture route is supported",
        )
        require(
            BLENDER.is_file() and SANDBOX.is_file(), "installed Blender or sandbox-exec missing"
        )
        self.inputs, self.stage = inputs, stage
        for name in ("home", "tmp"):
            (stage / name).mkdir()
        self.env = {
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "HOME": str(stage / "home"),
            "TMPDIR": str(stage / "tmp"),
        }

    @contextmanager
    def launch(self, args):
        command = [
            SANDBOX,
            "-D",
            f"M0_INPUTS={self.inputs}",
            "-D",
            f"M0_STAGE={self.stage}",
            "-p",
            POLICY,
            BLENDER,
            *args,
        ]
        with subprocess.Popen(
            command,
            cwd=self.stage,
            env=self.env,
            close_fds=True,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        ) as process:
            try:
                yield process
            finally:
                if process.poll() is None:
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)

    def run(self, args):
        with self.launch(args) as process:
            output, _ = process.communicate(timeout=30)
            detail = output.replace(str(self.stage.parent), "<scratch>").strip()[-450:]
            require(process.returncode == 0, f"offline Blender exit {process.returncode}: {detail}")
            return output

    def fixture(self, *args, project=None):
        options = BASE + ([str(project)] if project else [])
        return self.run(
            [
                *options,
                "--python-exit-code",
                "1",
                "--python",
                str(self.inputs / "blender_fixture.py"),
                "--",
                *args,
            ]
        )

    def controls(self, control):
        files = {
            self.inputs / "fixture.txt": b"read only\n",
            control / "unlisted.txt": b"out of scope\n",
            control / "canonical.json": b'{"accepted":"baseline"}\n',
            control / "approvals.json": b"[]\n",
        }
        for path, value in files.items():
            path.write_bytes(value)
        (self.stage / "outside-link").symlink_to(control / "unlisted.txt")

        def trial(confined):
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen(1)
                listener.settimeout(0.1)
                args = ["--", str(self.inputs), str(control), str(listener.getsockname()[1])]
                if confined:
                    output = self.run(
                        [
                            *BASE,
                            "--python-exit-code",
                            "1",
                            "--python",
                            str(self.inputs / "worker_canary.py"),
                            *args,
                        ]
                    )
                else:
                    # Positive control runs only this fixed, known fixture script, never Blender.
                    output = subprocess.run(
                        [sys.executable, "-I", self.inputs / "worker_canary.py", *args],
                        env={**self.env, "M0_A1_SYNTHETIC_MARKER": "positive-control"},
                        cwd=self.stage,
                        stdin=subprocess.DEVNULL,
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=15,
                    ).stdout
                lines = [line[10:] for line in output.splitlines() if line.startswith("M0_CANARY ")]
                require(len(lines) == 1, "canary did not report exactly one result")
                try:
                    peer, _ = listener.accept()
                    with peer:
                        peer.settimeout(0.2)
                        payload = peer.recv(32)
                except TimeoutError:
                    payload = b""
                return json.loads(lines[0]), payload

        positive, received = trial(False)
        allowed = {"input_read", "stage_write"}
        denied = {
            "input_write",
            "out_of_scope_read",
            "linked_outside_read",
            "linked_outside_write",
            "canonical_write",
            "approval_write",
            "loopback",
            "child_exec",
        }
        require(
            received == b"m0-synthetic"
            and all(positive.get(name) == "allowed" for name in allowed | denied)
            and positive["marker_present"] is True,
            "broken synthetic positive control",
        )
        (self.stage / "canary.out").unlink()
        for path, value in files.items():
            path.write_bytes(value)
        actual, received = trial(True)
        require(
            not received
            and all(actual.get(name) == "allowed" for name in allowed)
            and all(actual.get(name) == "denied" for name in denied)
            and actual["synthetic_home"] is True
            and actual["marker_present"] is False,
            f"unexpected offline Blender canary result: {actual}",
        )
        require(
            (self.stage / "canary.out").read_bytes() == b"canary\n"
            and all(path.read_bytes() == value for path, value in files.items()),
            "synthetic control bytes changed",
        )
        return actual

    def cancellation(self):
        code = 'from pathlib import Path; import time; Path("ready").touch(); time.sleep(60)'
        with self.launch([*BASE, "--python-exit-code", "1", "--python-expr", code]) as process:
            deadline = time.monotonic() + 10
            while not (self.stage / "ready").is_file() and process.poll() is None:
                require(time.monotonic() < deadline, "sandboxed Blender did not become ready")
                time.sleep(0.02)
            require(process.poll() is None, "sandboxed Blender exited before cancellation")
        require(process.returncode == -signal.SIGKILL, "sandboxed Blender was not reaped on cancel")
        require(not (self.stage / "candidate.blend").exists(), "cancellation published a candidate")
