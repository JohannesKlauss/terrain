import pytest

from terrain.catalog import GENRES, PARTS, ModelSpec, mvp_specs, named_spec


def test_core_catalog_covers_every_genre_without_retired_scene_props():
    specs = mvp_specs(seed=42)
    assert GENRES == ("plain", "mork_borg", "cyberpunk", "expanse")
    assert {(s.part, s.genre) for s in specs if s.part in PARTS} == {
        (part, genre) for part in PARTS for genre in GENRES
    }
    assert {(s.part, s.genre) for s in specs if s.part not in PARTS} == {
        ("clip", "plain"),
        ("coupon", "plain"),
        *(("assembly", genre) for genre in GENRES),
    }
    assert len(specs) == len(set(specs))
    assert all(s.seed == 42 for s in specs)


def test_named_spec_validates_part_and_genre():
    assert named_spec("e_floor", "mork_borg", 9) == ModelSpec("e_floor", "mork_borg", 9)
    with pytest.raises(ValueError, match="unknown part"):
        named_spec("unknown", "plain", 1)
    with pytest.raises(ValueError, match="unknown genre"):
        named_spec("e_floor", "unknown", 1)


def test_retired_vark_demo_is_not_a_supported_generator():
    with pytest.raises(ValueError, match="unknown part"):
        named_spec("main_machine", "plain", 42)
    with pytest.raises(ValueError, match="unknown genre"):
        named_spec("e_floor", "vark_lab", 42)
