include <../../src/core/parts.scad>

openlock_doorway("plain", 42);
translate([TILE / 2, WALL_BASE / 2, FLOOR_HEIGHT + 0.1]) cylinder(d = 32, h = 2, $fn = 96);
