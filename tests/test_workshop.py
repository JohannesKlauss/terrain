import json
from pathlib import Path

import numpy as np
import pytest
import trimesh
from PIL import Image

from terrain.build import BuildError
from terrain.cli import main
from terrain.library import index_library
from terrain.scene import add_placement
from terrain.workshop import checkpoint, init_workshop, review_workshop


@pytest.fixture
def workshop(tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    mesh = trimesh.creation.box(extents=[20, 10, 6])
    mesh.apply_translation([80, -40, 3])
    mesh.export(models / "wall.stl")
    catalog = tmp_path / "catalog.json"
    index_library(models, catalog)
    path = tmp_path / "encounter"
    init_workshop(path, catalog, "The pressure chapel", "A villain's ritual laboratory")
    add_placement(path / "scene.json", "wall.stl", "west-wall", [0, 0, 0])
    return path, tmp_path / "review", models, catalog


@pytest.fixture
def quick_previews(monkeypatch):
    def render(source, destination, view, *args, **kwargs):
        Image.new("RGB", (40, 30), "#345678").save(destination)

    monkeypatch.setattr("terrain.scene.render_source", render)


def test_checkpoints_preserve_feedback_brief_layout_and_print_quantities(workshop, quick_previews):
    path, output, models, _ = workshop
    before = (models / "wall.stl").read_bytes()
    first = checkpoint(path, output, "Approach", "Establish the ritual focus")
    frozen = first["snapshot"].read_bytes()
    add_placement(path / "scene.json", "wall.stl", "cover", [50, 0, 0], role="cover")
    (path / "design.md").write_text("Confirmed: villain needs a retreat route.")
    second = checkpoint(
        path, output, "Flanking route", "Add cover", feedback="The approach feels too exposed"
    )
    assert first["snapshot"].read_bytes() == frozen
    snapshot = json.loads(second["snapshot"].read_text())
    assert snapshot["iteration"]["feedback"] == "The approach feels too exposed"
    assert "retreat route" in snapshot["iteration"]["design_notes"]
    assert len(snapshot["placements"]) == 2
    assert snapshot["encounter"]["villains"] == []
    report = json.loads((output / "0002/report.json").read_text())
    assert report["print_list"][0]["required"] == 2
    assert report["print_list"][0]["already_printed"] is None
    assert report["print_list"][0]["to_print"] is None
    assert all(Path(p).exists() for p in report["previews"])
    assert report["physical_validation"] == "pending"
    assert (models / "wall.stl").read_bytes() == before
    assert "0001/review.html" in (output / "index.html").read_text()
    assert "0002/review.html" in (output / "index.html").read_text()
    assert len(list((output / "0002").glob("*.png"))) == 4
    assert "encounter" in report


def test_failed_preview_creates_no_revision_and_retry_keeps_number_one(workshop, monkeypatch):
    path, output, _, _ = workshop

    def fail(*args, **kwargs):
        raise BuildError("preview failed")

    monkeypatch.setattr("terrain.scene.render_source", fail)
    with pytest.raises(BuildError, match="preview failed"):
        checkpoint(path, output, "First", "Test")
    assert not list((path / "revisions").glob("*.json"))
    assert not (output / "0001").exists()
    monkeypatch.setattr(
        "terrain.scene.render_source",
        lambda source, destination, *a, **k: Image.new("RGB", (40, 30)).save(destination),
    )
    result = checkpoint(path, output, "Retry", "Test")
    assert result["revision"] == 1


def test_review_rebuilds_saved_revisions_without_using_current_working_draft(
    workshop, quick_previews, tmp_path
):
    path, output, _, _ = workshop
    checkpoint(path, output, "First", "Test")
    (path / "scene.json").write_text("{}")
    rebuilt = review_workshop(path, tmp_path / "rebuilt")
    assert rebuilt["revisions"] == 1
    assert (tmp_path / "rebuilt/0001/review.html").is_file()
    assert review_workshop(path, output)["revisions"] == 1


def test_changed_library_source_stops_checkpoint_and_review(workshop, quick_previews):
    path, output, models, catalog = workshop
    checkpoint(path, output, "First", "Test")
    trimesh.creation.box().export(models / "wall.stl")
    index_library(models, catalog)
    with pytest.raises(ValueError, match="changed"):
        checkpoint(path, output, "Second", "Test")
    with pytest.raises(ValueError, match="changed"):
        review_workshop(path, output)
    assert not (path / "revisions/0002.json").exists()


def test_new_checkpoint_rebuilds_earlier_iterations_in_a_new_output_directory(
    workshop, quick_previews, tmp_path
):
    path, output, _, _ = workshop
    checkpoint(path, output, "First", "Test")
    new_output = tmp_path / "new-review"
    checkpoint(path, new_output, "Second", "Refine layout")
    assert (new_output / "0001/review.html").is_file()
    assert (new_output / "0002/review.html").is_file()


def test_init_and_empty_review_via_cli(workshop, tmp_path, capsys):
    _, _, _, catalog = workshop
    path = tmp_path / "new-encounter"
    assert (
        main(
            [
                "workshop",
                "init",
                str(path),
                "--catalog",
                str(catalog),
                "--name",
                "Sanctum",
                "--brief",
                "The last stand",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["workshop"] == str(path)
    original = (path / "scene.json").read_bytes()
    assert (
        main(
            [
                "workshop",
                "init",
                str(path),
                "--catalog",
                str(catalog),
                "--name",
                "Other",
                "--brief",
                "No",
            ]
        )
        == 1
    )
    assert (path / "scene.json").read_bytes() == original
    assert main(["workshop", "review", str(path)]) == 1
    assert "no saved iterations" in capsys.readouterr().err


def test_rebuilt_history_preserves_stock_recorded_at_each_checkpoint(
    workshop, quick_previews, tmp_path
):
    path, output, _, catalog = workshop
    checkpoint(path, output, "First", "Stock is unknown")
    data = json.loads(catalog.read_text())
    data["assets"][0]["printed"] = 2
    catalog.write_text(json.dumps(data))
    checkpoint(path, output, "Second", "Printed stock confirmed")
    rebuilt = tmp_path / "rebuilt"
    review_workshop(path, rebuilt)
    first = json.loads((rebuilt / "0001/report.json").read_text())
    second = json.loads((rebuilt / "0002/report.json").read_text())
    assert first["print_list"][0]["already_printed"] is None
    assert second["print_list"][0]["already_printed"] == 2
    assert second["print_list"][0]["to_print"] == 0


def test_workshop_refuses_to_overwrite_inputs_or_unowned_output(workshop, tmp_path):
    path, output, models, _ = workshop
    for protected in (path, path / "previews", models, models / "preview", tmp_path):
        with pytest.raises(ValueError, match="output"):
            checkpoint(path, protected, "First", "Test")
    output.mkdir()
    (output / "notes.txt").write_text("user work")
    with pytest.raises(ValueError, match="output"):
        checkpoint(path, output, "First", "Test")
    assert (output / "notes.txt").read_text() == "user work"


def test_local_viewer_embeds_intact_geometry_instances_and_escaped_text(workshop, quick_previews):
    import base64
    import re

    path, output, models, _ = workshop
    add_placement(path / "scene.json", "wall.stl", "east-wall", [50, 0, 0], [0, 0, 90])
    result = checkpoint(path, output, "</script><h1>unsafe</h1>", "Test")
    html = result["review"].read_text()
    payload = json.loads(
        re.search(r'<script type="application/json" id="scene-data">(.*?)</script>', html, re.S)[1]
    )
    assert len(payload["geometry"]) == 1
    assert len(payload["instances"]) == 2
    geometry = payload["geometry"][0]
    vertices = np.frombuffer(base64.b64decode(geometry["vertices"]), dtype="<f4").reshape(-1, 3)
    faces = np.frombuffer(base64.b64decode(geometry["indices"]), dtype="<u4").reshape(-1, 3)
    source = trimesh.load(models / "wall.stl", process=False)
    assert np.array_equal(vertices, source.vertices)
    assert np.array_equal(faces, source.faces)
    assert "</script><h1>unsafe</h1>" not in html
    matrix = np.array(payload["instances"][1]["matrix"]).reshape(4, 4).T
    transformed = trimesh.transform_points(vertices, matrix)
    assert np.ptp(transformed, axis=0) == pytest.approx([10, 20, 6])
    assert (transformed.min(axis=0) + transformed.max(axis=0)) / 2 == pytest.approx([50, 0, 3])
    assert 'id="print-list"' in html
    assert 'id="feedback"' in html
    assert "https://" not in html  # No CDN, telemetry, font or model request.


def test_workshop_cli_real_multi_angle_review(workshop, capsys):
    path, output, _, _ = workshop
    assert (
        main(
            [
                "workshop",
                "checkpoint",
                str(path),
                "--output-dir",
                str(output),
                "--title",
                "First visual draft",
                "--changes",
                "Establish the approach",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["revision"] == 1
    assert (output / "index.html").is_file()
    for name in ("iso", "reverse", "top", "front"):
        pixels = np.asarray(Image.open(output / "0001" / f"{name}.png"))
        assert pixels.std() > 5
