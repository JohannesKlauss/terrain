include <mechanical.scad>
include <../styles/styles.scad>

DOOR_CLEAR_WIDTH = 38.1;
DOOR_POST_WIDTH = (TILE - DOOR_CLEAR_WIDTH) / 2;
CORNER_SIZE = 11.54;

module openlock_a_wall_template() {
    import("../../assets/openlock/official/A-Wall-Low-TRP-v7.2.stl");
}

module openlock_l_column_template() {
    import("../../assets/openlock/official/Column-L-TRP-v7.5.stl");
}

module openlock_low_l_column() {
    intersection() {
        openlock_l_column_template();
        translate([-EPSILON, -EPSILON, -EPSILON])
            cube([CORNER_SIZE + 2 * EPSILON, CORNER_SIZE + 2 * EPSILON, LOW_WALL_HEIGHT + EPSILON]);
    }
}

module openlock_floor(genre = "plain", seed = 42) {
    if (genre == "plain") openlock_e_floor();
    else difference() {
        openlock_e_floor();
        floor_decoration(genre, seed);
    }
}

module openlock_a_wall(genre = "plain", seed = 42) {
    if (genre == "plain") openlock_a_wall_template();
    else difference() {
        openlock_a_wall_template();
        wall_decoration(genre, seed);
    }
}

module doorway_opening() {
    translate([DOOR_POST_WIDTH, -EPSILON, FLOOR_HEIGHT])
        cube([DOOR_CLEAR_WIDTH, WALL_BASE + 2 * EPSILON, LOW_WALL_HEIGHT - FLOOR_HEIGHT + EPSILON]);
}

module openlock_doorway(genre = "plain", seed = 42) {
    difference() {
        openlock_a_wall_template();
        doorway_opening();
        wall_decoration(genre, seed);
    }
}

module openlock_l_corner(genre = "plain", seed = 42) {
    if (genre == "plain") openlock_low_l_column();
    else difference() {
        openlock_low_l_column();
        column_decoration(genre, seed);
    }
}

module mvp_assembly(genre = "plain", seed = 42) {
    for (x = [0, TILE + ASSEMBLY_GAP], y = [0, TILE + ASSEMBLY_GAP]) {
        translate([x, y, 0]) openlock_floor(genre, seed + x + y);
    }
    translate([0, -WALL_BASE - ASSEMBLY_GAP, FLOOR_HEIGHT + ASSEMBLY_GAP]) openlock_a_wall(genre, seed);
    translate([TILE + ASSEMBLY_GAP, -WALL_BASE - ASSEMBLY_GAP, FLOOR_HEIGHT + ASSEMBLY_GAP]) openlock_doorway(genre, seed);
    translate([-CORNER_SIZE - ASSEMBLY_GAP, -WALL_BASE - ASSEMBLY_GAP, FLOOR_HEIGHT + ASSEMBLY_GAP]) openlock_l_corner(genre, seed);
}
