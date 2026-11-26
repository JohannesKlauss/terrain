import hashlib
import json
import os
import platform
import selectors
import signal
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager, suppress
from http.client import HTTPConnection
from io import StringIO
from pathlib import Path

import pytest

VERIFIER = Path(__file__).parents[1] / "examples" / "m0_a1" / "verify.py"
BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")
needs_blender = pytest.mark.skipif(
    platform.system() != "Darwin"
    or platform.machine() != "arm64"
    or not BLENDER.is_file()
    or not Path("/usr/bin/sandbox-exec").is_file(),
    reason="M0 offline fixture requires macOS arm64, sandbox-exec and installed Blender",
)


def run_verifier(*args):
    return subprocess.run(
        [sys.executable, VERIFIER, *args], capture_output=True, text=True, timeout=45
    )


def test_existing_output_is_refused_without_touching_its_contents(tmp_path):
    original = tmp_path / "unchanged.txt"
    original.write_text("existing\n")
    result = run_verifier("--output", tmp_path)
    assert result.returncode == 1
    assert "output directory already exists" in result.stderr
    assert list(tmp_path.iterdir()) == [original]
    assert original.read_text() == "existing\n"


def test_m0_verifier_does_not_accept_external_worker_paths(tmp_path):
    script = tmp_path / "external.py"
    script.write_text("raise RuntimeError('unexpected external fixture')")
    output = tmp_path / "result"
    result = run_verifier("--script", script, "--output", output)
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
    assert not output.exists()


def test_loopback_accept_empty_is_not_a_denial(monkeypatch):
    monkeypatch.syspath_prepend(str(VERIFIER.parent))
    from offline_worker import observe_loopback

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(0.1)
        assert observe_loopback(listener) == (False, None)
        with socket.create_connection(listener.getsockname(), timeout=2) as peer:
            peer.shutdown(socket.SHUT_WR)
            assert observe_loopback(listener) == (True, b"")
        with socket.create_connection(listener.getsockname(), timeout=2):
            assert observe_loopback(listener) == (True, None)


@needs_blender
def test_real_m0_offline_scope_and_reproducibility(tmp_path, monkeypatch):
    monkeypatch.setenv("M0_A1_SYNTHETIC_MARKER", "supervisor-only")
    manifests = []
    for name in ("first", "repeat"):
        output = tmp_path / name
        result = run_verifier("--output", output)
        assert result.returncode == 0, result.stderr
        manifest = json.loads((output / "manifest.json").read_text())
        manifests.append(manifest)
        for artifact, digest in manifest["artifact_sha256"].items():
            assert hashlib.sha256((output / artifact).read_bytes()).hexdigest() == digest
        assert manifest["unit"] == "mm"
        assert manifest["target"] == "frame"
        assert manifest["profile"] == {"grid": 1, "assets": 5, "instances": 6, "triangles": 92}
        assert manifest["stl_bounds_mm"]["baseline"] == [[-12, -2, 0], [12, 2, 22]]
        assert manifest["stl_bounds_mm"]["candidate"] == [[-12, -2, 0], [12, 2, 23]]
        assert manifest["offline_controls"] == {
            "input_read": "allowed",
            "input_write": "denied",
            "stage_write": "allowed",
            "out_of_scope_read": "denied",
            "linked_outside_read": "denied",
            "linked_outside_write": "denied",
            "canonical_write": "denied",
            "approval_write": "denied",
            "loopback_connect": "denied",
            "loopback_send": "not_attempted",
            "loopback_accepted": False,
            "child_exec": "denied",
            "synthetic_home": True,
            "marker_present": False,
        }
        assert manifest["cancelled_and_reaped"]
        assert manifest["sealed_baseline_rewrite_denied"]
        storage = manifest["storage_probe"]
        hashes = manifest["artifact_sha256"]
        assert storage["request_base"] == hashes["baseline.blend"]
        for backend in ("atomic_file", "sqlite"):
            assert storage[backend]["reopened"] == hashes["candidate.blend"]
            assert storage[backend]["after_interruption"] == hashes["candidate.blend"]
            assert storage[backend]["stale_rejected"]
        assert not storage["atomic_file"]["cross_process_writer_fencing"]
        assert storage["sqlite"]["second_writer_blocked"]
        scope = json.loads((output / "scope.json").read_text())
        assert scope and all(manifest[key] == value for key, value in scope.items())
        viewer = (output / "compare.html").read_text()
        assert "Geometry picking is disabled" in viewer
        assert 'event.target.closest("[data-part]")' not in viewer
        base, candidate = [
            {entry["id"]: entry for entry in json.loads((output / f"{variant}.json").read_text())}
            for variant in ("baseline", "candidate")
        ]
        for identity in ("figure.body", "figure.hand-left", "figure.hand-right", "context.plinth"):
            assert identity in manifest["protected_ids"]
            assert base[identity] == candidate[identity]
        assert base["frame"]["vertices"] != candidate["frame"]["vertices"]
    stable_artifacts = (
        "baseline.json",
        "candidate.json",
        "scope.json",
        "prompt.txt",
        "reference.png",
    )
    for artifact in stable_artifacts:
        assert (
            manifests[0]["artifact_sha256"][artifact] == manifests[1]["artifact_sha256"][artifact]
        )


@needs_blender
def test_supervisor_sigterm_reaps_worker_and_discards_staged_candidate(tmp_path):
    staging = tmp_path / "verify-tmp"
    staging.mkdir()
    output = tmp_path / "result"
    cleanup_digest = tmp_path / "cleanup-digest"
    protected = (
        "inputs/baseline.blend",
        "inputs/baseline.json",
        "inputs/baseline-frame.stl",
        "inputs/scope.json",
        "control/canonical.json",
        "control/approvals.json",
    )
    # Pause the real, fixed Blender stage after it writes its output. No public CLI override.
    harness = """
import hashlib
import sys
from contextlib import contextmanager
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import verify

output, cleanup = map(Path, sys.argv[2:4])
protected = sys.argv[4:]
run = verify.OfflineWorker.run
temporary_directory = verify.tempfile.TemporaryDirectory
hold = ('import os,time; from pathlib import Path; '
        'Path("stage-worker.pid").write_text(str(os.getpid())); time.sleep(60)')

def hold_staging(worker, args, operation="version"):
    if "--" in args and args[args.index("--") + 1] == "stage":
        boundary = args.index("--")
        args = args[:boundary] + ["--python-expr", hold] + args[boundary:]
    return run(worker, args, operation)

@contextmanager
def observe_cleanup(*args, **kwargs):
    with temporary_directory(*args, **kwargs) as root:
        try:
            yield root
        finally:
            cleanup.write_text("\\n".join(
                hashlib.sha256((Path(root) / name).read_bytes()).hexdigest()
                for name in protected
            ))

verify.OfflineWorker.run = hold_staging
verify.tempfile.TemporaryDirectory = observe_cleanup
sys.argv = ["verify.py", "--output", str(output)]
raise SystemExit(verify.main())
"""
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-c",
            harness,
            str(VERIFIER.parent),
            str(output),
            str(cleanup_digest),
            *protected,
        ],
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "TMPDIR": str(staging)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    worker_pid = None
    worker_reaped = False
    try:
        deadline = time.monotonic() + 20
        while worker_pid is None and process.poll() is None and time.monotonic() < deadline:
            for ready in staging.glob("terrain-m0-a1-*/stage/stage-worker.pid"):
                value = ready.read_text()
                if value.isdecimal():
                    worker_pid = int(value)
                    root = ready.parent.parent
            if worker_pid is None:
                time.sleep(0.02)
        assert worker_pid is not None, "fixed Blender staging did not become ready"
        assert (root / "stage/candidate.blend").is_file()
        before = [hashlib.sha256((root / name).read_bytes()).hexdigest() for name in protected]
        process.send_signal(signal.SIGTERM)
        _, stderr = process.communicate(timeout=10)
        assert process.returncode == 1
        assert "supervisor cancelled by SIGTERM" in stderr
        assert cleanup_digest.read_text().splitlines() == before
        with pytest.raises(ProcessLookupError):
            os.kill(worker_pid, 0)
        worker_reaped = True
        assert not output.exists()
        assert not list(staging.iterdir())
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        if worker_pid is not None and not worker_reaped:
            with suppress(ProcessLookupError):
                os.killpg(worker_pid, signal.SIGKILL)
        process.stdout.close()
        process.stderr.close()


@needs_blender
def test_app_stages_real_candidate_and_preserves_it_on_cancel(monkeypatch):
    monkeypatch.syspath_prepend(str(VERIFIER.parent))
    from app import Shell, Stager
    from offline_worker import OfflineWorker

    active = []
    hold_stage = threading.Event()
    launch = OfflineWorker.launch

    @contextmanager
    def hold_active_stage(worker, args):
        hold = hold_stage.is_set() and "--" in args and args[args.index("--") + 1] == "stage"
        if hold:
            index = args.index("--")
            code = 'from pathlib import Path; import time; Path("active").touch(); time.sleep(10)'
            args = args[:index] + ["--python-expr", code] + args[index:]
        with launch(worker, args) as child:
            if hold:
                active.append((child, worker.stage))
            yield child

    monkeypatch.setattr(OfflineWorker, "launch", hold_active_stage)

    stager = Stager()
    with Shell(stager) as shell:
        thread = threading.Thread(target=shell.serve_forever)
        thread.start()
        try:
            headers = {"Origin": f"http://{shell.host}", "X-M0-Action": "fixed-fixture"}

            def request(method, path, request_headers=None, body=None):
                connection = HTTPConnection(shell.host, timeout=3)
                try:
                    connection.request(method, path, headers=request_headers or {}, body=body)
                    reply = connection.getresponse()
                    return reply.status, reply.read()
                finally:
                    connection.close()

            def state():
                status_code, body = request("GET", "/state")
                assert status_code == 200
                return json.loads(body)

            def wait(status):
                deadline = time.monotonic() + 25
                while time.monotonic() < deadline:
                    current = state()
                    if current["status"] == status:
                        return current
                    assert current["status"] != "blocked", current
                    time.sleep(0.025)
                pytest.fail(f"missing {status}: {state()}")

            assert request("GET", "/", {"Host": "not-loopback.invalid"})[0] == 403
            assert request("POST", "/run")[0] == 403
            assert request("POST", "/run", headers, body=b"external input")[0] == 403
            for path in ("/accept", "/commit", "/approve", "/stage?script=other.py"):
                assert request("POST", path, headers)[0] == 404
            assert request("GET", "/depth")[0] == 404
            assert request("POST", "/run", headers)[0] == 202
            assert wait("running")["phase"] != "Ready to stage the fixed edit"
            assert request("POST", "/run", headers)[0] == 409
            assert request("POST", "/cancel/0", headers)[0] == 409
            completed = wait("staged")
            assert len(completed["candidate"]) == 64
            prior_views = {route: request("GET", route) for route in ("/depth", "/svg")}
            assert b"depth-buffer probe" in prior_views["/depth"][1]
            assert b"Geometry picking is disabled" in prior_views["/svg"][1]
            hold_stage.set()
            assert request("POST", "/run", headers)[0] == 202
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and not (
                active and (active[0][1] / "active").is_file()
            ):
                assert state()["status"] == "running"
                time.sleep(0.02)
            assert len(active) == 1
            child, stage = active[0]
            assert (stage / "active").is_file() and (stage / "candidate.blend").is_file()
            assert child.poll() is None
            assert request("POST", "/cancel/1", headers)[0] == 409
            assert request("POST", "/cancel/2", headers)[0] == 202
            cancelled = wait("cancelled")
            assert cancelled["candidate"] == completed["candidate"]
            assert child.poll() == -signal.SIGKILL
            assert not stage.parents[1].exists()
            assert prior_views == {route: request("GET", route) for route in prior_views}
        finally:
            shell.shutdown()
            thread.join(timeout=5)
            stager.close()


def test_app_worker_failure_stops_without_candidate(monkeypatch):
    monkeypatch.syspath_prepend(str(VERIFIER.parent))
    from app import Stager
    from offline_worker import Blocked

    def blocked(*args, **kwargs):
        raise Blocked("known synthetic failure")

    stager = Stager(blocked)
    try:
        assert stager.start()
        stager.thread.join(timeout=5)
        assert stager.state()["status"] == "blocked"
        assert stager.state()["candidate"] is None
        assert stager.view("/depth") is None
    finally:
        stager.close()
    assert not stager.start()


def test_unconfirmed_worker_reap_latches_failure_and_preserves_preview(monkeypatch):
    monkeypatch.syspath_prepend(str(VERIFIER.parent))
    import offline_worker
    from app import Stager

    active = threading.Event()
    fixture_runs = []
    signals = []
    waits = []

    class Unreaped:
        pid = 123  # Only a sentinel; the test replaces killpg.
        stdout = StringIO()

        def poll(self):
            return None

        def wait(self, timeout):
            waits.append(timeout)
            raise subprocess.TimeoutExpired("synthetic worker", timeout)

    child = Unreaped()
    monkeypatch.setattr(offline_worker.subprocess, "Popen", lambda *args, **kwargs: child)
    monkeypatch.setattr(offline_worker.os, "killpg", lambda *args: signals.append(args))

    def fixture(work, grid, output, check, progress, *, probe_storage):
        fixture_runs.append(grid)
        if len(fixture_runs) == 1:
            output.mkdir()
            (output / "compare.html").write_bytes(b"prior SVG")
            (output / "depth.html").write_bytes(b"prior depth")
            return {"artifact_sha256": {"candidate.blend": "a" * 64}}
        worker = offline_worker.OfflineWorker.__new__(offline_worker.OfflineWorker)
        worker.inputs = worker.stage = work
        worker.check_cancelled = check
        worker.env = {}
        with worker.launch([]):
            active.set()
            assert stager.stop.wait(timeout=5)
            check()

    stager = Stager(fixture)
    try:
        assert stager.start()
        stager.thread.join(timeout=5)
        assert stager.state()["status"] == "staged"
        before = stager.state()["candidate"]
        assert stager.start() and active.wait(5)
        assert stager.cancel("2")
        stager.thread.join(timeout=5)
        state = stager.state()
        assert state["status"] == "cleanup_failed"
        assert state["candidate"] == before == "a" * 64
        assert stager.view("/depth") == b"prior depth"
        assert signals == [(child.pid, signal.SIGKILL)]
        assert waits == [5]
        assert child.stdout.closed
        assert not stager.start()
    finally:
        assert not stager.close()
    assert not stager.close()


def test_app_shutdown_deadline_latches_failure_even_on_late_completion(monkeypatch):
    monkeypatch.syspath_prepend(str(VERIFIER.parent))
    from app import Stager

    active, release = threading.Event(), threading.Event()

    def fixture(work, grid, output, check, progress, *, probe_storage):
        active.set()
        release.wait(timeout=5)
        check()

    stager = Stager(fixture)
    try:
        assert stager.start() and active.wait(5)
        assert not stager.close(timeout=0.01)
        assert stager.state()["status"] == "cleanup_failed"
        assert not stager.start()
    finally:
        release.set()
        assert not stager.close()
    assert stager.state()["status"] == "cleanup_failed"
    assert stager.state()["candidate"] is None


@needs_blender
def test_app_repeated_stop_waits_for_active_blender_reap(tmp_path):
    # Pause only this test's fixed Blender staging operation and its bounded cleanup.
    harness = """
import sys
import time
from contextlib import contextmanager
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import app
from offline_worker import OfflineWorker

markers = Path(sys.argv[2])
launch = OfflineWorker.launch
hold_worker = ('import os,time; from pathlib import Path; '
               'Path("active").write_text(str(os.getpid())); time.sleep(8)')

@contextmanager
def delayed_cleanup(worker, args):
    if "--" not in args or args[args.index("--") + 1] != "stage":
        with launch(worker, args) as child:
            yield child
        return
    boundary = args.index("--")
    args = args[:boundary] + ["--python-expr", hold_worker] + args[boundary:]
    child = None
    try:
        with launch(worker, args) as child:
            try:
                yield child
            finally:
                assert child.poll() is None
                (markers / "cleanup-started").touch()
                deadline = time.monotonic() + 2
                while not (markers / "release-cleanup").exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
    finally:
        if child is not None:
            (markers / "return-code").write_text(str(child.returncode))

OfflineWorker.launch = delayed_cleanup
sys.argv = ["app.py"]
raise SystemExit(app.main())
"""
    process = subprocess.Popen(
        [sys.executable, "-I", "-c", harness, str(VERIFIER.parent), str(tmp_path)],
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "TMPDIR": str(tmp_path)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=15), "App did not become ready"
            address = process.stdout.readline().strip().removeprefix("http://").rstrip("/")
        connection = HTTPConnection(address, timeout=3)
        try:
            connection.request(
                "POST",
                "/run",
                headers={"Origin": f"http://{address}", "X-M0-Action": "fixed-fixture"},
            )
            assert connection.getresponse().status == 202
        finally:
            connection.close()
        deadline = time.monotonic() + 15
        active = None
        while process.poll() is None and time.monotonic() < deadline:
            active = next(tmp_path.glob("terrain-m0-app-*/work/stage/active"), None)
            if active and active.read_text().isdecimal():
                break
            time.sleep(0.02)
        assert active and (active.parent / "candidate.blend").is_file()
        os.kill(int(active.read_text()), 0)
        process.send_signal(signal.SIGTERM)
        deadline = time.monotonic() + 3
        while not (tmp_path / "cleanup-started").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert (tmp_path / "cleanup-started").exists()
        process.send_signal(signal.SIGINT)
        process.send_signal(signal.SIGTERM)
        (tmp_path / "release-cleanup").touch()
        _, stderr = process.communicate(timeout=10)
        assert process.returncode == 0, stderr
        assert (tmp_path / "return-code").read_text() == str(-signal.SIGKILL)
        assert not list(tmp_path.glob("terrain-m0-app-*"))
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        process.stdout.close()
        process.stderr.close()
