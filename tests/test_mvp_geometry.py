import hashlib
import warnings

import numpy as np
import pytest
import trimesh
from conftest import OFFICIAL, ROOT, assert_single_printable_solid, export_model

from terrain.catalog import ModelSpec

EXPECTED_EXTENTS = {
    "e_floor": (50.8, 50.8, 7.0),
    "a_wall": (50.8, 12.7, 25.4),
    "doorway": (50.8, 12.7, 25.4),
    "l_corner": (11.5381, 11.5381, 25.4),
}


def connector_signature(mesh, z_max):
    mesh = mesh.copy()
    mesh.update_faces(mesh.area_faces > 1e-7)
    mesh.remove_unreferenced_vertices()
    lower = np.round(mesh.bounds[0], 1) + 0.5
    upper = np.round(mesh.bounds[1], 1) - 0.5
    axes = [np.linspace(lower[axis], upper[axis], 9) for axis in range(2)]
    axes.append(np.linspace(0.5, z_max, 6))
    points = np.array(np.meshgrid(*axes, indexing="ij")).reshape(3, -1).T
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        inside = mesh.contains(points)
    return hashlib.sha256(np.packbits(inside).tobytes()).hexdigest()


def test_plain_low_wall_preserves_official_mesh_contract(model_mesh):
    generated = model_mesh("a_wall")
    official = trimesh.load_mesh(OFFICIAL / "A-Wall-Low-TRP-v7.2.stl", process=True)

    assert_single_printable_solid(generated, EXPECTED_EXTENTS["a_wall"])
    assert generated.bounds == pytest.approx(official.bounds, abs=0.02)
    assert generated.volume == pytest.approx(official.volume, abs=0.05)


def test_low_corner_preserves_footprint_and_cuts_only_upper_height(model_mesh):
    generated = model_mesh("l_corner")
    official = trimesh.load_mesh(OFFICIAL / "Column-L-TRP-v7.5.stl", process=True)

    assert_single_printable_solid(generated, EXPECTED_EXTENTS["l_corner"])
    assert generated.bounds[0] == pytest.approx(official.bounds[0], abs=0.02)
    assert generated.bounds[1, 2] == pytest.approx(25.4, abs=0.002)
    assert 0 < generated.volume < official.volume
    assert connector_signature(generated, 6.9) == connector_signature(official, 6.9)


def test_doorway_retains_wall_envelope_and_removes_central_opening(model_mesh):
    doorway = model_mesh("doorway")
    wall = model_mesh("a_wall")

    assert_single_printable_solid(doorway, EXPECTED_EXTENTS["doorway"])
    assert 0 < doorway.volume < wall.volume
    assert connector_signature(doorway, 6.9) == connector_signature(wall, 6.9)


def test_doorway_accepts_32mm_base_gauge():
    fixture = ROOT / "tests" / "fixtures" / "doorway_gauge.scad"
    path, _ = export_model(ModelSpec("e_floor", "plain", 42), fixture, "doorway-base-gauge")
    mesh = trimesh.load_mesh(path, process=True)
    components = mesh.split(only_watertight=False)

    assert len(components) == 2
    assert min(component.volume for component in components) == pytest.approx(
        np.pi * 16**2 * 2, rel=0.002
    )


@pytest.mark.parametrize("part,expected_extents", EXPECTED_EXTENTS.items())
@pytest.mark.parametrize("genre", ["plain", "mork_borg", "cyberpunk", "expanse"])
def test_genre_variants_preserve_part_envelope_and_printability(
    model_mesh, part, genre, expected_extents
):
    mesh = model_mesh(part, genre)

    assert_single_printable_solid(mesh, expected_extents)


@pytest.mark.parametrize(
    "part,z_max",
    [("e_floor", 6.0), ("a_wall", 6.9), ("doorway", 6.9), ("l_corner", 6.9)],
)
@pytest.mark.parametrize("genre", ["mork_borg", "cyberpunk", "expanse"])
def test_genre_decoration_does_not_change_connector_regions(model_mesh, part, genre, z_max):
    plain = model_mesh(part, "plain")
    decorated = model_mesh(part, genre)

    assert connector_signature(decorated, z_max) == connector_signature(plain, z_max)


def test_mork_borg_has_three_flagstone_channels_per_axis(model_mesh):
    mesh = model_mesh("e_floor", "mork_borg", 42)
    for center in [12.7, 25.4, 38.1]:
        points = np.array([[x, 6.35, 6.9] for x in np.linspace(center - 1.5, center + 1.5, 61)])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            inside = mesh.contains(points)
        assert not inside.all(), f"missing flagstone channel near x={center}"


def test_mork_borg_seed_changes_decoration_but_not_interface(model_mesh):
    first = model_mesh("e_floor", "mork_borg", 7)
    second = model_mesh("e_floor", "mork_borg", 8)

    assert first.volume != pytest.approx(second.volume, abs=0.001)
    assert connector_signature(first, 6.0) == connector_signature(second, 6.0)


@pytest.mark.parametrize("genre", ["plain", "mork_borg", "cyberpunk", "expanse"])
def test_representative_assembly_is_watertight_and_dimensioned(model_mesh, genre):
    assembly = model_mesh("assembly", genre)

    assert assembly.is_watertight
    assert assembly.is_winding_consistent
    assert assembly.volume > 0
    assert assembly.extents == pytest.approx((113.1381, 114.3, 32.4), abs=0.03)
