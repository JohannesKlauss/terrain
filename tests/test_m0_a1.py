import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

import pytest

VERIFIER = Path(__file__).parents[1] / "examples" / "m0_a1" / "verify.py"
BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")


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


@pytest.mark.skipif(
    platform.system() != "Darwin"
    or platform.machine() != "arm64"
    or not BLENDER.is_file()
    or not Path("/usr/bin/sandbox-exec").is_file(),
    reason="M0 offline fixture requires macOS arm64, sandbox-exec and installed Blender",
)
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
            "loopback": "denied",
            "child_exec": "denied",
            "synthetic_home": True,
            "marker_present": False,
        }
        assert manifest["cancelled_and_reaped"]
        base, candidate = [
            {entry["id"]: entry for entry in json.loads((output / f"{variant}.json").read_text())}
            for variant in ("baseline", "candidate")
        ]
        for identity in ("figure.body", "figure.hand-left", "figure.hand-right", "context.plinth"):
            assert identity in manifest["protected_ids"]
            assert base[identity] == candidate[identity]
        assert base["frame"]["vertices"] != candidate["frame"]["vertices"]
    for artifact in ("baseline.json", "candidate.json", "prompt.txt", "reference.png"):
        assert (
            manifests[0]["artifact_sha256"][artifact] == manifests[1]["artifact_sha256"][artifact]
        )
