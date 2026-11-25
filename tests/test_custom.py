import json
from pathlib import Path

import pytest
import trimesh
from PIL import Image

from terrain.cli import main
from terrain.custom import approve_custom, blender_executable, create_custom, draft_asset
from terrain.library import index_library, load_catalog, sha256, source_path, write_json
from terrain.scene import add_custom_placement, assemble_scene, init_scene
from terrain.workshop import checkpoint, init_workshop, review_workshop


def init_legacy_workshop(path, catalog, name, brief):
    init_workshop(path, catalog, name, brief)
    (path / ".terrain-staged.json").unlink()
    (path / "workshop-state.json").unlink()
    scene = json.loads((path / "scene.json").read_text())
    del scene["staged_workshop"]
    write_json(path / "scene.json", scene)


@pytest.fixture
def draft(tmp_path):
    path = tmp_path / "drafts" / "altar-v1"
    path.mkdir(parents=True)
    trimesh.creation.box(extents=[50.8, 50.8, 7]).export(path / "model.stl")
    (path / "model.blend").write_bytes(b"test blend source")
    (path / "build.py").write_text("# original source\n")
    manifest = path / "draft.json"
    write_json(
        manifest,
        {
            "schema_version": 1,
            "status": "custom_unindexed",
            "name": "Original altar",
            "brief": "A low altar tile",
            "license": {
                "name": "Original personal-use work",
                "modify": True,
                "redistribute": False,
            },
            "files": {
                name: sha256(path / name) for name in ("model.stl", "model.blend", "build.py")
            },
        },
    )
    return manifest


@pytest.fixture
def catalog(tmp_path):
    root = tmp_path / "purchased"
    root.mkdir()
    trimesh.creation.box().export(root / "wall.stl")
    path = tmp_path / "catalog.json"
    index_library(root, path)
    return path


@pytest.fixture
def quick_previews(monkeypatch):
    monkeypatch.setattr(
        "terrain.scene.render_source",
        lambda source, destination, *a, **k: Image.new("RGB", (100, 80), "#345678").save(
            destination
        ),
    )


def test_unindexed_draft_in_scene_and_saved_review(draft, catalog, tmp_path, quick_previews):
    workshop = tmp_path / "workshop"
    init_legacy_workshop(workshop, catalog, "Shrine", "An original focal point")
    add_custom_placement(workshop / "scene.json", draft, "altar", [0, 0, 0])
    result = checkpoint(workshop, tmp_path / "review", "Draft", "Add custom altar")
    report = json.loads((result["review"].parent / "report.json").read_text())
    assert report["placements"][0]["library_status"] == "custom_unindexed"
    assert report["print_list"] == []
    assert report["custom_models"][0]["required"] == 1
    assert "Custom · unindexed · approval pending" in result["review"].read_text()
    assert "custom_unindexed" in result["review"].read_text()
    assert not (tmp_path / "assets").exists()
    assert len(load_catalog(catalog)["assets"]) == 1
    review_workshop(workshop, tmp_path / "rebuilt")
    assert "Custom · unindexed" in (tmp_path / "rebuilt/0001/review.html").read_text()


def test_approval_is_explicit_hash_pinned_and_reindexable(draft, catalog, tmp_path):
    root = tmp_path / "assets/custom"
    before = catalog.read_bytes()
    with pytest.raises(ValueError, match="approval"):
        approve_custom(draft, "altar", root, catalog, "", sha256(draft))
    assert not root.exists()
    assert catalog.read_bytes() == before
    with pytest.raises(ValueError, match="changed"):
        approve_custom(draft, "altar", root, catalog, "User approved this revision", "0" * 64)
    assert not root.exists()
    result = approve_custom(
        draft, "altar", root, catalog, "User: approve this altar for the library", sha256(draft)
    )
    assert result["asset"] == "custom/altar/model.stl"
    data = load_catalog(catalog)
    asset = next(a for a in data["assets"] if a["id"] == result["asset"])
    assert source_path(data, asset) == root / "altar/model.stl"
    assert asset["license"]["name"] == "Original personal-use work"
    assert (root / "altar/model.blend").read_bytes() == (draft.parent / "model.blend").read_bytes()
    assert asset["printed"] is None
    assert asset["print_validation"] == "not_checked"
    index_library(data["root"], catalog)
    assert len(load_catalog(catalog)["assets"]) == 2
    with pytest.raises(ValueError, match="exists"):
        approve_custom(draft, "altar", root, catalog, "Approve", sha256(draft))


@pytest.mark.parametrize("name", ["model.stl", "model.blend", "build.py"])
def test_modified_draft_cannot_be_previewed_or_approved(draft, catalog, tmp_path, name):
    (draft.parent / name).write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        draft_asset(draft)
    with pytest.raises(ValueError, match="changed"):
        approve_custom(
            draft, "altar", tmp_path / "assets/custom", catalog, "Approve", sha256(draft)
        )
    assert not (tmp_path / "assets").exists()


def test_drafts_only_scene_and_transform_hash_checks(draft, tmp_path):
    scene = tmp_path / "scene.json"
    init_scene(scene, None, "Draft", "No library needed")
    add_custom_placement(scene, draft, "altar", [10, 20, 0], [0, 0, 90])
    result = assemble_scene(scene, tmp_path / "out")
    assert "custom_unindexed" in result["report"].read_text()
    (draft.parent / "model.stl").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        assemble_scene(scene, tmp_path / "other")


def test_create_refuses_assets_and_existing_drafts_before_running_blender(tmp_path):
    script = tmp_path / "original.py"
    script.write_text("import bpy\n")
    for path in (tmp_path / "assets/new", tmp_path / "existing"):
        if path.name == "existing":
            path.mkdir()
        with pytest.raises(ValueError):
            create_custom(path, script, "Name", "Brief", "Original", blender="not-installed")
    assert not (tmp_path / "assets").exists()


def test_approval_cli_requires_confirmation_and_exact_revision(draft, catalog, tmp_path):
    args = [
        "custom",
        "approve",
        str(draft),
        "--id",
        "altar",
        "--assets-root",
        str(tmp_path / "assets/custom"),
        "--catalog",
        str(catalog),
    ]
    with pytest.raises(SystemExit):
        main(args)
    assert not (tmp_path / "assets").exists()


def test_drafts_are_not_picked_up_by_a_broad_index(draft, tmp_path):
    index = tmp_path / "broad.json"
    index_library(draft.parent.parent, index)
    assert load_catalog(index)["assets"] == []


def test_approval_without_an_existing_library_remembers_provenance(draft, tmp_path):
    root = tmp_path / "assets/custom"
    catalog = tmp_path / "new-catalog.json"
    result = approve_custom(draft, "altar", root, catalog, "Approve", sha256(draft))
    assert result["asset"] == "custom/altar/model.stl"
    index_library(root, catalog)
    asset = load_catalog(catalog)["assets"][0]
    assert asset["license"]["name"] == "Original personal-use work"
    assert asset["name"] == "Original altar"
    approve_custom(draft, "altar-copy", root, catalog, "Approve another asset", sha256(draft))
    assert len(load_catalog(catalog)["assets"]) == 2


def test_adding_purchased_library_later_keeps_approved_ids_and_saved_scenes(draft, tmp_path):
    from terrain.scene import add_placement

    catalog = tmp_path / "catalog.json"
    root = tmp_path / "assets/custom"
    approved = approve_custom(draft, "altar", root, catalog, "Approve", sha256(draft))
    scene = tmp_path / "scene.json"
    init_scene(scene, catalog, "Shrine", "An approved original")
    add_placement(scene, approved["asset"], "altar", [0, 0, 0])
    purchased = tmp_path / "purchased-later"
    purchased.mkdir()
    trimesh.creation.box().export(purchased / "wall.stl")
    index_library(purchased, catalog)
    data = load_catalog(catalog)
    assert len(data["assets"]) == 2
    asset = next(a for a in data["assets"] if a["id"] == approved["asset"])
    assert source_path(data, asset) == root / "altar/model.stl"
    assert asset["license"]["name"] == "Original personal-use work"
    result = assemble_scene(scene, tmp_path / "preview")
    assert json.loads(result["report"].read_text())["print_list"][0]["asset"] == approved["asset"]


def test_index_failure_rolls_back_only_the_newly_approved_copy(
    draft, catalog, tmp_path, monkeypatch
):
    root = tmp_path / "assets/custom"
    existing = root / "user-notes.txt"
    root.mkdir(parents=True)
    existing.write_text("Keep this")
    before = catalog.read_bytes()

    def fail(*args, **kwargs):
        raise ValueError("index failed")

    monkeypatch.setattr("terrain.custom.index_library", fail)
    with pytest.raises(ValueError, match="index failed"):
        approve_custom(draft, "altar", root, catalog, "Approve", sha256(draft))
    assert not (root / "altar").exists()
    assert existing.read_text() == "Keep this"
    assert catalog.read_bytes() == before


def test_approved_model_is_placeable_without_changing_historical_drafts(
    draft, catalog, tmp_path, quick_previews
):
    from terrain.scene import add_placement

    workshop = tmp_path / "workshop"
    init_legacy_workshop(workshop, catalog, "Shrine", "Original focus")
    add_custom_placement(workshop / "scene.json", draft, "altar", [0, 0, 0])
    first = checkpoint(workshop, tmp_path / "review", "Draft", "Unindexed altar")
    frozen = first["snapshot"].read_bytes()
    result = approve_custom(
        draft, "altar", tmp_path / "assets/custom", catalog, "Approved", sha256(draft)
    )
    scene = json.loads((workshop / "scene.json").read_text())
    scene["placements"] = []
    scene["custom_models"] = {}
    write_json(workshop / "scene.json", scene)
    add_placement(workshop / "scene.json", result["asset"], "altar", [0, 0, 0])
    second = checkpoint(workshop, tmp_path / "review", "Approved", "Use indexed original")
    report = json.loads((second["review"].parent / "report.json").read_text())
    assert len(report["print_list"]) == 1
    assert report["custom_models"] == []
    assert first["snapshot"].read_bytes() == frozen
    review_workshop(workshop, tmp_path / "rebuilt")
    assert "Custom · unindexed" in (tmp_path / "rebuilt/0001/review.html").read_text()
    assert "Custom · unindexed" not in (tmp_path / "rebuilt/0002/review.html").read_text()


@pytest.fixture
def real_blender():
    try:
        return blender_executable()
    except ValueError:
        pytest.skip("Blender is not installed")


def test_real_blender_cli_create_preview_and_approval(tmp_path, real_blender, capsys):
    source = Path(__file__).parents[1] / "examples/blender/stepped_plinth.py"
    path = tmp_path / "drafts/plinth-v1"
    assert (
        main(
            [
                "custom",
                "create",
                str(path),
                "--script",
                str(source),
                "--name",
                "Original plinth",
                "--brief",
                "Original stepped platform",
                "--blender",
                real_blender,
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert Path(result["review"]).is_file()
    assert (path / "model.blend").stat().st_size > 1000
    validation = json.loads((path / "validation.json").read_text())
    assert validation["valid"]
    assert validation["path"] == str(path / "model.stl")
    assert validation["metrics"]["extents_mm"] == pytest.approx([50.8, 50.8, 7], abs=0.001)
    # Independent analytic volume of the two stepped prisms in the source brief.
    assert validation["metrics"]["volume_mm3"] == pytest.approx(50.8**2 * 4 + 40**2 * 3)
    assert validation["metrics"]["components"] == 1
    report = json.loads(Path(result["report"]).read_text())
    assert report["print_list"] == []
    assert report["custom_models"][0]["approval"] == "pending"
    assert len(result["previews"]) == 4
    assert not (tmp_path / "assets").exists()
    assert (
        main(
            [
                "custom",
                "approve",
                str(path / "draft.json"),
                "--id",
                "plinth",
                "--assets-root",
                str(tmp_path / "assets/custom"),
                "--catalog",
                str(tmp_path / "catalog.json"),
                "--approval",
                "Automated test confirmation, not a user model approval",
                "--review-sha256",
                result["review_sha256"],
            ]
        )
        == 0
    )
    assert (tmp_path / "assets/custom/plinth/model.blend").is_file()


def test_blender_failure_never_creates_a_draft_or_assets(tmp_path, real_blender):
    from terrain.build import BuildError

    script = tmp_path / "broken.py"
    script.write_text("raise RuntimeError('intentional regression test failure')\n")
    path = tmp_path / "drafts/failed"
    with pytest.raises(BuildError, match="intentional regression test failure"):
        create_custom(path, script, "Fail", "Failure path", "Original", real_blender)
    assert not path.exists()
    assert not (tmp_path / "assets").exists()


def test_blender_export_preserves_world_transform_and_modifiers(tmp_path, real_blender):
    script = tmp_path / "transformed.py"
    script.write_text(
        "import bpy\n"
        "bpy.ops.mesh.primitive_cube_add(size=2, location=(40, 20, 3))\n"
        "obj = bpy.context.object\n"
        "obj.scale = (10, 5, 3)\n"
        "modifier = obj.modifiers.new('Double height', 'ARRAY')\n"
        "modifier.count = 2\n"
        "modifier.relative_offset_displace = (0, 0, 1)\n"
    )
    result = create_custom(
        tmp_path / "drafts/transformed",
        script,
        "Transformed",
        "Export test",
        "Original",
        real_blender,
    )
    asset = draft_asset(result["draft"])
    assert asset["bounds_mm"][0] == pytest.approx([30, 15, 0])
    assert asset["bounds_mm"][1] == pytest.approx([50, 25, 12])
