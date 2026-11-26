"""Fixed synthetic operations for the offline verifier; no user scripts or models."""

import json
import sys
from pathlib import Path

import bpy


def add_asset(identity, asset, mesh, location=(0, 0, 0)):
    obj = bpy.data.objects.new(identity, mesh)
    bpy.context.collection.objects.link(obj)
    obj["component_id"] = identity
    obj["asset_id"] = asset
    obj.location = location
    return obj


def mesh_for(name, vertices, faces):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


def box(name, width, depth, height):
    x, y, z = width / 2, depth / 2, height / 2
    vertices = [(a, b, c) for c in (-z, z) for a, b in [(-x, -y), (x, -y), (x, y), (-x, y)]]
    faces = [(3, 2, 1, 0), (4, 5, 6, 7)]
    for i in range(4):
        j = (i + 1) % 4
        faces.append((i, j, j + 4, i + 4))
    return mesh_for(name, vertices, faces)


def frame():
    outer = [(-12, 0), (12, 0), (12, 22), (-12, 22)]
    aperture = [(-8, 4), (8, 4), (8, 18), (-8, 18)]
    vertices = [(x, y, z) for y in (-2, 2) for x, z in outer + aperture]
    faces = []
    for i in range(4):
        j = (i + 1) % 4
        front = (i, j, j + 4, i + 4)
        faces.extend([front, tuple(k + 8 for k in reversed(front)), (j, i, i + 8, j + 8)])
        faces.append((i + 4, j + 4, j + 12, i + 12))
    return mesh_for("frame", vertices, faces)


def create(grid):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    settings = bpy.context.scene.unit_settings
    settings.system = "METRIC"
    settings.scale_length = 0.001
    add_asset("frame", "frame", frame())
    add_asset("figure.body", "body", box("body", 6, 3, 10), (0, 0, 11))
    hand = box("hand", 2, 2, 2)
    add_asset("figure.hand-left", "hand", hand, (-5, 0, 12))
    add_asset("figure.hand-right", "hand", hand, (5, 0, 12))
    add_asset("context.plinth", "plinth", box("plinth", 28, 10, 2), (0, 0, -1))
    block = box("block", 9, 9, 6)
    for x in range(grid):
        for y in range(grid):
            add_asset(f"context.block-{x:02}-{y:02}", "block", block, (22 + x * 14, y * 14, 3))
    bpy.ops.wm.save_as_mainfile(filepath=str(Path("baseline.blend").resolve()))


def stage_candidate(sealed):
    # The same candidate worker must be unable to rewrite any sealed baseline input.
    for filename in ("baseline.blend", "baseline.json", "baseline-frame.stl", "scope.json"):
        try:
            with (sealed / filename).open("ab"):
                raise RuntimeError(f"sealed input was writable: {filename}")
        except PermissionError:
            pass
    print("M0_BASELINE_REWRITE_DENIED", flush=True)
    # A known geometry delta to exercise staging, not a response to the reference.
    for vertex in bpy.data.objects["frame"].data.vertices:
        if vertex.co.z == 22:
            vertex.co.z = 23
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=str(Path("candidate.blend").resolve()))


def inspect(name):
    bpy.context.view_layer.update()
    scene = bpy.context.scene
    assert scene.unit_settings.system == "METRIC"
    assert abs(scene.unit_settings.scale_length - 0.001) <= 1e-9
    depsgraph = bpy.context.evaluated_depsgraph_get()
    objects = []
    for obj in sorted(scene.objects, key=lambda item: item["component_id"]):
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            mesh.calc_loop_triangles()
            objects.append(
                {
                    "id": obj["component_id"],
                    "asset": obj["asset_id"],
                    "transform": [list(row) for row in evaluated.matrix_world],
                    "vertices": [list(evaluated.matrix_world @ v.co) for v in mesh.vertices],
                    "triangles": [list(face.vertices) for face in mesh.loop_triangles],
                }
            )
        finally:
            evaluated.to_mesh_clear()
    Path(f"{name}.json").write_text(
        json.dumps(objects, separators=(",", ":"), allow_nan=False) + "\n", encoding="utf-8"
    )
    bpy.ops.object.select_all(action="DESELECT")
    bpy.data.objects["frame"].select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects["frame"]
    bpy.ops.wm.stl_export(
        filepath=str(Path(f"{name}-frame.stl").resolve()),
        export_selected_objects=True,
        apply_modifiers=True,
        global_scale=1.0,
        use_scene_unit=False,
        forward_axis="Y",
        up_axis="Z",
    )


if __name__ == "__main__":
    match sys.argv[sys.argv.index("--") + 1 :]:
        case ["create", grid] if 1 <= int(grid) <= 16:
            create(int(grid))
        case ["stage", sealed]:
            stage_candidate(Path(sealed))
        case ["inspect", "baseline" | "candidate" as name]:
            inspect(name)
        case _:
            raise SystemExit("Unsupported fixture operation")
