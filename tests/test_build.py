import hashlib
import json

import pytest

from terrain.build import BuildError, generate_model
from terrain.catalog import named_spec, part_contract
from terrain.cli import main
from terrain.mesh import inspect_mesh


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_generate_model_exports_valid_stl_3mf_preview_and_manifest(tmp_path):
    spec = named_spec("e_floor", "mork_borg", 42)

    result = generate_model(spec, output_dir=tmp_path, preview=True)

    assert result["spec"] == {"part": "e_floor", "genre": "mork_borg", "seed": 42}
    assert result["physical_validation"] == "pending"
    assert {artifact.suffix for artifact in result["artifacts"]} == {".stl", ".3mf"}
    assert result["preview"].is_file()
    manifest = json.loads(result["manifest"].read_text())
    assert manifest["license"] == "CC BY-NC 4.0"
    assert manifest["physical_validation"] == "pending"
    assert len(manifest["source_sha256"]) == 64

    for artifact in result["artifacts"]:
        report = inspect_mesh(artifact, part_contract("e_floor").rules())
        assert report["valid"] is True, report


def test_plain_e_floor_stl_and_3mf_share_serialization_budget(tmp_path):
    result = generate_model(named_spec("e_floor", "plain", 42), output_dir=tmp_path)

    for artifact in result["artifacts"]:
        report = inspect_mesh(artifact, part_contract("e_floor").rules())
        assert report["valid"] is True, report


def test_stl_generation_is_byte_deterministic(tmp_path):
    spec = named_spec("e_floor", "mork_borg", 7)
    first = generate_model(spec, output_dir=tmp_path / "first")
    second = generate_model(spec, output_dir=tmp_path / "second")

    first_stl = next(path for path in first["artifacts"] if path.suffix == ".stl")
    second_stl = next(path for path in second["artifacts"] if path.suffix == ".stl")
    assert file_hash(first_stl) == file_hash(second_stl)


def test_generate_rejects_unknown_source_failures(tmp_path):
    spec = named_spec("assembly", "plain", 42)

    with pytest.raises(BuildError):
        generate_model(spec, output_dir=tmp_path, openscad="/missing/openscad")


def test_validate_cli_returns_failure_for_invalid_artifact(tmp_path, capsys):
    artifact = tmp_path / "empty.stl"
    artifact.write_text("solid empty\nendsolid empty\n")

    assert main(["validate", str(artifact)]) == 1
    assert '"valid": false' in capsys.readouterr().out


def test_generate_cli_requires_part_or_all(capsys):
    assert main(["generate"]) == 2
    assert "requires a part or --all" in capsys.readouterr().err
