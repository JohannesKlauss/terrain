from pathlib import Path


def test_public_model_parameters_do_not_shadow_mcp_wrapped_inputs():
    source = (Path(__file__).parents[1] / "src" / "terrain.scad").read_text()

    assert "module terrain_model(part_id, genre_id, layout_seed)" in source
    assert 'is_undef(part) ? "e_floor" : part' in source
    assert 'is_undef(genre) ? "plain" : genre' in source
    assert "is_undef(seed) ? 42 : seed" in source
    assert '\npart = "e_floor";' not in source
    assert '\ngenre = "plain";' not in source
    assert "\nseed = 42;" not in source
