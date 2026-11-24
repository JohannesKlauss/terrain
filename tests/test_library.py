import json
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pytest
import trimesh

from terrain.cli import main
from terrain.library import index_library, load_catalog, search_assets, source_path
from terrain.visual import preview_library


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "purchased"
    pack = root / "Industrial"
    pack.mkdir(parents=True)
    mesh = trimesh.creation.box(extents=(20, 30, 8))
    mesh.apply_translation((100, -40, 4))
    mesh.export(pack / "Pipe Control.stl")
    (pack / "broken.stl").write_text("not a mesh")
    (pack / "license.txt").write_text("PERSONAL USE ONLY, you may not share, modify or sell them.")
    metadata = tmp_path / "metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "collections": {"Industrial": {"tags": ["laboratory", "industrial"]}},
                "assets": {
                    "Industrial/Pipe Control.stl": {
                        "description": "A corroded pressure regulator",
                        "printed": 1,
                    }
                },
            }
        )
    )
    catalog = tmp_path / "catalog.json"
    return root, metadata, catalog


def test_index_is_read_only_searchable_and_explicit_about_unknown_fit(library):
    root, metadata, destination = library
    before = (root / "Industrial/Pipe Control.stl").read_bytes()
    result = index_library(root, destination, metadata)
    assert result["indexed"] == 1
    assert result["failed"] == 1
    catalog = load_catalog(destination)
    asset = search_assets(catalog, "laboratory pressure")[0]
    assert asset["id"] == "Industrial/Pipe Control.stl"
    assert asset["extents_mm"] == pytest.approx((20, 30, 8))
    assert asset["bounds_mm"][0] == pytest.approx((90, -55, 0))
    assert asset["printed"] == 1
    assert asset["units_confirmed"] is False
    assert asset["connectors"]["status"] == "unverified"
    assert asset["license"]["modify"] is False
    assert asset["license"]["redistribute"] is False
    assert (root / "Industrial/Pipe Control.stl").read_bytes() == before
    assert search_assets(catalog, "no such shape") == []


def test_reindex_preserves_annotations_but_refreshes_changed_and_removed_files(library):
    root, metadata, destination = library
    index_library(root, destination, metadata)
    original = load_catalog(destination)["assets"][0]["sha256"]
    trimesh.creation.box(extents=(4, 5, 6)).export(root / "Industrial/Pipe Control.stl")
    (root / "Industrial/broken.stl").unlink()
    index_library(root, destination, metadata)
    catalog = load_catalog(destination)
    assert len(catalog["assets"]) == 1
    asset = catalog["assets"][0]
    assert asset["sha256"] != original
    assert asset["extents_mm"] == pytest.approx((4, 5, 6))
    assert asset["printed"] == 1


def test_index_keeps_3mf_instances_and_transforms(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    scene = trimesh.Scene()
    box = trimesh.creation.box(extents=(2, 4, 6))
    scene.add_geometry(box, geom_name="box", node_name="first")
    scene.graph.update(
        frame_to="second",
        geometry="box",
        matrix=trimesh.transformations.translation_matrix((10, 0, 0)),
    )
    (root / "instances.3mf").write_bytes(trimesh.exchange.threemf.export_3MF(scene))
    index_library(root, tmp_path / "catalog.json")
    asset = load_catalog(tmp_path / "catalog.json")["assets"][0]
    assert asset["extents_mm"] == pytest.approx((12, 4, 6))
    assert asset["triangles"] == 24
    assert asset["license"]["name"] == "unknown"


def test_3mf_declared_units_are_interpreted_in_millimetres(tmp_path):
    root = tmp_path / "models"
    root.mkdir()
    model = trimesh.Scene(trimesh.creation.box(extents=(2, 4, 6)))
    raw = tmp_path / "raw.3mf"
    raw.write_bytes(trimesh.exchange.threemf.export_3MF(model))
    with zipfile.ZipFile(raw) as source, zipfile.ZipFile(root / "centimetres.3mf", "w") as out:
        for name in source.namelist():
            contents = source.read(name)
            if name.endswith(".model"):
                document = ET.fromstring(contents)
                document.set("unit", "centimeter")
                contents = ET.tostring(document)
            out.writestr(name, contents)
    index_library(root, tmp_path / "catalog.json")
    asset = load_catalog(tmp_path / "catalog.json")["assets"][0]
    assert asset["extents_mm"] == pytest.approx((20, 40, 60))


def test_reindex_uses_recorded_annotation_file_when_flag_is_omitted(library):
    root, metadata, destination = library
    index_library(root, destination, metadata)
    index_library(root, destination)
    asset = search_assets(load_catalog(destination), "pressure")[0]
    assert asset["printed"] == 1


def test_catalog_paths_cannot_escape_the_library(library):
    root, metadata, destination = library
    index_library(root, destination, metadata)
    catalog = load_catalog(destination)
    with pytest.raises(ValueError, match="outside"):
        source_path(catalog, {"path": "../secret.stl"})
    assert source_path(catalog, search_assets(catalog)[0]).is_relative_to(root)


def test_index_rejects_missing_root_and_bad_inventory(library):
    root, metadata, destination = library
    with pytest.raises(ValueError, match="directory"):
        index_library(root / "missing", destination)
    metadata.write_text(json.dumps({"assets": {"Industrial/Pipe Control.stl": {"printed": -1}}}))
    with pytest.raises(ValueError, match="printed"):
        index_library(root, destination, metadata)


def test_library_cli_and_real_multiangle_contact_sheet(library, tmp_path, capsys):
    _, metadata, destination = library
    assert (
        main(
            [
                "library",
                "index",
                str(library[0]),
                "--catalog",
                str(destination),
                "--metadata",
                str(metadata),
            ]
        )
        == 1
    )  # A broken mesh is reported, not silently skipped.
    capsys.readouterr()
    assert (
        main(
            [
                "library",
                "search",
                "pressure",
                "--catalog",
                str(destination),
            ]
        )
        == 0
    )
    assert "Pipe Control" in capsys.readouterr().out
    catalog = load_catalog(destination)
    result = preview_library(
        catalog, search_assets(catalog), tmp_path / "previews", views=("iso", "top", "underside")
    )
    from PIL import Image

    assert len(result["sheets"]) == 1
    selection = json.loads(result["selection"].read_text())
    assert selection["assets"][0]["id"] == "Industrial/Pipe Control.stl"
    assert len(selection["assets"][0]["previews"]) == 3
    pixels = np.asarray(Image.open(result["sheets"][0]).convert("RGB"))
    assert pixels.std() > 10
    assert all(path.is_file() for path in result["sheets"])
