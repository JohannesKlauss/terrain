from pathlib import Path

from terrain.mesh import MeshRules, inspect_mesh

ROOT = Path(__file__).parents[1]
E_FLOOR = ROOT / "build" / "test-meshes" / "e_floor-plain-42.stl"


def test_vendor_degenerates_are_reported_within_explicit_budget():
    report = inspect_mesh(
        E_FLOOR,
        MeshRules(
            expected_extents=(50.8, 50.8, 7.0),
            expected_components=1,
            allowed_degenerate=19,
        ),
    )

    assert report["valid"] is True
    assert report["metrics"]["degenerate_triangles"] == 19
    assert "19 zero-area" in report["warnings"][0]


def test_baseline_topology_notes_are_visible_in_reports():
    report = inspect_mesh(
        E_FLOOR,
        MeshRules(
            allowed_degenerate=19,
            baseline_notes=("49 open edges in official baseline",),
        ),
    )

    assert report["valid"] is True
    assert "49 open edges in official baseline" in report["warnings"]


def test_excess_degenerate_faces_are_rejected():
    report = inspect_mesh(E_FLOOR, MeshRules(allowed_degenerate=18))

    assert report["valid"] is False
    assert any("zero-area" in error for error in report["errors"])


def test_wrong_scale_and_component_count_are_rejected():
    report = inspect_mesh(
        E_FLOOR,
        MeshRules(
            expected_extents=(5.08, 5.08, 0.7),
            expected_components=2,
            allowed_degenerate=19,
        ),
    )

    assert report["valid"] is False
    assert any("extents" in error for error in report["errors"])
    assert any("components" in error for error in report["errors"])


def test_open_mesh_is_rejected(tmp_path):
    artifact = tmp_path / "open.stl"
    artifact.write_text(
        "solid open\n"
        "facet normal 0 0 1\n"
        "outer loop\n"
        "vertex 0 0 0\n"
        "vertex 1 0 0\n"
        "vertex 0 1 0\n"
        "endloop\n"
        "endfacet\n"
        "endsolid open\n"
    )

    report = inspect_mesh(artifact)

    assert report["valid"] is False
    assert any("watertight" in error for error in report["errors"])


def test_missing_mesh_returns_error_report(tmp_path):
    report = inspect_mesh(tmp_path / "missing.stl")

    assert report["valid"] is False
    assert report["errors"]
