"""Top-down, grid-based workshop plans. Dimensions are in millimetres."""

import html
import json
import math
import re
import textwrap
from pathlib import Path

from terrain.library import read_json, sha256


def text(value, name):
    if not isinstance(value, str) or not value.strip() or len(value) > 300:
        raise ValueError(f"{name} must be nonempty text (at most 300 characters)")
    return value


def number(value, name, *, zero=False):
    if (
        type(value) not in (int, float)
        or not math.isfinite(value)
        or (value < 0 if zero else value <= 0)
    ):
        raise ValueError(f"{name} must be a finite {'nonnegative' if zero else 'positive'} number")
    return value


def point(value, name):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{name} must be [x, y]")
    return [number(v, name, zero=True) for v in value]


def identifier(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,20}", value):
        raise ValueError(f"{name} must be a simple identifier of at most 20 characters")
    return value


def check_plan(plan):
    """Validate a plan and return conservative centre-line clearance checks."""
    if not isinstance(plan, dict) or plan.get("schema_version") != 1:
        raise ValueError("Unsupported 2D plan")
    for field in ("changes", "clarified", "pending_decision"):
        text(plan.get(field), field)
    dims = plan.get("dimensions")
    if not isinstance(dims, dict):
        raise ValueError("dimensions must be an object")
    for field in (
        "game_pitch_mm",
        "mini_scale",
        "base_diameter_mm",
        "viewer_ruler_mm",
        "library_pitch_mm",
    ):
        number(dims.get(field), field)
    bases = dims.get("base_diameters_mm", [dims["base_diameter_mm"]])
    if not isinstance(bases, list) or not bases:
        raise ValueError("base_diameters_mm must be a nonempty list")
    for base in bases:
        number(base, "base diameter")
    if dims["base_diameter_mm"] not in bases:
        raise ValueError("The displayed base must be among the expected bases")
    for field in ("confirmed", "assumptions", "physical_unknowns"):
        if not isinstance(dims.get(field), list):
            raise ValueError(f"{field} must be a list")
        for entry in dims[field]:
            text(entry, field)
    width, depth = point(dims.get("outer_mm"), "outer_mm")
    limit_x, limit_y = point(dims.get("footprint_limit_mm"), "footprint_limit_mm")
    if not width or not depth or not limit_x or not limit_y or max(width, depth) > 10000:
        raise ValueError("Invalid outer size or footprint limit")
    grid = dims.get("playable_squares")
    if not isinstance(grid, list) or len(grid) != 2:
        raise ValueError("playable_squares must contain two integers")
    cols, rows = grid
    if (
        type(cols) is not int
        or type(rows) is not int
        or not (1 <= cols <= 100 and 1 <= rows <= 100)
    ):
        raise ValueError("playable_squares must contain two integers from 1 to 100")
    pitch = dims["game_pitch_mm"]
    if cols * pitch > width or rows * pitch > depth:
        raise ValueError("Playable grid exceeds the outer dimensions")
    options = plan.get("options")
    if not isinstance(options, list) or len(options) not in (2, 3):
        raise ValueError("A comparison requires two or three options")
    ids, signatures, checks = set(), set(), {}
    for option in options:
        if not isinstance(option, dict):
            raise ValueError("Option must be an object")
        identity = identifier(option.get("id"), "option id")
        if identity in ids:
            raise ValueError("Option IDs must be unique simple identifiers")
        ids.add(identity)
        if len(text(option.get("title"), "option title")) > 45:
            raise ValueError("Option title must be at most 45 characters")
        text(option.get("intent"), "option intent")
        features = option.get("features")
        routes = option.get("routes")
        if not isinstance(features, list) or not isinstance(routes, list) or not routes:
            raise ValueError("Each option needs features and at least one route")
        kinds, names, obstacles = set(), set(), []
        for f in features:
            if not isinstance(f, dict):
                raise ValueError("Feature must be an object")
            fid = identifier(f.get("id"), "feature id")
            kind = f.get("kind")
            if fid in names or kind not in (
                "entry",
                "reveal",
                "cover",
                "interaction",
                "height",
                "stairs",
            ):
                raise ValueError("Duplicate feature or unsupported feature kind")
            names.add(fid)
            kinds.add(kind)
            text(f.get("label"), "feature label")
            x, y = point(f.get("at"), "feature at")
            w, h = point(f.get("size"), "feature size")
            if not w or not h or x + w > width or y + h > depth:
                raise ValueError(f"Feature {fid} lies outside the outer dimensions")
            if type(f.get("blocks")) is not bool:
                raise ValueError("Each feature needs a boolean blocks value")
            if f["blocks"]:
                obstacles.append((x, y, x + w, y + h))
        if not {"entry", "reveal", "cover", "interaction", "height", "stairs"} <= kinds:
            raise ValueError(
                "Each option needs entry, reveal, cover, interaction, height and stairs"
            )
        if option.get("approach") not in ("alternate", "intentional_choke"):
            raise ValueError("Specify alternate or intentional_choke")
        if option["approach"] == "alternate" and len(routes) < 2:
            raise ValueError("An alternate approach needs at least two routes")
        signature = json.dumps([features, routes], sort_keys=True)
        if signature in signatures:
            raise ValueError("Options must have different geometry")
        signatures.add(signature)
        route_checks = []
        for route in routes:
            if not isinstance(route, dict):
                raise ValueError("Route must be an object")
            rid = identifier(route.get("id"), "route id")
            points = route.get("points")
            if not isinstance(points, list) or len(points) < 2:
                raise ValueError("Route needs at least two points")
            points = [point(p, "route point") for p in points]
            if any(x > width or y > depth for x, y in points):
                raise ValueError("Route point lies outside the outer dimensions")
            declared = number(route.get("width_mm"), "route width")
            clearance = min(width, depth)
            for (x1, y1), (x2, y2) in zip(points, points[1:], strict=False):
                if (x1 == x2) == (y1 == y2):
                    raise ValueError("Routes must use nonzero horizontal or vertical segments")
                clearance = min(
                    clearance,
                    2 * min(x1, x2, width - x1, width - x2, y1, y2, depth - y1, depth - y2),
                )
                if y1 == y2:
                    lo, hi = sorted((x1, x2))
                    for x0, y0, x3, y3 in obstacles:
                        dx = max(x0 - hi, lo - x3, 0)
                        dy = max(y0 - y1, y1 - y3, 0)
                        clearance = min(clearance, 2 * math.hypot(dx, dy))
                else:
                    lo, hi = sorted((y1, y2))
                    for x0, y0, x3, y3 in obstacles:
                        dx = max(x0 - x1, x1 - x3, 0)
                        dy = max(y0 - hi, lo - y3, 0)
                        clearance = min(clearance, 2 * math.hypot(dx, dy))
            available = min(clearance, declared)
            base = max(bases)
            status = (
                "blocked"
                if available < base
                else ("tight" if available < base * 1.25 else "feasible")
            )
            entries = [f for f in features if f["kind"] == "entry"]

            def in_entry(p, entries=entries):
                return any(
                    f["at"][0] <= p[0] <= f["at"][0] + f["size"][0]
                    and f["at"][1] <= p[1] <= f["at"][1] + f["size"][1]
                    for f in entries
                )

            route_checks.append(
                {
                    "id": rid,
                    "available_mm": available,
                    "status": status,
                    "from_entry": in_entry(points[0]) or in_entry(points[-1]),
                }
            )
        checks[identity] = {
            "footprint": "fits" if width <= limit_x and depth <= limit_y else "exceeds",
            "routes": route_checks,
            "interactions": interaction_checks(features, routes, route_checks, max(bases)),
        }
    selected = plan.get("selected_option")
    if selected is not None and (not isinstance(selected, str) or selected not in checks):
        raise ValueError("Selected option is not in this comparison")
    return checks


def interaction_checks(features, routes, route_checks, base):
    """An interaction is reachable only when a route ends at its marked approach point."""
    endpoints = [
        p
        for route, check in zip(routes, route_checks, strict=True)
        if check["status"] != "blocked" and check["from_entry"]
        for p in (route["points"][0], route["points"][-1])
    ]
    result = []
    for feature in features:
        if feature["kind"] != "interaction":
            continue
        approach = point(feature.get("approach_at"), "interaction approach_at")
        x, y = feature["at"]
        w, h = feature["size"]
        dx = max(x - approach[0], 0, approach[0] - (x + w))
        dy = max(y - approach[1], 0, approach[1] - (y + h))
        connected = approach in endpoints and math.hypot(dx, dy) <= base
        result.append({"id": feature["id"], "status": "connected" if connected else "unverified"})
    return result


def sheet(plan, checks, number):
    """Create one strictly orthographic comparison, in a fixed common orientation."""
    e = lambda s: html.escape(str(s), quote=True)  # noqa: E731
    dims = plan["dimensions"]
    width, depth = dims["outer_mm"]
    scale = min(380 / width, 300 / depth)
    panel_width, panel_height = 460, 590
    total_width = panel_width * len(plan["options"])
    parts = [
        "",
        '<rect width="100%" height="100%" fill="white"/>',
        '<g font-family="sans-serif" font-size="12" fill="#172332">',
        f'<text x="15" y="18">Revision {number} · TOP DOWN · North ↑ · X → / Y ↓</text>',
    ]
    max_lines = 0
    for index, option in enumerate(plan["options"]):
        ox, oy = 30 + index * panel_width, 65
        parts.append(f'<text x="{ox}" y="43">{e(option["id"])}: {e(option["title"])}</text>')
        parts.append(
            f'<rect x="{ox}" y="{oy}" width="{width * scale}" height="{depth * scale}" '
            'fill="#f9fafb" stroke="#172332"/>'
        )
        pitch = dims["game_pitch_mm"]
        cols, rows = dims["playable_squares"]
        for col in range(cols + 1):
            x = ox + col * pitch * scale
            parts.append(f'<path d="M{x} {oy} v{rows * pitch * scale}" stroke="#c6cdd3"/>')
            if col < cols:
                parts.append(f'<text x="{x + 2}" y="{oy - 3}" font-size="9">{col}</text>')
        for row in range(rows + 1):
            y = oy + row * pitch * scale
            parts.append(f'<path d="M{ox} {y} h{cols * pitch * scale}" stroke="#c6cdd3"/>')
            if row < rows:
                parts.append(f'<text x="{ox - 16}" y="{y + 10}" font-size="9">{row}</text>')
        colors = {
            "entry": "#81c995",
            "reveal": "#a9d5ff",
            "cover": "#d4b48c",
            "interaction": "#f5a8a8",
            "height": "#d8c1eb",
            "stairs": "#eacb68",
        }
        for f in option["features"]:
            x, y = f["at"]
            w, h = f["size"]
            parts.append(
                f'<rect x="{ox + x * scale}" y="{oy + y * scale}" width="{w * scale}" '
                f'height="{h * scale}" fill="{colors[f["kind"]]}" fill-opacity=".65" '
                'stroke="#49515a"/>'
            )
            parts.append(
                f'<text x="{ox + x * scale + 2}" y="{oy + y * scale + 12}" font-size="9">'
                f"{e(f['id'])}</text>"
            )
        for route, result in zip(option["routes"], checks[option["id"]]["routes"], strict=True):
            pts = " ".join(f"{ox + x * scale},{oy + y * scale}" for x, y in route["points"])
            color = {"blocked": "#b00020", "tight": "#b46b00", "feasible": "#087c46"}[
                result["status"]
            ]
            parts.append(
                f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="3" '
                'stroke-dasharray="6 3"/>'
            )
            x, y = route["points"][len(route["points"]) // 2]
            parts.append(
                f'<text x="{ox + x * scale}" y="{oy + y * scale - 5}" font-size="9" '
                f'fill="{color}">{e(route["id"])}</text>'
            )
        bases = dims.get("base_diameters_mm", [dims["base_diameter_mm"]])
        max_base = max(bases) * scale
        cx, cy = ox + max_base / 2 + 4, oy + depth * scale - max_base / 2 - 4
        for base in bases:
            parts.append(
                f'<circle cx="{cx}" cy="{cy}" r="{base * scale / 2}" '
                'fill="none" stroke="#111" stroke-width="1"/>'
            )
        lines = [
            f"{option['approach']}; outer {width} × {depth} mm; grid {cols} × {rows}",
            f"game pitch {pitch} mm; miniature scale {dims['mini_scale']} mm nominal; "
            f"base {dims['base_diameter_mm']} mm",
            f"viewer ruler {dims['viewer_ruler_mm']} mm; "
            f"library pitch {dims['library_pitch_mm']} mm",
            "Expected bases (concentric circles), mm: " + ", ".join(map(str, bases)),
            f"footprint: {checks[option['id']]['footprint']}",
            "routes: "
            + ", ".join(
                f"{r['id']} {r['status']} ({r['available_mm']:.1f} mm)"
                for r in checks[option["id"]]["routes"]
            ),
            "interactions: "
            + ", ".join(f"{r['id']} {r['status']}" for r in checks[option["id"]]["interactions"]),
            "Features: "
            + "; ".join(f"{f['id']} ({f['kind']}): {f['label']}" for f in option["features"]),
            "Confirmed: " + "; ".join(dims["confirmed"]),
            "Assumptions: " + "; ".join(dims["assumptions"]),
            "Physical unknowns: " + "; ".join(dims["physical_unknowns"]),
            "Sketch only: not a physical-fit certificate.",
            "Intent: " + option["intent"],
            "Changed: " + plan["changes"],
            "Clarified: " + plan["clarified"],
            "Next decision: " + plan["pending_decision"],
        ]
        wrapped = [piece for line in lines for piece in textwrap.wrap(line, width=65)]
        max_lines = max(max_lines, len(wrapped))
        for n, line in enumerate(wrapped):
            parts.append(f'<text x="{ox}" y="{390 + n * 18}" font-size="10">{e(line)}</text>')
    panel_height = max(panel_height, 410 + max_lines * 18)
    parts[0] = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" '
        f'height="{panel_height}" viewBox="0 0 {total_width} {panel_height}">'
    )
    parts.append("</g></svg>")
    return "\n".join(parts) + "\n"


def verify_revision(root, ref):
    if not isinstance(ref, dict) or set(ref) != {"number", "sha256", "sheet_sha256"}:
        raise ValueError("Invalid layout revision reference")
    number_ = ref["number"]
    if type(number_) is not int or number_ < 1:
        raise ValueError("Invalid layout revision number")
    folder = Path(root) / "layouts"
    source, svg = folder / f"{number_:04}.json", folder / f"{number_:04}.svg"
    if sha256(source) != ref["sha256"] or sha256(svg) != ref["sheet_sha256"]:
        raise ValueError("Layout revision or sheet changed")
    record = read_json(source)
    if record.get("number") != number_:
        raise ValueError("Layout revision number mismatch")
    checks = check_plan(record["plan"])
    if checks != record.get("checks"):
        raise ValueError("Layout checks do not match the plan")
    return record
