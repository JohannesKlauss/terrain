import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import trimesh
from PIL import Image

from terrain.cli import main
from terrain.layout import check_plan
from terrain.library import index_library, read_json
from terrain.workshop import (
    approve_layout,
    init_workshop,
    save_layout,
    workshop_lock,
    workshop_status,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/workshop-2d-plan.json"


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "scenes/chapel"
    init_workshop(path, tmp_path / "missing-catalog.json", "Chapel", "A dangerous altar")
    return path, read_json(EXAMPLE)


def test_save_refine_resume_and_reopen(setup, tmp_path):
    path, plan = setup
    first = save_layout(path, plan, 0)
    saved = first["source"].read_bytes()
    sheet = first["sheet"].read_text()
    assert "TOP DOWN" in sheet and "Physical unknowns" in sheet
    assert "direct" in sheet and "offset" in sheet and "25.4" in sheet
    assert first["checks"]["direct"]["routes"][0]["status"] == "feasible"
    assert first["checks"]["direct"]["interactions"][0]["status"] == "connected"
    result = subprocess.run(
        [str(Path(sys.executable).parent / "terrain"), "workshop", "status", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout)["pending_decision"] == plan["pending_decision"]
    plan["options"][0]["features"][2]["at"] = [110, 145]
    plan["changes"] = "Moved cover 10 mm west and 5 mm south."
    plan["clarified"] = "The direct aisle remains open."
    plan["pending_decision"] = "Approve the moved cover?"
    second = save_layout(path, plan, 1)
    assert first["source"].read_bytes() == saved
    assert second["revision"]["number"] == 2
    assert workshop_status(path)["pending_decision"] == "Approve the moved cover?"
    ref = second["revision"]
    approve_layout(path, 2, ref["sha256"], "I approve 2D revision 2 option direct for 3D")
    assert workshop_status(path)["stage"] == "3d"
    plan["changes"] = "Library fit requires moving cover."
    plan["options"][0]["features"][2]["at"] = [100, 145]
    third = save_layout(path, plan, 2)
    assert third["revision"]["number"] == 3
    assert workshop_status(path)["stage"] == "layout_review"
    assert (
        main(["scene", "build", str(path / "scene.json"), "--output-dir", str(tmp_path / "out")])
        == 1
    )
    assert not (tmp_path / "out").exists()


def test_check_distinguishes_clear_tight_and_blocked_routes(setup):
    path, plan = setup
    plan["options"][0]["routes"][0]["width_mm"] = 35
    plan["options"][1]["features"][2]["at"] = [100, 185]
    checks = check_plan(plan)
    assert checks["direct"]["routes"][0]["status"] == "tight"
    assert checks["offset"]["routes"][0]["status"] == "blocked"
    assert checks["offset"]["interactions"][0]["status"] == "unverified"
    saved = save_layout(path, plan, 0)
    assert "flank blocked" in saved["sheet"].read_text()
    assert "aisle tight" in saved["sheet"].read_text()
    plan["selected_option"] = "offset"
    saved = save_layout(path, plan, 1)
    with pytest.raises(ValueError, match="unchecked"):
        approve_layout(
            path, 2, saved["revision"]["sha256"], "I approve 2D revision 2 option offset for 3D"
        )


def test_invalid_footprint_cannot_be_approved(setup):
    path, plan = setup
    plan["dimensions"]["footprint_limit_mm"] = [200, 200]
    saved = save_layout(path, plan, 0)
    assert saved["checks"]["direct"]["footprint"] == "exceeds"
    with pytest.raises(ValueError, match="unchecked"):
        approve_layout(
            path, 1, saved["revision"]["sha256"], "I approve 2D revision 1 option direct for 3D"
        )


def test_approval_rejects_assent_old_other_and_changed_files(setup, tmp_path):
    path, plan = setup
    result = save_layout(path, plan, 0)
    ref = result["revision"]
    for answer in (
        "",
        "yes",
        "I pick direct",
        "I approve 2D revision 1 option direct for 3D if it fits",
    ):
        with pytest.raises(ValueError):
            approve_layout(path, 1, ref["sha256"], answer)
    other = tmp_path / "other"
    init_workshop(other, None, "Other", "Different workshop")
    other_ref = save_layout(other, copy.deepcopy(plan), 0)["revision"]
    with pytest.raises(ValueError):
        approve_layout(path, 1, other_ref["sha256"], "I approve 2D revision 1 option direct for 3D")
    result2 = save_layout(path, plan, 1)
    with pytest.raises(ValueError):
        approve_layout(path, 1, ref["sha256"], "I approve 2D revision 1 option direct for 3D")
    result2["source"].write_text(result2["source"].read_text() + " ")
    with pytest.raises(ValueError, match="changed"):
        approve_layout(
            path, 2, result2["revision"]["sha256"], "I approve 2D revision 2 option direct for 3D"
        )
    assert (
        main(["scene", "build", str(path / "scene.json"), "--output-dir", str(tmp_path / "out")])
        == 1
    )
    assert not (tmp_path / "out").exists()


def test_preapproval_never_calls_3d_tools(setup, tmp_path, monkeypatch):
    path, plan = setup

    def forbidden(*args, **kwargs):
        pytest.fail("3D tool invoked")

    monkeypatch.setattr("terrain.scene.scene_catalog", forbidden)
    monkeypatch.setattr("terrain.scene.render_source", forbidden)
    monkeypatch.setattr("terrain.custom.draft_asset", forbidden)
    monkeypatch.setattr("terrain.workshop.resolve_placements", forbidden)
    result = save_layout(path, plan, 0)
    out = tmp_path / "out"
    scene = str(path / "scene.json")
    commands = [
        ["scene", "add", scene, "--asset", "x", "--id", "x", "--at", "0", "0", "0"],
        ["scene", "add-custom", scene, "--draft", "x", "--id", "x", "--at", "0", "0", "0"],
        ["scene", "build", scene, "--output-dir", str(out)],
        [
            "workshop",
            "checkpoint",
            str(path),
            "--output-dir",
            str(out),
            "--title",
            "x",
            "--changes",
            "x",
        ],
        ["workshop", "review", str(path), "--output-dir", str(out)],
    ]
    for command in commands:
        assert main(command) == 1
    assert not out.exists()
    assert result["sheet"].exists()


def test_approved_layout_unlocks_real_scene_and_checkpoint(tmp_path, monkeypatch):
    models = tmp_path / "models"
    models.mkdir()
    trimesh.creation.box(extents=[10, 10, 10]).export(models / "wall.stl")
    catalog = tmp_path / "catalog.json"
    index_library(models, catalog)
    path = tmp_path / "workshop"
    init_workshop(path, catalog, "Chapel", "Altar")
    working = path / "scene.json"
    scene_record = read_json(working)
    scene_record["rough"] = {
        "bindings": {},
        "tolerance_mm": 1,
        "clearance_height_mm": 30,
        "gaps": [],
        "sourcing": [],
        "proxies": [],
        "physical_unknowns": [],
    }
    working.write_text(json.dumps(scene_record))
    result = save_layout(path, read_json(EXAMPLE), 0)
    ref = result["revision"]
    approve_layout(path, 1, ref["sha256"], "I approve 2D revision 1 option direct for 3D")
    monkeypatch.setattr(
        "terrain.scene.render_source",
        lambda source, dest, *a, **k: Image.new("RGB", (40, 30)).save(dest),
    )
    scene = str(path / "scene.json")
    add = ["scene", "add", scene, "--asset", "wall.stl", "--id", "wall", "--at", "30", "30", "0"]
    with workshop_lock(path, state_update=True):
        result_process = subprocess.run(
            [str(Path(sys.executable).parent / "terrain"), *add], capture_output=True, text=True
        )
        assert result_process.returncode == 1
        assert "locked" in result_process.stderr
    assert main(add) == 0
    assert (
        main(
            [
                "workshop",
                "checkpoint",
                str(path),
                "--output-dir",
                str(tmp_path / "review"),
                "--title",
                "First",
                "--changes",
                "Place wall",
            ]
        )
        == 0
    )
    assert (path / "revisions/0001.json").is_file()
    assert main(["workshop", "review", str(path), "--output-dir", str(tmp_path / "rebuilt")]) == 0
    assert (tmp_path / "rebuilt/0001/review.html").is_file()
    result["sheet"].write_text(result["sheet"].read_text() + " ")
    assert main(["scene", "build", scene, "--output-dir", str(tmp_path / "out")]) == 1
    assert not (tmp_path / "out").exists()
