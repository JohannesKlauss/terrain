import pytest
import trimesh
from conftest import OFFICIAL, assert_single_printable_solid


def test_plain_e_floor_preserves_official_mesh_contract(model_mesh):
    generated = model_mesh("e_floor")
    official = trimesh.load_mesh(OFFICIAL / "E-TRP-v7.6.stl", process=True)

    assert_single_printable_solid(generated, (50.8, 50.8, 7.0))
    assert generated.bounds == pytest.approx(official.bounds, abs=0.02)
    assert generated.volume == pytest.approx(official.volume, abs=0.05)
    assert (generated.area_faces <= 1e-10).sum() == (official.area_faces <= 1e-10).sum()


def test_plain_clip_preserves_official_mesh_contract(model_mesh):
    generated = model_mesh("clip")
    official = trimesh.load_mesh(OFFICIAL / "OpenLOCK-Clip-v5.4.stl", process=True)

    assert_single_printable_solid(generated, (13.2, 19.5, 3.5))
    assert generated.bounds == pytest.approx(official.bounds, abs=0.002)
    assert generated.volume == pytest.approx(official.volume, abs=0.01)


def test_coupon_contains_two_cropped_port_stubs_and_separate_clip(model_mesh):
    coupon = model_mesh("coupon")
    components = coupon.split(only_watertight=False)

    assert coupon.is_watertight
    assert coupon.is_winding_consistent
    assert coupon.volume > 0
    assert coupon.extents == pytest.approx((40.6, 25.4, 7.0), abs=0.02)
    assert len(components) == 3
    volumes = sorted(component.volume for component in components)
    assert volumes[0] == pytest.approx(503.7784, abs=0.01)
    assert volumes[1] > volumes[0]
