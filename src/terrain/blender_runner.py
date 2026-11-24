"""Executed inside Blender, not the terrain Python environment."""


def main():
    import runpy
    import sys
    from pathlib import Path

    import bpy

    script, output = map(Path, sys.argv[sys.argv.index("--") + 1 :])
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 0.001
    runpy.run_path(str(script), run_name="__main__")
    # The modelling contract uses one coordinate unit per millimetre.
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 0.001
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    meshes = [obj for obj in scene.objects if obj.type == "MESH" and not obj.hide_render]
    if not meshes:
        raise ValueError("The modelling script produced no mesh objects")
    for obj in meshes:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "model.blend"))
    bpy.ops.wm.stl_export(
        filepath=str(output / "model.stl"),
        export_selected_objects=True,
        apply_modifiers=True,
        global_scale=1.0,
        use_scene_unit=False,
        forward_axis="Y",
        up_axis="Z",
    )


if __name__ == "__main__":
    main()
