DECOR_DEPTH = 0.35;
WALL_FRONT = 2.35;
WALL_BACK = 10.35;
$fn = 48;

function valid_genre(genre) = genre == "plain" || genre == "mork_borg" || genre == "cyberpunk" || genre == "expanse";

module floor_cut(size, position) {
    translate([position[0], position[1], FLOOR_HEIGHT - DECOR_DEPTH])
        cube([size[0], size[1], DECOR_DEPTH + EPSILON]);
}

module mork_borg_floor(seed) {
    widths = rands(0.5, 1.1, 3, seed);
    offsets = rands(-1.2, 1.2, 6, seed + 1);
    for (i = [0:2]) {
        floor_cut([widths[i], TILE - 4], [TILE * (i + 1) / 4 + offsets[i], 2]);
        floor_cut([TILE - 4, widths[i]], [2, TILE * (i + 1) / 4 + offsets[i + 3]]);
    }
    translate([TILE / 2, TILE / 2, FLOOR_HEIGHT - DECOR_DEPTH])
        difference() {
            cylinder(r = 6, h = DECOR_DEPTH + EPSILON);
            translate([0, 0, -EPSILON]) cylinder(r = 5.35, h = DECOR_DEPTH + 3 * EPSILON);
        }
}

module cyberpunk_floor(seed) {
    offset = rands(-1.5, 1.5, 1, seed)[0];
    for (y = [7, 9, TILE - 9]) floor_cut([TILE - 8, 0.6], [4, y]);
    for (x = [15, 31]) floor_cut([0.55, 16], [x + offset, 17.4]);
    for (y = [17.4, 32.85]) floor_cut([16, 0.55], [15 + offset, y]);
    for (x = [14, 32]) for (y = [16.5, 34]) {
        translate([x + offset, y, FLOOR_HEIGHT - DECOR_DEPTH])
            cylinder(d = 1.6, h = DECOR_DEPTH + EPSILON);
    }
}

module expanse_floor(seed) {
    inset = rands(0, 1, 1, seed)[0];
    floor_cut([0.55, TILE - 8], [TILE / 2, 4]);
    for (y = [GRID, TILE - GRID]) floor_cut([TILE - 8, 0.55], [4, y]);
    for (x = [6, TILE - 8]) floor_cut([2, TILE - 16], [x, 8]);
    for (y = [6 + inset, TILE - 8 + inset]) floor_cut([TILE - 16, 1], [8, y]);
}

module floor_decoration(genre, seed) {
    if (genre == "mork_borg") mork_borg_floor(seed);
    else if (genre == "cyberpunk") cyberpunk_floor(seed);
    else if (genre == "expanse") expanse_floor(seed);
}

module wall_groove(x, z, width, height, back = false) {
    if (back) translate([x, WALL_BACK - DECOR_DEPTH, z]) cube([width, DECOR_DEPTH + EPSILON, height]);
    else translate([x, WALL_FRONT - EPSILON, z]) cube([width, DECOR_DEPTH + EPSILON, height]);
}

module wall_grooves(x, z, width, height) {
    for (back = [false, true]) wall_groove(x, z, width, height, back);
}

module mork_borg_wall(seed) {
    shifts = rands(-1, 1, 4, seed);
    for (row = [0:3]) {
        z = 9.5 + row * 3.6;
        wall_grooves(1, z, TILE - 2, 0.55);
        for (column = [0:3]) {
            x = 6.35 + column * TILE / 4 + (row % 2) * 8 + shifts[row];
            wall_grooves(x, z, 0.55, 3.6);
        }
    }
}

module cyberpunk_wall(seed) {
    panel_x = 17 + rands(-1, 1, 1, seed)[0];
    for (z = [10, 12]) wall_grooves(2, z, TILE - 4, 0.65);
    for (x = [panel_x, panel_x + 16]) wall_grooves(x, 14, 0.55, 9);
    for (z = [14, 22.45]) wall_grooves(panel_x, z, 16.55, 0.55);
}

module expanse_wall(seed) {
    for (x = [GRID, TILE / 2, TILE - GRID]) wall_grooves(x, 9, 0.55, 14.5);
    for (z = [9, 16.5, 23]) wall_grooves(2, z, TILE - 4, 0.55);
}

module wall_decoration(genre, seed) {
    if (genre == "mork_borg") mork_borg_wall(seed);
    else if (genre == "cyberpunk") cyberpunk_wall(seed);
    else if (genre == "expanse") expanse_wall(seed);
}

module column_groove(x, y, z, width, depth, height) {
    translate([x, y, z]) cube([width, depth, height]);
}

module column_decoration(genre, seed) {
    if (genre == "mork_borg") {
        for (z = [11, 16, 21]) {
            column_groove(1.5, -EPSILON, z, 8, DECOR_DEPTH + EPSILON, 0.55);
            column_groove(-EPSILON, 1.5, z, DECOR_DEPTH + EPSILON, 8, 0.55);
        }
    } else if (genre == "cyberpunk") {
        for (z = [10, 12]) {
            column_groove(1.5, -EPSILON, z, 8, DECOR_DEPTH + EPSILON, 0.65);
            column_groove(-EPSILON, 1.5, z, DECOR_DEPTH + EPSILON, 8, 0.65);
        }
        column_groove(5, -EPSILON, 15, 0.55, DECOR_DEPTH + EPSILON, 8);
        column_groove(-EPSILON, 5, 15, DECOR_DEPTH + EPSILON, 8, 0.55);
    } else if (genre == "expanse") {
        for (x = [3, 7]) column_groove(x, -EPSILON, 9, 0.55, DECOR_DEPTH + EPSILON, 14.5);
        for (y = [3, 7]) column_groove(-EPSILON, y, 9, DECOR_DEPTH + EPSILON, 0.55, 14.5);
    }
}
