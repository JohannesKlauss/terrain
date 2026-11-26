import hashlib
import json
import os
import platform
import signal
import socket
import subprocess
import sys
import time
from contextlib import suppress
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
