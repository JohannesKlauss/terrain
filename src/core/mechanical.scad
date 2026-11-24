GRID = 25.4;
TILE = 50.8;
FLOOR_HEIGHT = 7;
WALL_BASE = 12.7;
LOW_WALL_HEIGHT = 25.4;
CLIP_CENTER_X = 12.7;
COUPON_LAYOUT_GAP = 15.2;
ASSEMBLY_GAP = 0.01;
EPSILON = 0.01;

module openlock_e_floor() {
    import("../../assets/openlock/official/E-TRP-v7.6.stl");
}

module openlock_clip() {
    import("../../assets/openlock/official/OpenLOCK-Clip-v5.4.stl");
}

module openlock_clip_at(x = 0, y = 0, z = 0) {
    translate([x - CLIP_CENTER_X, y, z]) openlock_clip();
}

module coupon_port_stub(offset = 0, crop_x = TILE - WALL_BASE) {
    intersection() {
        translate([offset, 0, 0]) openlock_e_floor();
        translate([crop_x, WALL_BASE, -EPSILON])
            cube([WALL_BASE, GRID, FLOOR_HEIGHT + 2 * EPSILON]);
    }
}

module connector_coupon() {
    right_offset = TILE + COUPON_LAYOUT_GAP;
    clip_center = TILE + COUPON_LAYOUT_GAP / 2;
    coupon_port_stub();
    coupon_port_stub(right_offset, right_offset);
    translate([0, 0, -1.75]) openlock_clip_at(clip_center, GRID);
}
