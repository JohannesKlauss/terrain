import hashlib
import json
import re
import subprocess
from pathlib import Path

from terrain.catalog import ModelSpec, mvp_specs, part_contract
from terrain.mesh import inspect_mesh

ROOT = Path(__file__).parents[2]
MODEL = ROOT / "src" / "terrain.scad"


class BuildError(RuntimeError):
    pass


def source_fingerprint():
    paths = [
        *ROOT.glob("src/**/*.scad"),
        *ROOT.glob("src/**/*.py"),
        *ROOT.glob("assets/openlock/official/*.stl"),
        ROOT / "assets" / "openlock" / "provenance.json",
    ]
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def run_openscad(arguments, openscad):
    try:
        result = subprocess.run(
            [str(openscad), *map(str, arguments)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BuildError(f"OpenSCAD execution failed: {error}") from error
    diagnostics = result.stdout + result.stderr
    if result.returncode or re.search(r"^ERROR:", diagnostics, re.MULTILINE):
        raise BuildError(diagnostics.strip() or f"OpenSCAD exited {result.returncode}")
    return diagnostics


def openscad_version(openscad):
    try:
        result = subprocess.run(
            [str(openscad), "--version"], capture_output=True, text=True, timeout=30
        )
    except OSError as error:
        raise BuildError(f"OpenSCAD execution failed: {error}") from error
    if result.returncode:
        raise BuildError(result.stderr.strip() or "unable to determine OpenSCAD version")
    return (result.stdout + result.stderr).strip()


def model_arguments(spec):
    return [
        "-D",
        f'part="{spec.part}"',
        "-D",
        f'genre="{spec.genre}"',
        "-D",
        f"seed={spec.seed}",
        str(MODEL),
    ]


def export_meshes(spec, artifacts, openscad):
    arguments = ["--backend", "Manifold"]
    for artifact in artifacts:
        arguments.extend(["-o", str(artifact)])
    return run_openscad([*arguments, *model_arguments(spec)], openscad)


def render_preview(spec, preview_path, openscad):
    arguments = [
        "--backend",
        "Manifold",
        "--render",
        "--autocenter",
        "--viewall",
        "--projection=o",
        "--imgsize=1200,900",
        "--colorscheme=DeepOcean",
        "-o",
        str(preview_path),
        *model_arguments(spec),
    ]
    return run_openscad(arguments, openscad)


def generate_model(spec: ModelSpec, output_dir=ROOT / "build", openscad="openscad", preview=False):
    destination = Path(output_dir) / spec.genre
    destination.mkdir(parents=True, exist_ok=True)
    stem = f"{spec.part}-{spec.genre}-{spec.seed}"
    artifacts = [destination / f"{stem}.stl", destination / f"{stem}.3mf"]
    diagnostics = export_meshes(spec, artifacts, openscad)
    preview_path = destination / f"{stem}.png" if preview else None
    if preview_path:
        diagnostics += render_preview(spec, preview_path, openscad)

    contract = part_contract(spec.part)
    reports = [inspect_mesh(artifact, contract.rules()) for artifact in artifacts]
    manifest_path = destination / f"{stem}.json"
    result = {
        "spec": {"part": spec.part, "genre": spec.genre, "seed": spec.seed},
        "openscad": openscad_version(openscad),
        "artifacts": artifacts,
        "preview": preview_path,
        "manifest": manifest_path,
        "reports": reports,
        "source_sha256": source_fingerprint(),
        "physical_validation": "pending",
    }
    manifest = {
        **result,
        "license": "CC BY-NC 4.0",
        "attribution": "Printable Scenery - https://www.printablescenery.com/",
        "diagnostics": diagnostics,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str) + "\n")

    failures = [report for report in reports if not report["valid"]]
    if failures:
        raise BuildError(f"mesh validation failed; see {manifest_path}")
    return result


def generate_mvp(output_dir=ROOT / "build", openscad="openscad", preview=False, seed=42):
    return [generate_model(spec, output_dir, openscad, preview) for spec in mvp_specs(seed)]
