"""Original Blender modelling example. Coordinates are millimetres, not metres.

This is a standalone plinth, not an OpenLOCK-compatible connector tile.
"""

import bpy

rings = [(25.4, 0), (25.4, 4), (20, 4), (20, 7)]
vertices = [
    (x * half_width, y * half_width, z)
    for half_width, z in rings
    for x, y in [(-1, -1), (1, -1), (1, 1), (-1, 1)]
]
faces = [(3, 2, 1, 0)]
for ring in range(len(rings) - 1):
    lower, upper = ring * 4, (ring + 1) * 4
    for corner in range(4):
        following = (corner + 1) % 4
        faces.append((lower + corner, lower + following, upper + following, upper + corner))
faces.append((12, 13, 14, 15))

mesh = bpy.data.meshes.new("Original stepped plinth")
mesh.from_pydata(vertices, [], faces)
mesh.update()
plinth = bpy.data.objects.new("Stepped plinth", mesh)
bpy.context.collection.objects.link(plinth)
