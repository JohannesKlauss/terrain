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
        check=True,
        capture_output=True,
        text=True,
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
    sample = build_sample(
        path, tmp_path / "sample", "cover", "altar", "steps", "Reference", "Proxy", "Focal"
    )["sample"]
    with pytest.raises(ValueError, match="proxy focal"):
        decide_sample(
            path, 1, sample["sha256"], "approved", "I would print the board if it matched sample 1"
        )
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
        build_sample(
            path, tmp_path / "sample", "altar", "dais", "steps", "Reference", "Intent", "Missing"
        )
    assert workshop_status(path)["quality_status"]["rough_acceptance"] == "accepted"
    assert sample_review_status(path)["sample_review_ready"]


def test_handoff_requires_gates_and_rechecks_evidence(workshop, tmp_path, monkeypatch):
    from terrain.handoff import CHECKS, handoff, verify_handoff
    from terrain.library import sha256
    from terrain.quality import build_sample, decide_finished, decide_sample

    path, _, models = workshop
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: pytest.fail("Unexpected external process")
    )
    output = tmp_path / "pack"
    before = (path / "workshop-state.json").read_bytes()
    with monkeypatch.context() as guard:
        guard.setattr("terrain.handoff.assemble_scene", lambda *a, **k: pytest.fail("rendered"))
        with pytest.raises(ValueError):
            handoff(path, output, 1, "wrong")
        assert (
            main(
                [
                    "workshop",
                    "handoff",
                    str(path),
                    "--output-dir",
                    str(output),
                    "--revision",
                    "1",
                    "--sha256",
                    "wrong",
                ]
            )
            == 1
        )
        assert (
            main(
                [
                    "workshop",
                    "handoff",
                    str(tmp_path / "absent"),
                    "--output-dir",
                    str(output),
                    "--revision",
                    "1",
                    "--sha256",
                    "wrong",
                ]
            )
            == 1
        )
    assert not output.exists()
    assert (path / "workshop-state.json").read_bytes() == before

    catalog_path = tmp_path / "catalog.json"
    catalog = read_json(catalog_path)
    asset = catalog["assets"][0]
    asset.update(
        license={"name": "Fixture license"},
        units_confirmed=True,
        printed=1,
        connectors={"system": "OpenLOCK", "status": "fixture"},
    )
    catalog_path.write_text(json.dumps(catalog))
    scene_path = path / "scene.json"
    scene = read_json(scene_path)
    scene["rough"]["proxies"] = []
    scene["handoff"] = {
        "removable": ["steps"],
        "nonprinted": ["fixture token"],
        "handedness": "No handed pieces",
    }
    scene_path.write_text(json.dumps(scene))
    monkeypatch.setattr(
        "terrain.visual.render_seated",
        lambda source, destination, *a, **k: Image.new("RGB", (40, 30), "#777777").save(
            destination
        ),
    )
    checkpoint(path, tmp_path / "out", "Rough", "Place all parts")
    ref = workshop_status(path)["revisions"]["scene"]
    with pytest.raises(ValueError):
        handoff(path, output, 1, ref["sha256"])
    assert not output.exists()
    accept_rough(path, 1, ref["sha256"], "I accept rough revision 1 for sample review")
    sample = build_sample(
        path, tmp_path / "sample", "altar", "dais", "steps", "Fixture", "Simplified", "Details"
    )["sample"]
    assert "Review sample" in workshop_status(path)["pending_decision"]
    decide_sample(
        path, 1, sample["sha256"], "approved", "I would print the board if it matched sample 1"
    )
    checkpoint(path, tmp_path / "out", "Final", "Finish board")
    ref = workshop_status(path)["revisions"]["scene"]
    decide_finished(path, 2, ref["sha256"], "play", "I approve finished play revision 2")
    assert "finished visuals" in workshop_status(path)["pending_decision"]
    with pytest.raises(ValueError):
        handoff(path, output, 2, ref["sha256"])
    assert not output.exists()
    decide_finished(path, 2, ref["sha256"], "visual", "I approve finished board revision 2")
    assert "handoff" in workshop_status(path)["pending_decision"]
    state_file = path / "workshop-state.json"
    original_state = state_file.read_bytes()
    state = read_json(state_file)
    event_ref = state["quality"]["history"][-1]
    event_path = path / "quality" / f"{event_ref['number']:04}.json"
    original_event = event_path.read_bytes()
    event = read_json(event_path)
    event["workshop_id"] = "another-workshop"
    event_path.write_text(json.dumps(event))
    event_ref["sha256"] = sha256(event_path)
    state_file.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="another workshop"):
        handoff(path, output, 2, ref["sha256"])
    assert not output.exists()
    event_path.write_bytes(original_event)
    state_file.write_bytes(original_state)
    scene_bytes = scene_path.read_bytes()
    scene_path.write_bytes(scene_bytes + b" ")
    with pytest.raises(ValueError, match="changed"):
        handoff(path, output, 2, ref["sha256"])
    assert not output.exists()
    scene_path.write_bytes(scene_bytes)
    layout_path = path / "layouts" / "0001.json"
    layout_bytes = layout_path.read_bytes()
    layout_path.write_bytes(layout_bytes + b" ")
    with pytest.raises(ValueError, match="changed"):
        handoff(path, output, 2, ref["sha256"])
    assert not output.exists()
    layout_path.write_bytes(layout_bytes)
    with pytest.raises(ValueError, match="current finished"):
        handoff(path, output, 1, ref["sha256"])
    assert not output.exists()
    pending = handoff(path, output, 2, ref["sha256"])
    pack = Path(pending["handoff"])
    assert pending["release"]["status"] == "pending"
    assert pending["release"]["checks"]["openlock_coupon"]["status"] == "pending"
    assert verify_handoff(path, pack)["valid"]
    assert not (pack / "print-list.csv").exists()
    assert "fixture token" in (pack / "handoff-assembly.md").read_text()
    assert read_json(pack / "handoff.json")["print_table"][0]["outstanding"] == 3
    catalog_bytes = catalog_path.read_bytes()
    catalog_path.write_bytes(catalog_bytes + b" ")
    with pytest.raises(ValueError, match="catalog changed"):
        verify_handoff(path, pack)
    catalog_path.write_bytes(catalog_bytes)
    picture = pack / "top.png"
    original_picture = picture.read_bytes()
    picture.write_bytes(original_picture + b"changed")
    with pytest.raises(ValueError, match="artifact changed"):
        verify_handoff(path, pack)
    picture.write_bytes(original_picture)

    local_evidence = tmp_path / "test-only-evidence.txt"
    local_evidence.write_text("Test fixture, not a real physical or slicer result.")
    link = {"path": str(local_evidence), "sha256": sha256(local_evidence)}
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "workshop_id": workshop_status(path)["workshop_id"],
                "snapshot_sha256": ref["sha256"],
                "checks": {
                    name: {"status": "verified", "note": "Test only", "evidence": [link]}
                    for name in CHECKS
                },
            }
        )
    )
    evidence = read_json(evidence_path)
    evidence["workshop_id"] = "wrong-workshop"
    evidence_path.write_text(json.dumps(evidence))
    with pytest.raises(ValueError, match="identify this workshop"):
        handoff(path, tmp_path / "wrong-evidence", 2, ref["sha256"], evidence_path)
    assert not (tmp_path / "wrong-evidence").exists()
    evidence["workshop_id"] = workshop_status(path)["workshop_id"]
    evidence_path.write_text(json.dumps(evidence))
    complete = handoff(path, tmp_path / "complete", 2, ref["sha256"], evidence_path)
    assert complete["release"]["status"] == "evidence recorded"
    assert verify_handoff(path, complete["handoff"])["valid"]
    local_evidence.write_text("changed")
    with pytest.raises(ValueError, match="evidence changed"):
        verify_handoff(path, complete["handoff"])
    trimesh.creation.box(extents=[11, 10, 10]).export(models / "box.stl")
    with pytest.raises(ValueError, match="changed"):
        verify_handoff(path, pack)
    with pytest.raises(ValueError, match="changed"):
        handoff(path, tmp_path / "stale-output", 2, ref["sha256"])
    assert not (tmp_path / "stale-output").exists()


def test_handoff_excludes_unknown_license_and_preserves_unknown_stock(workshop):
    from terrain.handoff import inventory

    path, _, _ = workshop
    scene, catalog, resolved = resolve_placements(path / "scene.json")
    rows, excluded = inventory(scene, catalog, resolved, {"proxy_placements": ["cover"]})
    assert rows == []
    assert any(item.get("reason") == "unknown license" for item in excluded)
    assert any(item.get("placement") == "cover" for item in excluded)
    licensed = []
    for placement, asset, matrix, bounds in resolved:
        asset = {**asset, "license": {"name": "Fixture"}, "printed": None}
        licensed.append((placement, asset, matrix, bounds))
    rows, excluded = inventory(scene, catalog, licensed, {"proxy_placements": ["cover"]})
    assert rows[0]["required"] == 3
    assert rows[0]["physical_stock"] is None and rows[0]["outstanding"] is None
    assert len(excluded) == 1


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
