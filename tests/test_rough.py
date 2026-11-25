import copy
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import trimesh
from PIL import Image
from shapely.geometry import LineString

from terrain.cli import main
from terrain.layout import verify_revision
from terrain.library import index_library, read_json
from terrain.rough import evidence, projected_mesh
from terrain.scene import add_placement, assemble_scene, init_scene, resolve_placements
from terrain.workshop import (
    accept_rough,
    approve_layout,
    checkpoint,
    init_workshop,
    sample_review_status,
    save_layout,
    workshop_status,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/workshop-2d-plan.json"


@pytest.fixture
def workshop(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    trimesh.creation.box(extents=[10, 10, 10]).export(models / "box.stl")
    catalog = tmp_path / "catalog.json"
    index_library(models, catalog)
    path = tmp_path / "workshop"
    init_workshop(path, catalog, "Workshop", "An altar")
    plan = read_json(EXAMPLE)
    for option in plan["options"]:
        for feature in option["features"]:
            if feature["kind"] in ("height", "stairs"):
                feature["height_mm"] = 10
    ref = save_layout(path, plan, 0)["revision"]
    approve_layout(path, 1, ref["sha256"], "I approve 2D revision 1 option direct for 3D")
    for pid, pos in {
        "cover": [140, 160, 0],
        "altar": [255, 110, 0],
        "dais": [230, 190, 0],
        "steps": [190, 190, 0],
    }.items():
        add_placement(path / "scene.json", "box.stl", pid, pos)
    scene = read_json(path / "scene.json")
    scene["rough"] = {
        "bindings": {name: name for name in ("cover", "altar", "dais", "steps")},
        "tolerance_mm": 1,
        "clearance_height_mm": 30,
        "gaps": [],
        "sourcing": [],
        "proxies": ["cover"],
        "physical_unknowns": ["Stair fit unverified"],
        "occupied_bases": [{"at": [100, 110], "diameter_mm": 25}],
    }
    (path / "scene.json").write_text(json.dumps(scene))
    monkeypatch.setattr(
        "terrain.scene.render_source",
        lambda source, destination, *a, **k: Image.new("RGB", (40, 30), "#999999").save(
            destination
        ),
    )
    return path, plan, models


def test_checkpoint_exact_acceptance_and_invalidation(workshop, tmp_path):
    path, _, models = workshop
    with pytest.raises(ValueError, match="acceptance"):
        sample_review_status(path)
    saved = checkpoint(path, tmp_path / "out", "Rough", "Place all parts")
    status = workshop_status(path)
    ref = status["revisions"]["scene"]
    snapshot = read_json(saved["snapshot"])
    play = snapshot["iteration"]["rough_evidence"]
    assert play["routes"][0]["status"] == "clear"
    assert play["routes"][0]["occupied_base_intersections"] == [0]
    assert play["interaction_clearances"][0]["nearest_projected_obstacle_mm"] == 30
    assert play["interaction_clearances"][0]["remaining_after_base_radius_mm"] == 14
    assert "not a 3D sightline verdict" in play["cover_reveal_projections"][0]["method"]
    assert play["stock"][0]["printed"] is None
    assert play["stock"][0]["shortfall"] is None
    assert play["stock"][0]["required"] == 3
    assert play["proxy_placements"] == ["cover"]
    with pytest.raises(ValueError):
        accept_rough(path, ref["number"], ref["sha256"], "yes")
    with pytest.raises(ValueError):
        accept_rough(path, 1, "wrong", "I accept rough revision 1 for sample review")
    accept_rough(path, 1, ref["sha256"], "I accept rough revision 1 for sample review")
    assert sample_review_status(path)["sample_review_ready"]
    working = read_json(path / "scene.json")
    working["placements"][0]["position_mm"][0] += 1
    (path / "scene.json").write_text(json.dumps(working))
    with pytest.raises(ValueError, match="changed"):
        sample_review_status(path)
    working["placements"][0]["position_mm"][0] -= 1
    (path / "scene.json").write_text(json.dumps(working))
    trimesh.creation.box(extents=[11, 10, 10]).export(models / "box.stl")
    with pytest.raises(ValueError, match="changed"):
        sample_review_status(path)


def test_sample_and_finished_gates(workshop, tmp_path, monkeypatch):
    from terrain.quality import build_sample, decide_finished, decide_sample

    path, _, models = workshop
    monkeypatch.setattr(
        "terrain.visual.render_seated",
        lambda source, destination, *a, **k: Image.new("RGB", (40, 30), "#777777").save(
            destination
        ),
    )
    arguments = (
        path,
        tmp_path / "sample-output",
        "altar",
        "dais",
        "steps",
        "Agreed reference",
        "rough intent",
        "surface detail",
    )
    with pytest.raises(ValueError, match="rough acceptance"):
        build_sample(*arguments)
    checkpoint(path, tmp_path / "out", "Rough", "Place all parts")
    ref = workshop_status(path)["revisions"]["scene"]
    with pytest.raises(ValueError, match="rough acceptance"):
        build_sample(*arguments)
    accept_rough(path, 1, ref["sha256"], "I accept rough revision 1 for sample review")
    with pytest.raises(ValueError, match="sample"):
        add_placement(path / "scene.json", "box.stl", "detail", [400, 400, 0])
    result = build_sample(*arguments)
    sample = result["sample"]
    assert Path(result["review"]).is_file()
    assert workshop_status(path)["quality_status"]["rough_acceptance"] == "accepted"
    decide_sample(path, sample["number"], sample["sha256"], "rejected", "No", "Too plain")
    assert workshop_status(path)["quality_status"]["sample_verdict"] == "rejected"
    assert workshop_status(path)["quality_status"]["rough_acceptance"] == "accepted"
    with pytest.raises(ValueError, match="sample"):
        add_placement(path / "scene.json", "box.stl", "detail", [400, 400, 0])
    with pytest.raises(ValueError, match="confirmation"):
        decide_sample(path, sample["number"], sample["sha256"], "approved", "maybe")
    decide_sample(path, sample["number"], sample["sha256"], "inconclusive", "Not sure", "Texture")
    assert workshop_status(path)["quality_status"]["sample_verdict"] == "inconclusive"
    decide_sample(
        path,
        sample["number"],
        sample["sha256"],
        "approved",
        "I would print the board if it matched sample 1",
    )
    assert not workshop_status(path)["quality_status"]["handoff"]
    checkpoint(path, tmp_path / "out", "Finished", "Complete detailing")
    final = workshop_status(path)["revisions"]["scene"]
    with pytest.raises(ValueError, match="play approval"):
        decide_finished(path, 2, final["sha256"], "visual", "I approve finished board revision 2")
    decide_finished(path, 2, final["sha256"], "play", "I approve finished play revision 2")
    decide_finished(path, 2, final["sha256"], "visual", "I approve finished board revision 2")
    assert workshop_status(path)["quality_status"]["handoff"]
    fresh = subprocess.run(
        [str(Path(sys.executable).parent / "terrain"), "workshop", "status", str(path)],
        check=True, capture_output=True, text=True,
    )
    fresh_status = json.loads(fresh.stdout)["quality_status"]
    assert fresh_status["rough_acceptance"] == "accepted (historical)"
    assert fresh_status["sample_verdict"] == "approved"
    assert fresh_status["finished_visual"] == "approved"
    final_path = path / "revisions" / "0002.json"
    snapshot_bytes = final_path.read_bytes()
    final_path.write_bytes(snapshot_bytes + b" ")
    with pytest.raises(ValueError, match="snapshot"):
        workshop_status(path)
    final_path.write_bytes(snapshot_bytes)
    original = (path / "scene.json").read_bytes()
    working = read_json(path / "scene.json")
    working["brief"] = "Changed finished snapshot"
    (path / "scene.json").write_text(json.dumps(working))
    assert not workshop_status(path)["quality_status"]["handoff"]
    (path / "scene.json").write_bytes(original)
    trimesh.creation.box(extents=[11, 10, 10]).export(models / "box.stl")
    assert not workshop_status(path)["quality_status"]["handoff"]


def test_proxy_and_changed_sample_inputs_block_detail(workshop, tmp_path, monkeypatch):
    from terrain.quality import build_sample, decide_sample

    path, _, _ = workshop
    monkeypatch.setattr(
        "terrain.visual.render_seated",
        lambda source, destination, *a, **k: Image.new("RGB", (40, 30), "#777777").save(
            destination
        ),
    )
    checkpoint(path, tmp_path / "out", "Rough", "Place all parts")
    ref = workshop_status(path)["revisions"]["scene"]
    accept_rough(path, 1, ref["sha256"], "I accept rough revision 1 for sample review")
    sample = build_sample(path, tmp_path / "sample", "cover", "altar", "steps",
                          "Reference", "Proxy", "Focal")["sample"]
    with pytest.raises(ValueError, match="proxy focal"):
        decide_sample(path, 1, sample["sha256"], "approved",
                      "I would print the board if it matched sample 1")
    scene = read_json(path / "scene.json")
    scene["rough"]["clearance_height_mm"] += 1
    (path / "scene.json").write_text(json.dumps(scene))
    with pytest.raises(ValueError, match="Play inputs changed"):
        decide_sample(path, 1, sample["sha256"], "rejected", "No", "Proxy")
    assert workshop_status(path)["quality_status"]["rough_acceptance"] == "stale"


def test_failed_sample_render_preserves_rough_acceptance(workshop, tmp_path, monkeypatch):
    from terrain.quality import build_sample

    path, _, _ = workshop
    checkpoint(path, tmp_path / "out", "Rough", "Place all parts")
    ref = workshop_status(path)["revisions"]["scene"]
    accept_rough(path, 1, ref["sha256"], "I accept rough revision 1 for sample review")

    def fail(*args, **kwargs):
        raise ValueError("render failed")

    monkeypatch.setattr("terrain.visual.render_seated", fail)
    with pytest.raises(ValueError, match="render failed"):
        build_sample(path, tmp_path / "sample", "altar", "dais", "steps",
                     "Reference", "Intent", "Missing")
    assert workshop_status(path)["quality_status"]["rough_acceptance"] == "accepted"
    assert sample_review_status(path)["sample_review_ready"]


def test_material_change_requires_new_layout(workshop, tmp_path):
    path, plan, _ = workshop
    scene = read_json(path / "scene.json")
    scene["placements"][0]["position_mm"] = [100, 110, 0]
    (path / "scene.json").write_text(json.dumps(scene))
    current, catalog, resolved = resolve_placements(path / "scene.json")
    state = workshop_status(path)
    play = evidence(current, catalog, resolved, verify_revision(path, state["revisions"]["layout"]))
    assert play["routes"][0]["status"] == "blocked"
    assert "cover" in play["routes"][0]["blocking_placements"]
    assert (
        main(["scene", "build", str(path / "scene.json"), "--output-dir", str(tmp_path / "out")])
        == 1
    )
    with pytest.raises(ValueError, match="approved 2D"):
        checkpoint(path, tmp_path / "out", "Changed", "Moved cover into route")
    assert not (tmp_path / "out").exists()
    state = workshop_status(path)
    assert state["stage"] == "layout_review"
    assert state["requires_new_layout"]
    with pytest.raises(ValueError, match="new 2D"):
        approve_layout(
            path,
            1,
            state["revisions"]["layout"]["sha256"],
            "I approve 2D revision 1 option direct for 3D",
        )
    plan["pending_decision"] = "Review the new route"
    revised = save_layout(path, copy.deepcopy(plan), 1)
    assert revised["revision"]["number"] == 2


def test_mesh_projection_distinguishes_aabb_warning(tmp_path):
    mesh = trimesh.creation.box(extents=[100, 2, 10])
    rotation = trimesh.transformations.rotation_matrix(np.pi / 4, [0, 0, 1])
    shifted = rotation.copy()
    shifted[:3, 3] = [-4, 4, 0]
    first = trimesh.transform_points(mesh.vertices, rotation)
    second = trimesh.transform_points(mesh.vertices, shifted)
    assert (
        np.minimum(first.max(axis=0), second.max(axis=0))
        - np.maximum(first.min(axis=0), second.min(axis=0))
        > 0
    ).all()
    first_shape = projected_mesh(mesh, rotation)
    second_shape = projected_mesh(mesh, shifted)
    assert not first_shape.intersects(second_shape)
    route = LineString([[-20, -20], [20, 20]]).buffer(1)
    assert route.intersects(first_shape)
    assert not route.intersects(second_shape)
    models = tmp_path / "models"
    models.mkdir()
    mesh.export(models / "slat.stl")
    catalog = tmp_path / "catalog.json"
    index_library(models, catalog)
    scene = tmp_path / "standalone.json"
    init_scene(scene, catalog, "Slats", "Two separated diagonals")
    add_placement(scene, "slat.stl", "first", [0, 0, 0], [0, 0, 45])
    add_placement(scene, "slat.stl", "second", [-4, 4, 0], [0, 0, 45])
    report = assemble_scene(scene, tmp_path / "assembled")
    assert read_json(report["report"])["aabb_overlaps"] == [["first", "second"]]


def test_zero_stock_candidate_and_proxy_remain_distinct(workshop, tmp_path):
    path, _, _ = workshop
    catalog_path = tmp_path / "catalog.json"
    catalog = read_json(catalog_path)
    catalog["assets"][0]["printed"] = 0
    catalog_path.write_text(json.dumps(catalog))
    working = read_json(path / "scene.json")
    working["rough"]["sourcing"] = [
        {
            "vendor_link": "https://example.com/item",
            "price_date": "Unknown at date of review",
            "contents": "Unknown",
            "size_interface_evidence": "Unverified",
            "license": "Unknown",
            "unknowns": "Actual dimensions and availability",
            "recommendation": "Inspect before purchase",
            "fallback": "Use a locally owned piece",
        }
    ]
    (path / "scene.json").write_text(json.dumps(working))
    saved = checkpoint(path, tmp_path / "out", "Rough", "Review inventory")
    play = read_json(saved["snapshot"])["iteration"]["rough_evidence"]
    assert play["stock"][0]["printed"] == 0
    assert play["stock"][0]["shortfall"] == 3
    assert play["sourcing_candidates_unavailable"][0]["contents"] == "Unknown"
    assert play["proxy_placements"] == ["cover"]


def test_failed_render_preserves_last_snapshot_and_decision(workshop, tmp_path, monkeypatch):
    path, _, _ = workshop
    first = checkpoint(path, tmp_path / "out", "First", "Initial")
    before = workshop_status(path)

    def fail(*args, **kwargs):
        raise ValueError("render failed")

    monkeypatch.setattr("terrain.scene.render_source", fail)
    with pytest.raises(ValueError, match="render failed"):
        checkpoint(path, tmp_path / "out", "Second", "Refine")
    assert workshop_status(path) == before
    assert first["snapshot"].exists()
    assert not (path / "revisions/0002.json").exists()
