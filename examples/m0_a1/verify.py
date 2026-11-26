"""Generate and check a fixed M0-A1 fixture; only explicit local output is retained."""

import argparse
import copy
import hashlib
import json
import platform
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import trimesh
from foundation import storage_probe, viewer
from offline_worker import POLICY, Blocked, OfflineWorker, require
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ENVELOPE = [[-12, -2, 0], [12, 2, 24]]
# Coordinates are binary-exact before export. Allow four float32 ULP at 24 mm.
EXPORT_TOLERANCE_MM = 4 * 2**-19
PROMPT = (
    "Refine only the selected frame using the attached reference. Keep its placement, "
    "opening and base interface, and leave all other components unchanged.\n"
)


def digest(path):
    require(
        stat.S_ISREG(path.lstat().st_mode) and path.stat().st_size > 0,
        f"missing or non-regular output: {path.name}",
    )
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_reference(path):
    image = Image.new("RGB", (256, 256), "#312623")
    draw = ImageDraw.Draw(image)
    for y in (52, 128, 204):
        draw.polygon([(128, y - 27), (177, y), (128, y + 27), (79, y)], fill="#cba56d")
        draw.polygon([(128, y - 14), (153, y), (128, y + 14), (103, y)], fill="#573b4d")
    image.save(path)


def snapshot(path):
    digest(path)
    rows = json.loads(path.read_text(encoding="utf-8"))
    index = {row["id"]: row for row in rows}
    require(len(index) == len(rows), "duplicate fixture component IDs")
    return index


def validate_scope(baseline, candidate):
    require(baseline.keys() == candidate.keys(), "fixture IDs changed")
    require("frame" in baseline, "fixture target missing")
    for key in baseline.keys() - {"frame"}:
        require(baseline[key] == candidate[key], f"protected component changed: {key}")
    before, after = baseline["frame"], candidate["frame"]
    for prop in ("asset", "transform", "triangles"):
        require(before[prop] == after[prop], f"frame {prop} changed")
    vertices = after["vertices"]
    require(
        all(
            lo <= coord <= hi for v in vertices for coord, lo, hi in zip(v, *ENVELOPE, strict=True)
        ),
        "frame left its allowed envelope",
    )
    expected_interface = {(x, y, 0) for x in (-12, 12) for y in (-2, 2)}
    interface = {tuple(v) for v in vertices if v[2] == 0}
    require(interface == expected_interface, "frame landing interface changed")
    aperture = {(x, y, z) for x in (-8, 8) for y in (-2, 2) for z in (4, 18)}
    require(aperture <= {tuple(v) for v in vertices}, "frame aperture changed")
    expected = [[x, y, 23 if z == 22 else z] for x, y, z in before["vertices"]]
    require(expected != before["vertices"] and vertices == expected, "unexpected frame delta")


def negative_controls(baseline, candidate):
    def changed(component, vertex, axis, delta, expected_error):
        invalid = copy.deepcopy(candidate)
        invalid[component]["vertices"][vertex][axis] += delta
        try:
            validate_scope(baseline, invalid)
        except Blocked as error:
            require(expected_error in str(error), "negative control hit the wrong verdict")
        else:
            raise Blocked("scope checker accepted a deliberate negative control")

    changed("figure.hand-left", 0, 0, 1, "protected component")
    changed("frame", 0, 2, 1, "landing interface")
    changed("frame", 2, 2, 2, "envelope")


def check_export(path, height):
    digest(path)
    mesh = trimesh.load_mesh(path)
    expected = [[-12, -2, 0], [12, 2, height]]
    require(
        len(mesh.faces) == 32
        and mesh.is_watertight
        and mesh.is_winding_consistent
        and abs(mesh.volume - (24 * height - 16 * 14) * 4) < 1e-3
        and all(
            abs(actual - want) <= EXPORT_TOLERANCE_MM
            for corner, expected_corner in zip(mesh.bounds, expected, strict=True)
            for actual, want in zip(corner, expected_corner, strict=True)
        ),
        "real STL export does not match the analytical millimetre fixture",
    )
    return mesh.bounds.tolist()


def verify(root, grid, output, check_cancelled):
    inputs, stage, control = [root / name for name in ("inputs", "stage", "control")]
    for path in (inputs, stage, control):
        path.mkdir(mode=0o700)
    for name in ("blender_fixture.py", "worker_canary.py"):
        shutil.copyfile(HERE / name, inputs / name)
    worker = OfflineWorker(inputs, stage, check_cancelled)
    version = worker.run(["--version"]).splitlines()[0]
    require(version.startswith("Blender "), "Blender version not reported")
    controls = worker.controls(control)
    worker.cancellation()
    canonical = [control / "canonical.json", control / "approvals.json"]
    control_digests = [digest(path) for path in canonical]

    ref, prompt = inputs / "reference.png", inputs / "prompt.txt"
    write_reference(ref)
    prompt.write_text(PROMPT, encoding="utf-8")
    worker.fixture("create", str(grid))
    made = stage / "baseline.blend"
    digest(made)
    accepted = inputs / made.name
    made.replace(accepted)
    worker.fixture("inspect", "baseline", project=accepted)
    a, stl_a, scope_path = [
        inputs / name for name in ("baseline.json", "baseline-frame.stl", "scope.json")
    ]
    for path in (a, stl_a):
        (stage / path.name).replace(path)
    baseline = snapshot(a)
    require("frame" in baseline, "fixture target missing")
    bounds = {"baseline": check_export(stl_a, 22)}
    assets = len({obj["asset"] for obj in baseline.values()})
    instances = len(baseline)
    triangles = sum(len(obj["triangles"]) for obj in baseline.values())
    require(
        (assets, instances, triangles) == (5, 5 + grid**2, 80 + 12 * grid**2),
        "unexpected representative scene counts",
    )
    scope = {
        "unit": "mm",
        "target": "frame",
        "allowed_bounds_mm": ENVELOPE,
        "export_tolerance_mm": EXPORT_TOLERANCE_MM,
        "protected_ids": sorted(baseline.keys() - {"frame"}),
        "interface": "Frame lands at Z=0; preserve its base corners and fixed aperture",
    }
    scope_path.write_text(json.dumps(scope, indent=2) + "\n", encoding="utf-8")
    sealed = (accepted, a, stl_a, scope_path)
    sealed_digests = tuple(digest(path) for path in sealed)

    ran = worker.fixture("stage", str(inputs), project=accepted)
    require("M0_BASELINE_REWRITE_DENIED" in ran.splitlines(), "sealed rewrite control missing")
    candidate = stage / "candidate.blend"
    digest(candidate)
    worker.fixture("inspect", "candidate", project=candidate)
    require(tuple(digest(path) for path in sealed) == sealed_digests, "sealed baseline changed")
    require([digest(path) for path in canonical] == control_digests, "canonical state changed")
    b, stl_b = [stage / name for name in ("candidate.json", "candidate-frame.stl")]
    revised = snapshot(b)
    validate_scope(baseline, revised)
    negative_controls(baseline, revised)
    bounds["candidate"] = check_export(stl_b, 23)
    view = stage / "compare.html"
    viewer(view, baseline, revised)
    files = [*sealed, candidate, ref, prompt, b, stl_b, view]
    manifest = {
        "fixture": "m0-a1-frame-v1",
        "provenance": "Original generated fixture geometry, reference and prompt; no asset inputs",
        **scope,
        "profile": {"grid": grid, "assets": assets, "instances": instances, "triangles": triangles},
        "toolchain": {"blender": version, "macos": platform.mac_ver()[0]},
        "policy_sha256": hashlib.sha256(POLICY.encode()).hexdigest(),
        "artifact_sha256": {path.name: digest(path) for path in files},
        "stl_bounds_mm": bounds,
        "offline_controls": controls,
        "sealed_baseline_rewrite_denied": True,
        "cancelled_and_reaped": True,
        "storage_probe": storage_probe(control, sealed_digests[0]),
    }
    check_cancelled()
    if output is not None:
        with tempfile.TemporaryDirectory(prefix=".m0-evidence-", dir=output.parent) as path:
            staged = Path(path) / "result"
            staged.mkdir(mode=0o700)
            for artifact in files:
                check_cancelled()
                shutil.copyfile(artifact, staged / artifact.name)
            (staged / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
            )
            require(
                not output.exists() and not output.is_symlink(), "output directory already exists"
            )
            check_cancelled()
            staged.rename(output)
    print(f"PASS {version}; allowed fixture reads and candidate writes; eight blocked operations")
    print("PASS Blender cancelled and reaped; accepted/canonical/approval bytes unchanged")
    print("PASS real STL in millimetres, protected geometry, and three rejected scope controls")
    print(f"PASS {assets} assets, {instances} instances, {triangles} triangles; storage probes")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grid", type=int, choices=range(1, 17), default=1)
    parser.add_argument("--output", type=Path, help="new directory for cleared fixture evidence")
    args = parser.parse_args()
    cancelled = False

    def request_stop(signum, frame):
        # Defer unwinding until a checkpoint so a just-launched child is owned by launch().
        nonlocal cancelled
        cancelled = True

    def check_cancelled():
        require(not cancelled, "supervisor cancelled by SIGTERM")

    previous = signal.signal(signal.SIGTERM, request_stop)
    try:
        require(
            not args.output or not (args.output.exists() or args.output.is_symlink()),
            "output directory already exists",
        )
        with tempfile.TemporaryDirectory(prefix="terrain-m0-a1-") as path:
            verify(Path(path).resolve(), args.grid, args.output, check_cancelled)
    except (Blocked, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
