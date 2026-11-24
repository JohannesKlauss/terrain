import os
import re
import subprocess
from pathlib import Path

import pytest
import trimesh

from terrain.catalog import ModelSpec

ROOT = Path(__file__).parents[1]
MODEL = ROOT / "src" / "terrain.scad"
OFFICIAL = ROOT / "assets" / "openlock" / "official"


def export_model(spec=None, source=MODEL, name=None):
    spec = spec or ModelSpec("e_floor", "plain", 42)
    output_dir = ROOT / "build" / "test-meshes"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{name or f'{spec.part}-{spec.genre}-{spec.seed}'}.stl"
    output.unlink(missing_ok=True)
    command = [
        os.environ.get("OPENSCAD", "openscad"),
        "--backend",
        "Manifold",
        "--export-format",
        "binstl",
        "-o",
        str(output),
        "-D",
        f'part="{spec.part}"',
        "-D",
        f'genre="{spec.genre}"',
        "-D",
        f"seed={spec.seed}",
        str(source),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    diagnostics = result.stdout + result.stderr
    assert result.returncode == 0, diagnostics
    assert not re.search(r"^ERROR:", diagnostics, re.MULTILINE), diagnostics
    assert output.is_file() and output.stat().st_size > 84, diagnostics
    return output, diagnostics


@pytest.fixture
def model_mesh():
    cache = {}

    def load(part="e_floor", genre="plain", seed=42):
        spec = ModelSpec(part, genre, seed)
        if spec not in cache:
            path, _ = export_model(spec)
            cache[spec] = trimesh.load_mesh(path, process=True)
        return cache[spec]

    return load


def assert_single_printable_solid(mesh, expected_extents, tolerance=0.02):
    assert mesh.is_watertight
    assert mesh.is_winding_consistent
    assert mesh.volume > 0
    assert len(mesh.split(only_watertight=False)) == 1
    assert mesh.extents == pytest.approx(expected_extents, abs=tolerance)
