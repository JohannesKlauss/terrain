import hashlib
import json
from pathlib import Path

import pytest
import trimesh

ROOT = Path(__file__).parents[1]
ASSET_DIR = ROOT / "assets" / "openlock" / "official"
EXPECTED_HASHES = {
    "A-Wall-Low-TRP-v7.2.stl": "635029a34ea89ba4b6d4c3457cbe8523dfb09b25d44678c51c727612d0dbb3d4",
    "Column-L-TRP-v7.5.stl": "91255a6aacb8bc8a360d467f70eb978c11b65ce8987d99420bf90a6e911fe5b1",
    "E-TRP-v7.6.stl": "6809aab3fdc64f78d651faaba01049b306b54dad7ba9feaa28e038dba25dc17a",
    "OpenLOCK-Clip-v5.4.stl": "50d2e770f52f6c6836d157b4351b39a6b6733ddb625b2cb08611866965fe7cd6",
}
EXPECTED_EXTENTS = {
    "A-Wall-Low-TRP-v7.2.stl": (50.8, 12.7, 25.4),
    "Column-L-TRP-v7.5.stl": (11.5381, 11.5381, 50.8),
    "E-TRP-v7.6.stl": (50.8, 50.8, 7.0),
    "OpenLOCK-Clip-v5.4.stl": (13.2, 19.5, 3.5),
}


def test_official_assets_match_pinned_hashes_and_provenance():
    manifest_path = ROOT / "assets" / "openlock" / "provenance.json"
    manifest = json.loads(manifest_path.read_text())

    assert manifest["system_version"] == "8.6"
    assert manifest["clip_version"] == "5.4"
    assert manifest["license"] == "CC BY-NC 4.0"
    assert manifest["commercial_use"] is False
    assert manifest["attribution"] == "Printable Scenery - https://www.printablescenery.com/"
    assert set(manifest["files"]) == set(EXPECTED_HASHES)

    for name, expected_hash in EXPECTED_HASHES.items():
        payload = (ASSET_DIR / name).read_bytes()
        record = manifest["files"][name]
        assert hashlib.sha256(payload).hexdigest() == expected_hash
        assert record["sha256"] == expected_hash
        assert record["source_url"].startswith("https://www.myminifactory.com/object/")
        assert record["license"] == manifest["license"]


def test_e_floor_vendor_topology_discrepancy_is_recorded():
    manifest = json.loads((ROOT / "assets" / "openlock" / "provenance.json").read_text())
    issue = manifest["files"]["E-TRP-v7.6.stl"]["known_mesh_issues"]["openscad_mcp_0_6_1"]

    assert issue["open_edge_count"] == 49
    assert issue["degenerate_triangle_count"] == 19
    assert issue["generated_plain_stl_matches_baseline"] is True


@pytest.mark.parametrize("name,expected_extents", EXPECTED_EXTENTS.items())
def test_official_meshes_are_single_watertight_solids_at_expected_scale(name, expected_extents):
    mesh = trimesh.load_mesh(ASSET_DIR / name, process=True)

    assert mesh.is_watertight
    assert mesh.is_winding_consistent
    assert mesh.volume > 0
    assert len(mesh.split(only_watertight=False)) == 1
    assert mesh.extents == pytest.approx(expected_extents, abs=0.002)
