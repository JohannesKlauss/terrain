include <core/parts.scad>

module terrain_model(part_id, genre_id, layout_seed) {
    assert(valid_genre(genre_id), str("Unknown genre: ", genre_id));
    if (part_id == "e_floor") {
        openlock_floor(genre_id, layout_seed);
    } else if (part_id == "a_wall") {
        openlock_a_wall(genre_id, layout_seed);
    } else if (part_id == "doorway") {
        openlock_doorway(genre_id, layout_seed);
    } else if (part_id == "l_corner") {
        openlock_l_corner(genre_id, layout_seed);
    } else if (part_id == "assembly") {
        mvp_assembly(genre_id, layout_seed);
    } else if (part_id == "clip") {
        openlock_clip();
    } else if (part_id == "coupon") {
        connector_coupon();
    } else {
        assert(false, str("Unknown part: ", part_id));
    }
}

terrain_model(
    is_undef(part) ? "e_floor" : part,
    is_undef(genre) ? "plain" : genre,
    is_undef(seed) ? 42 : seed
);
