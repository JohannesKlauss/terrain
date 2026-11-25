"""Editable rigid-body scenes referencing immutable library assets."""

import csv
import json
import os
from collections import Counter
from pathlib import Path

import numpy as np
import trimesh

from terrain.library import catalog_roots, load_catalog, read_json, sha256, source_path, write_json
from terrain.staged import guard_scene, scene_operation
from terrain.visual import CAMERAS, label_custom_preview, preview_source, render_source


def init_scene(path, catalog, name, brief):
    path = Path(path).resolve()
    if path.exists():
        raise ValueError(f"Scene already exists: {path}")
    if catalog is not None:
        load_catalog(catalog)
    write_json(
        path,
        {
            "schema_version": 1,
            "name": name,
            "brief": brief,
            "catalog": os.path.relpath(Path(catalog).resolve(), path.parent) if catalog else None,
            "art_direction": {
                "mood": "",
                "focal_point": "",
                "composition": "",
                "alternatives": [],
                "missing_assets": [],
            },
            "placements": [],
        },
    )
    return {"scene": path}


def scene_catalog(path, scene):
    if scene.get("schema_version") != 1 or not isinstance(scene.get("placements"), list):
        raise ValueError("Unsupported scene manifest")
    parent = Path(path).resolve().parent
    catalog = (
        load_catalog((parent / scene["catalog"]).resolve())
        if scene.get("catalog")
        else {"schema_version": 1, "root": None, "assets": []}
    )
    custom = scene.get("custom_models", {})
    if not isinstance(custom, dict):
        raise ValueError("custom_models must map draft IDs to manifest paths")
    for identity, reference in custom.items():
        from terrain.custom import draft_asset

        asset = draft_asset(parent / reference)
        if asset["id"] != identity:
            raise ValueError(f"Custom draft manifest changed since placement: {identity}")
        if any(item["id"] == identity for item in catalog["assets"]):
            raise ValueError(f"Duplicate custom asset: {identity}")
        catalog["assets"].append(asset)
    return catalog


def vector(value, name):
    if (
        not isinstance(value, (tuple, list))
        or len(value) != 3
        or any(type(n) not in (int, float) for n in value)
        or not np.isfinite(value).all()
    ):
        raise ValueError(f"{name} must contain three finite numbers")
    return np.asarray(value, dtype=float)


def placement_matrix(placement, asset):
    allowed = {
        "id",
        "asset",
        "source_sha256",
        "position_mm",
        "rotation_deg",
        "anchor",
        "role",
        "note",
    }
    if set(placement) - allowed:
        raise ValueError(f"Unsupported placement fields (no scaling): {set(placement) - allowed}")
    if placement.get("anchor", "bottom_center") not in ("bottom_center", "source"):
        raise ValueError("anchor must be bottom_center or source")
    position = vector(placement["position_mm"], "position_mm")
    rotation = vector(placement.get("rotation_deg", [0, 0, 0]), "rotation_deg")
    matrix = trimesh.transformations.euler_matrix(*np.radians(rotation), axes="sxyz")
    if placement.get("anchor", "bottom_center") == "bottom_center":
        bounds = np.asarray(asset["bounds_mm"])
        anchor = np.array([*bounds[:, :2].mean(axis=0), bounds[0, 2]])
        matrix[:3, 3] = position - matrix[:3, :3] @ anchor
    else:
        matrix[:3, 3] = position
    return matrix


@scene_operation
def add_placement(path, asset_id, placement_id, position, rotation=(0, 0, 0), role="architecture"):
    guard_scene(path)
    scene = read_json(path)
    catalog = scene_catalog(path, scene)
    if any(p["id"] == placement_id for p in scene["placements"]):
        raise ValueError(f"duplicate placement id: {placement_id}")
    asset = next((a for a in catalog["assets"] if a["id"] == asset_id), None)
    if not asset or asset.get("error"):
        raise ValueError(f"Unknown or unreadable asset: {asset_id}")
    placement = {
        "id": placement_id,
        "asset": asset_id,
        "source_sha256": asset["sha256"],
        "position_mm": list(position),
        "rotation_deg": list(rotation),
        "anchor": "bottom_center",
        "role": role,
    }
    placement_matrix(placement, asset)
    scene["placements"].append(placement)
    write_json(path, scene)
    return {"scene": Path(path), "placement": placement}


@scene_operation
def add_custom_placement(
    path, manifest, placement_id, position, rotation=(0, 0, 0), role="architecture"
):
    from terrain.custom import draft_asset

    guard_scene(path)

    path, manifest = Path(path).resolve(), Path(manifest).resolve()
    asset = draft_asset(manifest)
    scene = read_json(path)
    catalog = scene_catalog(path, scene)
    if any(manifest.is_relative_to(root) for root in catalog_roots(catalog).values()):
        raise ValueError("Unindexed custom drafts must stay outside indexed library roots")
    if any(p["id"] == placement_id for p in scene["placements"]):
        raise ValueError(f"duplicate placement id: {placement_id}")
    placement = {
        "id": placement_id,
        "asset": asset["id"],
        "source_sha256": asset["sha256"],
        "position_mm": list(position),
        "rotation_deg": list(rotation),
        "anchor": "bottom_center",
        "role": role,
    }
    placement_matrix(placement, asset)
    scene.setdefault("custom_models", {})[asset["id"]] = os.path.relpath(manifest, path.parent)
    scene["placements"].append(placement)
    write_json(path, scene)
    return {"scene": path, "placement": placement, "library_status": "custom_unindexed"}


def resolve_placements(path):
    scene = read_json(path)
    catalog = scene_catalog(path, scene)
    assets = {asset["id"]: asset for asset in catalog["assets"]}
    if not scene["placements"]:
        raise ValueError("Scene has no placements")
    seen, verified, resolved = set(), set(), []
    for placement in scene["placements"]:
        identity = placement.get("id")
        if not isinstance(identity, str) or not identity:
            raise ValueError("Each placement needs a nonempty id")
        if identity in seen:
            raise ValueError(f"duplicate placement id: {identity}")
        seen.add(identity)
        asset = assets.get(placement["asset"])
        if not asset or asset.get("error"):
            raise ValueError(f"Unknown or unreadable asset: {placement['asset']}")
        if placement.get("source_sha256") != asset["sha256"]:
            raise ValueError(f"Source changed since placement was authored: {identity}")
        if asset["id"] not in verified:
            if sha256(source_path(catalog, asset)) != asset["sha256"]:
                raise ValueError(f"Source changed since indexing: {asset['id']}")
            verified.add(asset["id"])
        matrix = placement_matrix(placement, asset)
        corners = trimesh.bounds.corners(np.asarray(asset["bounds_mm"]))
        transformed = trimesh.transform_points(corners, matrix)
        resolved.append(
            (
                placement,
                asset,
                matrix,
                np.array(
                    [
                        transformed.min(axis=0),
                        transformed.max(axis=0),
                    ]
                ),
            )
        )
    return scene, catalog, resolved


@scene_operation
def assemble_scene(path, output_dir, preview=False, openscad="openscad", views=("iso", "top")):
    guard_scene(path)
    if not views or any(view not in CAMERAS for view in views):
        raise ValueError(f"Unknown scene preview views: {views}")
    scene, catalog, resolved = resolve_placements(path)
    output_dir = Path(output_dir).resolve()
    inputs = {Path(path).resolve()}
    if scene.get("catalog"):
        inputs.add((Path(path).resolve().parent / scene["catalog"]).resolve())
    for asset in catalog["assets"]:
        if asset.get("draft_manifest"):
            inputs.update(
                Path(asset["draft_manifest"]).parent / name
                for name in ("draft.json", "model.stl", "model.blend", "build.py")
            )
    if catalog.get("metadata"):
        inputs.add(Path(catalog["metadata"]).resolve())
    outputs = {
        output_dir / name
        for name in (
            "assembly.scad",
            "report.json",
            "print-list.csv",
            "assembly.md",
            *(f"{view}.png" for view in views),
        )
    }
    if inputs & outputs or any(
        output_dir.is_relative_to(root) for root in catalog_roots(catalog).values()
    ):
        raise ValueError("Assembly output could overwrite inputs; use a separate build directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    source = output_dir / "assembly.scad"
    lines = ["// PRIVATE inspection-only assembly. Do not export merged production meshes."]
    sources = {}
    for _placement, asset, matrix, _ in resolved:
        if asset["id"] not in sources:
            sources[asset["id"]] = preview_source(catalog, asset, output_dir / "cache")
        lines.append(
            f"multmatrix({json.dumps(matrix.tolist())}) "
            + ("color([0.78, 0.48, 0.91]) " if asset.get("draft_manifest") else "")
            + f"import({json.dumps(str(sources[asset['id']]), ensure_ascii=False)});"
        )
    source.write_text("\n".join(lines) + "\n")
    counts = Counter(asset["id"] for _, asset, _, _ in resolved)
    unique = {asset["id"]: asset for _, asset, _, _ in resolved}
    print_list, custom_models = [], []
    for asset_id, count in counts.items():
        asset = unique[asset_id]
        if asset.get("library_status") == "custom_unindexed":
            custom_models.append(
                {
                    "asset": asset_id,
                    "name": asset["name"],
                    "required": count,
                    "library_status": "custom_unindexed",
                    "approval": "pending",
                    "draft_manifest": asset["draft_manifest"],
                    "review_sha256": sha256(asset["draft_manifest"]),
                    "sha256": asset["sha256"],
                }
            )
            continue
        printed = (
            scene.get("iteration", {}).get("printed_inventory", {}).get(asset_id, asset["printed"])
        )
        if printed is not None and (type(printed) is not int or printed < 0):
            raise ValueError(f"Invalid printed inventory: {asset_id}")
        print_list.append(
            {
                "asset": asset_id,
                "source": str(source_path(catalog, asset)),
                "sha256": asset["sha256"],
                "required": count,
                "already_printed": printed,
                "to_print": None if printed is None else max(0, count - printed),
                "license": asset["license"],
            }
        )
    overlaps = []
    for i, (first, _, _, first_bounds) in enumerate(resolved):
        for second, _, _, second_bounds in resolved[i + 1 :]:
            overlap = np.minimum(first_bounds[1], second_bounds[1]) - np.maximum(
                first_bounds[0], second_bounds[0]
            )
            if (overlap > 0.01).all():
                overlaps.append([first["id"], second["id"]])
    all_bounds = np.array([bounds for *_, bounds in resolved])
    bounds = np.array([all_bounds[:, 0].min(axis=0), all_bounds[:, 1].max(axis=0)])
    warnings = [
        "Inspection only, not a production plate; print unchanged original source files.",
        "AABB overlap is a broad-phase warning, not a collision or connector-fit certificate.",
        "Units, connector alignment, stability, miniature clearance and slicer review are pending.",
        "Unknown printed inventory stays null; owning digital files does not imply printed stock.",
        "Per-asset licenses apply; this assembly has no blanket redistribution license.",
    ]
    if custom_models:
        warnings.append(
            "Purple custom models are unindexed drafts awaiting explicit library approval; "
            "they are excluded from the printing list."
        )
    previews = []
    if preview:
        for view in views:
            destination = output_dir / f"{view}.png"
            render_source(source, destination, view, openscad, size=(1600, 1200))
            if custom_models:
                label_custom_preview(
                    destination,
                    [p["id"] for p, asset, _, _ in resolved if asset.get("draft_manifest")],
                )
            previews.append(destination)
    report_path = output_dir / "report.json"
    write_json(
        report_path,
        {
            "name": scene["name"],
            "brief": scene["brief"],
            "art_direction": scene.get("art_direction", {}),
            "encounter": scene.get("encounter", {}),
            "iteration": scene.get("iteration", {}),
            "placements": [
                {
                    **placement,
                    "world_aabb_mm": bounds.tolist(),
                    "library_status": asset.get("library_status", "indexed"),
                }
                for placement, asset, _, bounds in resolved
            ],
            "bounds_mm": bounds.tolist(),
            "bounds_method": "Conservative transformed source AABBs, not exact mesh bounds",
            "extents_mm": np.ptp(bounds, axis=0).tolist(),
            "print_list": print_list,
            "custom_models": custom_models,
            "aabb_overlaps": overlaps,
            "warnings": warnings,
            "artistic_review": "pending",
            "connector_validation": "pending",
            "physical_validation": "pending",
            "previews": list(map(str, previews)),
        },
    )
    print_path = output_dir / "print-list.csv"
    with print_path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["asset", "required", "already_printed", "to_print", "source", "license"])
        for item in print_list:
            writer.writerow(
                [
                    item["asset"],
                    item["required"],
                    item["already_printed"],
                    item["to_print"],
                    item["source"],
                    item["license"]["name"],
                ]
            )
    instructions = output_dir / "assembly.md"
    instructions.write_text(
        f"# {scene['name']}\n\n{scene['brief']}\n\n"
        "Private assembly preview only. Coordinates are millimetres; rotations are XYZ degrees.\n"
        "bottom_center anchors the original mesh at its XY bounds centre and lowest Z, "
        "then rotates and translates it. No scaling, fusion or source editing occurs.\n\n"
        + "\n".join(
            f"- `{p['id']}`: `{p['asset']}`, position {p['position_mm']}, "
            f"rotation {p.get('rotation_deg', [0, 0, 0])}, role {p.get('role', '')}."
            for p, *_ in resolved
        )
        + "\n\n## Unresolved checks\n\n"
        + "\n".join(f"- {w}" for w in warnings)
        + "\n"
    )
    return {
        "source": source,
        "report": report_path,
        "print_list": print_path,
        "instructions": instructions,
        "previews": previews,
    }
