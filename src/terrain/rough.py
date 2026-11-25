"""Conservative play evidence from the actual transformed mesh triangles."""

from collections import Counter

import numpy as np
import trimesh
from shapely.geometry import GeometryCollection, LineString, Point, Polygon
from shapely.ops import unary_union

from terrain.library import read_mesh, source_path


def projected_mesh(mesh, matrix):
    """Union triangle projections; conservative in XY even for overhanging geometry."""
    vertices = trimesh.transform_points(mesh.vertices, matrix)
    triangles = vertices[mesh.faces][:, :, :2]
    faces = []
    for triangle in triangles:
        polygon = Polygon(triangle)
        if polygon.area > 1e-10:
            faces.append(polygon)
    return unary_union(faces) if faces else GeometryCollection()


def evidence(scene, catalog, resolved, layout):
    """Return measured sketch evidence, not a claim of physical or visual approval."""
    plan = layout["plan"]
    option = next(o for o in plan["options"] if o["id"] == plan["selected_option"])
    spec = scene.get("rough")
    if not isinstance(spec, dict):
        raise ValueError("Staged rough scene needs a rough specification")
    bindings = spec.get("bindings")
    if not isinstance(bindings, dict):
        raise ValueError("rough.bindings must map feature IDs to placement IDs")
    tolerance = spec.get("tolerance_mm")
    if type(tolerance) not in (int, float) or not np.isfinite(tolerance) or tolerance < 0:
        raise ValueError("rough.tolerance_mm must be a nonnegative finite number")
    band = spec.get("clearance_height_mm")
    if type(band) not in (int, float) or not np.isfinite(band) or band <= 0:
        raise ValueError("rough.clearance_height_mm must be positive")
    gaps = spec.get("gaps")
    sourcing = spec.get("sourcing")
    proxies = spec.get("proxies")
    notes = spec.get("physical_unknowns")
    if not all(isinstance(v, list) for v in (gaps, sourcing, proxies, notes)):
        raise ValueError("rough gaps, sourcing, proxies and physical_unknowns must be lists")
    for gap in gaps:
        if (
            not isinstance(gap, dict)
            or any(
                not isinstance(gap.get(k), str) or not gap[k].strip()
                for k in (
                    "role",
                    "envelope_interface",
                    "substitutes",
                    "decision_deadline",
                    "status",
                )
            )
            or type(gap.get("quantity")) is not int
            or gap["quantity"] < 1
        ):
            raise ValueError(
                "Each gap needs role, envelope/interface, quantity, substitutes, "
                "deadline and status"
            )
    for item in sourcing:
        if not isinstance(item, dict) or any(
            not isinstance(item.get(k), str) or not item[k].strip()
            for k in (
                "vendor_link",
                "price_date",
                "contents",
                "size_interface_evidence",
                "license",
                "unknowns",
                "recommendation",
                "fallback",
            )
        ):
            raise ValueError("Each sourcing candidate needs the complete read-only listing record")
    if any(not isinstance(v, str) or not v.strip() for v in notes + proxies):
        raise ValueError("Proxy IDs and physical unknowns must be text")
    entries = {p["id"]: (p, asset, matrix, bounds) for p, asset, matrix, bounds in resolved}
    if len(set(proxies)) != len(proxies) or any(p not in entries for p in proxies):
        raise ValueError("Proxy IDs must name unique placements")
    features = {f["id"]: f for f in option["features"]}
    if any(fid not in features or pid not in entries for fid, pid in bindings.items()):
        raise ValueError("Rough bindings must name a current feature and placement")
    actual_bounds = {}
    projected = {}
    for placement, asset, matrix, _ in resolved:
        mesh = read_mesh(source_path(catalog, asset))
        points = trimesh.transform_points(mesh.vertices, matrix)
        actual_bounds[placement["id"]] = np.array([points.min(axis=0), points.max(axis=0)])
        projected[placement["id"]] = projected_mesh(mesh, matrix)
    material = []
    for feature_id, placement_id in bindings.items():
        feature = features[feature_id]
        x, y = feature["at"]
        w, h = feature["size"]
        bounds = actual_bounds[placement_id]
        if (
            bounds[0, 0] < x - tolerance
            or bounds[0, 1] < y - tolerance
            or bounds[1, 0] > x + w + tolerance
            or bounds[1, 1] > y + h + tolerance
        ):
            material.append(
                {
                    "feature": feature_id,
                    "placement": placement_id,
                    "reason": "Actual placement exceeds the approved feature envelope",
                    "approved_mm": [x, y, x + w, y + h],
                    "actual_mm": [*bounds[0, :2].tolist(), *bounds[1, :2].tolist()],
                }
            )
        if (
            feature["kind"] in ("height", "stairs")
            and "height_mm" in feature
            and abs(bounds[1, 2] - feature["height_mm"]) > tolerance
        ):
            material.append(
                {
                    "feature": feature_id,
                    "placement": placement_id,
                    "reason": "Actual height differs from the approved height",
                    "approved_mm": feature["height_mm"],
                    "actual_mm": float(bounds[1, 2]),
                }
            )
    required = {
        f["id"]
        for f in option["features"]
        if f["kind"] in ("cover", "interaction", "height", "stairs")
    }
    unresolved = sorted(required - bindings.keys())
    unresolved += sorted(
        f["id"] + " height not specified in 2D"
        for f in option["features"]
        if f["kind"] in ("height", "stairs") and "height_mm" not in f
    )
    radius = (
        max(plan["dimensions"].get("base_diameters_mm", [plan["dimensions"]["base_diameter_mm"]]))
        / 2
    )
    shapes = {}
    for placement, _, _, _ in resolved:
        bounds = actual_bounds[placement["id"]]
        # A floor entirely below this band does not block a moving miniature.
        if bounds[1, 2] <= tolerance or bounds[0, 2] >= band:
            continue
        shapes[placement["id"]] = projected[placement["id"]]
    occupied = spec.get("occupied_bases", [])
    if not isinstance(occupied, list):
        raise ValueError("occupied_bases must be a list")
    occupied_shapes = []
    for item in occupied:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("at"), list)
            or (
                len(item["at"]) != 2
                or any(type(n) not in (int, float) or not np.isfinite(n) for n in item["at"])
            )
            or type(item.get("diameter_mm")) not in (int, float)
            or not (np.isfinite(item["diameter_mm"]) and item["diameter_mm"] > 0)
        ):
            raise ValueError("Occupied bases need finite XY and a positive diameter_mm")
        occupied_shapes.append(Point(item["at"]).buffer(item["diameter_mm"] / 2))
    routes = []
    for route in option["routes"]:
        centre = LineString(route["points"])
        swept = centre.buffer(radius + tolerance, cap_style="round", join_style="round")
        hits = [pid for pid, shape in shapes.items() if swept.intersects(shape)]
        occupied_hits = [
            index for index, shape in enumerate(occupied_shapes) if swept.intersects(shape)
        ]
        routes.append(
            {
                "id": route["id"],
                "status": "blocked" if hits else "clear",
                "blocking_placements": hits,
                "occupied_base_intersections": occupied_hits,
                "base_diameter_mm": radius * 2,
                "tolerance_mm": tolerance,
                "method": "Union of transformed triangle XY projections against swept base; "
                "conservative over the stated height band, not exact collision.",
            }
        )
    interactions = []
    for feature in option["features"]:
        if feature["kind"] != "interaction":
            continue
        point = Point(feature["approach_at"])
        mesh_distances = {pid: point.distance(shape) for pid, shape in shapes.items()}
        occupied_distances = [point.distance(shape) for shape in occupied_shapes]
        closest = min([*mesh_distances.values(), *occupied_distances], default=None)
        interactions.append(
            {
                "feature": feature["id"],
                "approach_at_mm": feature["approach_at"],
                "nearest_projected_obstacle_mm": closest,
                "remaining_after_base_radius_mm": None if closest is None else closest - radius,
                "occupied_base_clearance_mm": min(occupied_distances, default=None),
                "method": "Planar distances from intended base centre to transformed mesh "
                "projections and explicitly positioned occupied bases.",
                "hand_access": "Vertical access and hand size not measured; unverified",
            }
        )
    entry = next(f for f in option["features"] if f["kind"] == "entry")
    ex, ey = entry["at"]
    ew, eh = entry["size"]
    entry_point = (ex + ew / 2, ey + eh / 2)
    sightlines = []
    for feature in option["features"]:
        if feature["kind"] not in ("reveal", "interaction"):
            continue
        x, y = feature["at"]
        w, h = feature["size"]
        line = LineString([entry_point, (x + w / 2, y + h / 2)])
        target = bindings.get(feature["id"])
        hits = [pid for pid, shape in shapes.items() if pid != target and line.intersects(shape)]
        sightlines.append(
            {
                "feature": feature["id"],
                "planar_obstructions": hits,
                "method": "Entry-centre to feature-centre XY projection; "
                "not a 3D sightline verdict",
            }
        )
    footprint = plan["dimensions"]["outer_mm"]
    actual = np.array(list(actual_bounds.values()))
    bounds = [actual[:, 0].min(axis=0), actual[:, 1].max(axis=0)]
    if (bounds[0][:2] < -tolerance).any() or (
        bounds[1][:2] > np.asarray(footprint) + tolerance
    ).any():
        material.append(
            {
                "reason": "Actual scene exceeds approved outer footprint",
                "actual_mm": [bounds[0].tolist(), bounds[1].tolist()],
                "approved_mm": footprint,
            }
        )
    planned = layout["checks"][option["id"]]["routes"]
    for route, previous in zip(routes, planned, strict=True):
        if route["status"] == "blocked" and previous["status"] != "blocked":
            material.append(
                {
                    "reason": "Previously open route is blocked by projected mesh",
                    "route": route["id"],
                    "placements": route["blocking_placements"],
                }
            )
    counts = Counter(
        asset["id"]
        for placement, asset, _, _ in resolved
        if placement["id"] not in proxies and asset.get("library_status") != "custom_unindexed"
    )
    # Stock is recorded from catalog annotations, never inferred from a digital file.
    assets = {asset["id"]: asset for _, asset, _, _ in resolved}
    stock = [
        {
            "asset": identity,
            "required": count,
            "printed": assets[identity].get("printed"),
            "shortfall": None
            if assets[identity].get("printed") is None
            else max(0, count - assets[identity]["printed"]),
        }
        for identity, count in counts.items()
    ]
    return {
        "schema_version": 1,
        "layout_revision": layout["number"],
        "option": option["id"],
        "method": "Transformed triangle XY projection, conservative over clearance band",
        "clearance_height_mm": band,
        "tolerance_mm": tolerance,
        "routes": routes,
        "interaction_clearances": interactions,
        "cover_reveal_projections": sightlines,
        "feature_measurements": {
            fid: {
                "placement": pid,
                "kind": features[fid]["kind"],
                "world_bounds_mm": actual_bounds[pid].tolist(),
                "status": "measured envelope; physical access, sightlines and function unverified",
            }
            for fid, pid in bindings.items()
        },
        "feature_bindings": bindings,
        "unresolved_features": unresolved,
        "material_changes": material,
        "stock": stock,
        "owned_files": [
            {
                "asset": identity,
                "source": str(source_path(catalog, assets[identity])),
                "sha256": assets[identity]["sha256"],
            }
            for identity in counts
        ],
        "unindexed_drafts": [
            placement["id"]
            for placement, asset, _, _ in resolved
            if asset.get("library_status") == "custom_unindexed"
        ],
        "proxy_placements": proxies,
        "gaps": gaps,
        "sourcing_candidates_unavailable": sourcing,
        "physical_unknowns": notes,
        "unverified": [
            "Physical fit, mesh units, stability, stairs, hand access, cover and reveal",
            "Occupied bases are checked only at the explicitly supplied positions; "
            "visual quality requires human review",
            "AABB warnings are not collision evidence; proxies are not visual proof",
        ],
    }
