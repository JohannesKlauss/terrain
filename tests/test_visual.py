import numpy as np
import pytest
from PIL import Image

from terrain.visual import render_source


@pytest.mark.parametrize("top_height", [5, 75, 750])
def test_top_and_underside_show_the_correct_side_of_asymmetric_geometry(tmp_path, top_height):
    source = tmp_path / "direction.scad"
    source.write_text(
        'color("blue") cube([20,20,10], center=true);\n'
        f'color("red") translate([0,0,{top_height}]) cube([10,10,2], center=true);\n'
    )
    centre_colors = {}
    for view in ("top", "underside"):
        output = tmp_path / f"{view}.png"
        render_source(source, output, view)
        pixels = np.asarray(Image.open(output).convert("RGB"), dtype=int)
        # Test which surface occludes the centre, not its screen area: view-all
        # legitimately zooms out on a very tall, narrow object.
        centre_colors[view] = pixels[pixels.shape[0] // 2, pixels.shape[1] // 2]
    assert centre_colors["top"][0] > centre_colors["top"][2] + 50
    assert centre_colors["underside"][2] > centre_colors["underside"][0] + 50
