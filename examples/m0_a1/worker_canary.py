"""Benign controls: touch only the verifier's synthetic files and loopback listener."""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path


def append(path):
    with path.open("a", encoding="utf-8") as handle:
        handle.write("canary\n")


def connect(port):
    try:
        client = socket.create_connection(("127.0.0.1", port), timeout=2)
    except PermissionError:
        return "denied", "not_attempted"
    with client:
        try:
            client.sendall(b"m0-synthetic")
        except OSError:
            return "allowed", "failed"
    return "allowed", "sent"


def probe(read_only, control, port):
    path = Path.cwd()
    probes = {
        "input_read": (read_only / "fixture.txt").read_bytes,
        "input_write": lambda: append(read_only / "fixture.txt"),
        "stage_write": lambda: append(path / "canary.out"),
        "out_of_scope_read": (control / "unlisted.txt").read_bytes,
        "linked_outside_read": (path / "outside-link").read_bytes,
        "linked_outside_write": lambda: append(path / "outside-link"),
        "canonical_write": lambda: append(control / "canonical.json"),
        "approval_write": lambda: append(control / "approvals.json"),
        "child_exec": lambda: subprocess.run(["/usr/bin/true"], check=True, timeout=2),
    }
    results = {}
    for name, action in probes.items():
        try:
            action()
        except PermissionError:
            results[name] = "denied"
        else:
            results[name] = "allowed"
    results["synthetic_home"] = Path(os.environ["HOME"]) == path / "home"
    results["marker_present"] = "M0_A1_SYNTHETIC_MARKER" in os.environ
    results["loopback_connect"], results["loopback_send"] = connect(port)
    return results


if __name__ == "__main__":
    source, protected, port = sys.argv[sys.argv.index("--") + 1 :]
    print("M0_CANARY " + json.dumps(probe(Path(source), Path(protected), int(port))), flush=True)
