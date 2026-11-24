"""Offline WebGL inspection, never a fused or production-ready mesh export."""

import base64
import html
import json
from pathlib import Path
from string import Template

import numpy as np

from terrain.library import read_json, read_mesh, source_path
from terrain.scene import resolve_placements

TEMPLATES = Path(__file__).parent / "templates"


def escaped(value):
    return html.escape(str(value), quote=True)


def packed(values, dtype):
    return base64.b64encode(np.asarray(values, dtype=dtype).tobytes()).decode("ascii")


def safe_json(value):
    # JSON in a script data element must not terminate the enclosing HTML tag.
    return json.dumps(value, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")


def build_review(snapshot, output_dir):
    scene, catalog, resolved = resolve_placements(snapshot)
    output = Path(output_dir)
    report = read_json(output / "report.json")
    geometry = {}
    instances = []
    for placement, asset, matrix, _ in resolved:
        identity = asset["id"]
        if identity not in geometry:
            mesh = read_mesh(source_path(catalog, asset))
            geometry[identity] = {
                "id": identity,
                "sha256": asset["sha256"],
                "vertices": packed(mesh.vertices, "<f4"),
                "indices": packed(mesh.faces, "<u4"),
            }
        instances.append(
            {
                "id": placement["id"],
                "asset": identity,
                "role": placement.get("role", "architecture"),
                "matrix": matrix.T.ravel().tolist(),
            }
        )
    iteration = scene["iteration"]
    payload = {
        "geometry": list(geometry.values()),
        "instances": instances,
        "bounds": report["bounds_mm"],
        "iteration": {k: iteration[k] for k in ("number", "title")},
    }
    rows = []
    for item in report["print_list"]:
        stock = "Unknown" if item["already_printed"] is None else item["already_printed"]
        remaining = "Unknown" if item["to_print"] is None else item["to_print"]
        rows.append(
            "<tr>"
            f"<td>{escaped(item['asset'])}<small>{escaped(item['license']['name'])}</small></td>"
            f"<td>{item['required']}</td><td>{stock}</td><td>{remaining}</td></tr>"
        )
    parts = "".join(
        f'<label class="part"><input type="checkbox" checked data-piece="{i}">'
        f"<span><b>{escaped(p['id'])}</b><small>{escaped(p['role'])}</small></span></label>"
        for i, p in enumerate(instances)
    )
    previews = "".join(
        f'<a href="{name}.png"><img src="{name}.png" alt="{name} geometry view">'
        f"<span>{name.title()}</span></a>"
        for name in ("iso", "reverse", "top", "front")
    )
    overlaps = report["aabb_overlaps"]
    checks = [
        *report["warnings"],
        f"{len(overlaps)} AABB overlap warning(s). This may include intentional floor contact.",
    ]
    if overlaps:
        checks.append("Review pairs: " + "; ".join(" / ".join(pair) for pair in overlaps))
    substitutions = {
        "title": escaped(scene["name"]),
        "iteration": f"{iteration['number']:02} / {escaped(iteration['title'])}",
        "brief": escaped(scene["brief"]),
        "changes": escaped(iteration["changes"]),
        "feedback_received": escaped(iteration["feedback"] or "No feedback recorded yet."),
        "dimensions": " × ".join(f"{n:.1f}" for n in report["extents_mm"]),
        "parts": parts,
        "rows": "".join(rows),
        "previews": previews,
        "checks": "".join(f"<li>{escaped(w)}</li>" for w in checks),
        "encounter": escaped(json.dumps(scene.get("encounter", {}), indent=2, ensure_ascii=False)),
        "art_direction": escaped(
            json.dumps(scene.get("art_direction", {}), indent=2, ensure_ascii=False)
        ),
        "journal": escaped(iteration["design_notes"]),
        "data": safe_json(payload),
        "style": (TEMPLATES / "review.css").read_text(),
        "script": (TEMPLATES / "review.js").read_text(),
    }
    page = Template((TEMPLATES / "review.html").read_text()).substitute(substitutions)
    destination = output / "review.html"
    destination.write_text(page)
    return destination


def write_history(output, history):
    output = Path(output)
    latest = history[-1][1]
    cards = []
    for _, scene in reversed(history):
        iteration = scene["iteration"]
        cards.append(
            f'<a class="revision" target="scene-review" '
            f'href="{iteration["number"]:04}/review.html">'
            f"<small>ITERATION {iteration['number']:02}</small>"
            f"<strong>{escaped(iteration['title'])}</strong>"
            f"<span>{escaped(iteration['changes'])}</span></a>"
        )
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'; frame-src 'self' file:;\">"
        f"<title>{escaped(latest['name'])} · Terrain workshop</title><style>"
        + (TEMPLATES / "review.css").read_text()
        + '</style></head><body class="history"><aside><p class="eyebrow">TERRAIN WORKSHOP</p>'
        f"<h1>{escaped(latest['name'])}</h1>"
        '<p class="muted">Saved drafts, not print approval. Choose an iteration to inspect.</p>'
        + "".join(cards)
        + '<p class="muted">Discuss changes with your agent. Refresh this page after '
        "the next checkpoint. Everything stays on this computer.</p></aside>"
        f'<iframe name="scene-review" title="Interactive scene review" '
        f'src="{latest["iteration"]["number"]:04}/review.html"></iframe></body></html>'
    )
    temporary = output / ".index.html.tmp"
    temporary.write_text(page)
    temporary.replace(output / "index.html")
