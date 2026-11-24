import json

import numpy as np
import pytest
import trimesh

from terrain.cli import main
from terrain.library import index_library, load_catalog
from terrain.scene import add_placement, assemble_scene, init_scene


@pytest.fixture
def scene_files(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    box = trimesh.creation.box(extents=(20, 10, 6))
    box.apply_translation((80, -40, 3))
    box.export(root / "wall.stl")
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"assets": {"wall.stl": {"printed": 1}}}))
    catalog = tmp_path / "catalog.json"
    index_library(root, catalog, metadata)
    scene = tmp_path / "scene.json"
    init_scene(scene, catalog, "The pressure chapel", "A laboratory inside a ruined shrine")
    return root, catalog, scene


def test_scene_transforms_inventory_and_per_asset_provenance(scene_files, tmp_path):
    root, _, scene = scene_files
    before = (root / "wall.stl").read_bytes()
    add_placement(scene, "wall.stl", "west", (40, 50, 0), (0, 0, 90), "architecture")
    add_placement(scene, "wall.stl", "east", (80, 50, 0), (0, 0, 0), "cover")
    result = assemble_scene(scene, tmp_path / "output")
    report = json.loads(result["report"].read_text())
    assert report["bounds_mm"] == pytest.approx(np.array([[35, 40, 0], [90, 60, 6]]))
    assert report["print_list"][0]["required"] == 2
    assert report["print_list"][0]["already_printed"] == 1
    assert report["print_list"][0]["to_print"] == 1
    assert report["print_list"][0]["license"]["name"] == "unknown"
    assert report["physical_validation"] == "pending"
    assert report["connector_validation"] == "pending"
    assert "license" not in report  # Never relabel a mixed assembly as CC BY-NC.
    assert result["source"].is_file()
    assert "multmatrix" in result["source"].read_text()
    assert not list((tmp_path / "output").glob("*.stl"))
    assert (root / "wall.stl").read_bytes() == before


def test_scene_rejects_changed_sources_even_if_catalog_is_reindexed(scene_files, tmp_path):
    root, catalog, scene = scene_files
    add_placement(scene, "wall.stl", "one", (0, 0, 0))
    trimesh.creation.box().export(root / "wall.stl")
    with pytest.raises(ValueError, match="changed"):
        assemble_scene(scene, tmp_path / "output")
    index_library(root, catalog)
    with pytest.raises(ValueError, match="changed"):
        assemble_scene(scene, tmp_path / "output")


@pytest.mark.parametrize(
    "change",
    [
        {"scale": [2, 2, 2]},
        {"position_mm": [float("nan"), 0, 0]},
        {"rotation_deg": [0, 0]},
        {"anchor": "whatever"},
    ],
)
def test_scene_rejects_scaling_invalid_transforms_and_unknown_anchors(
    scene_files, tmp_path, change
):
    _, _, scene = scene_files
    add_placement(scene, "wall.stl", "one", (0, 0, 0))
    data = json.loads(scene.read_text())
    data["placements"][0].update(change)
    scene.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        assemble_scene(scene, tmp_path / "output")


def test_scene_rejects_duplicate_ids_and_does_not_overwrite_scene(scene_files):
    _, catalog, scene = scene_files
    with pytest.raises(ValueError, match="exists"):
        init_scene(scene, catalog, "Other", "Other")
    add_placement(scene, "wall.stl", "one", (0, 0, 0))
    with pytest.raises(ValueError, match="duplicate"):
        add_placement(scene, "wall.stl", "one", (0, 0, 0))


def test_unknown_inventory_and_overlap_are_not_false_fit_certificates(scene_files, tmp_path):
    _, catalog, scene = scene_files
    data = load_catalog(catalog)
    data["assets"][0]["printed"] = None
    catalog.write_text(json.dumps(data))
    add_placement(scene, "wall.stl", "one", (0, 0, 0))
    add_placement(scene, "wall.stl", "two", (1, 0, 0))
    result = assemble_scene(scene, tmp_path / "output")
    report = json.loads(result["report"].read_text())
    assert report["print_list"][0]["to_print"] is None
    assert len(report["aabb_overlaps"]) == 1
    assert any("not a collision" in warning for warning in report["warnings"])


def test_real_scene_preview_via_cli(scene_files, tmp_path, capsys):
    _, _, scene = scene_files
    add_placement(scene, "wall.stl", "one", (0, 0, 0))
    assert (
        main(
            [
                "scene",
                "build",
                str(scene),
                "--output-dir",
                str(tmp_path / "output"),
                "--preview",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert len(result["previews"]) == 2
    from PIL import Image

    for path in result["previews"]:
        pixels = np.asarray(Image.open(path).convert("RGB"))
        assert pixels.std() > 5


def test_output_directory_cannot_overwrite_a_scene_input(scene_files):
    _, _, scene = scene_files
    add_placement(scene, "wall.stl", "one", (0, 0, 0))
    renamed = scene.with_name("report.json")
    scene.rename(renamed)
    before = renamed.read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        assemble_scene(renamed, renamed.parent)
    assert renamed.read_bytes() == before
