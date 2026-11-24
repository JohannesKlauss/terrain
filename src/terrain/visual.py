"""Private previews, never production copies of third-party geometry."""

import hashlib
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from terrain.build import BuildError, openscad_version, run_openscad
from terrain.library import read_mesh, sha256, source_path, write_json

CAMERAS = {
    "iso": "55,0,25",
    "reverse": "55,0,205",
    "front": "90,0,0",
    "top": "0,0,0",
    "underside": "180,0,0",
}


def label_custom_preview(path, placement_ids):
    from terrain.custom import DRAFT_LABEL

    with Image.open(path) as source:
        picture = source.convert("RGB")
    draw = ImageDraw.Draw(picture)
    font = ImageFont.load_default(size=18)
    draw.rectangle((0, 0, picture.width, 70), fill="#f4eafa")
    draw.text((16, 10), DRAFT_LABEL + " (purple)", fill="#74399b", font=font)
    draw.text((16, 38), ", ".join(placement_ids)[:130], fill="#74399b", font=font)
    picture.save(path)


def preview_source(catalog, asset, cache_dir):
    path = source_path(catalog, asset)
    if sha256(path) != asset["sha256"]:
        raise ValueError(f"Source changed; reindex and review placements: {asset['id']}")
    if path.suffix.lower() == ".3mf":
        # Flatten instances only in a private preview cache. Never touch the source.
        converted = Path(cache_dir) / f"mm-v2-{asset['sha256']}.preview.stl"
        if not converted.exists():
            converted.parent.mkdir(parents=True, exist_ok=True)
            read_mesh(path).export(converted)
        return converted.resolve()
    return path


def render_source(source, destination, view, openscad="openscad", size=(400, 300)):
    if view not in CAMERAS:
        raise ValueError(f"Unknown preview view: {view}")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    diagnostics = run_openscad(
        [
            "--preview",
            "--autocenter",
            "--viewall",
            "--projection=o",
            f"--camera=0,0,0,{CAMERAS[view]},0",
            f"--imgsize={size[0]},{size[1]}",
            "--colorscheme=Tomorrow",
            "-o",
            str(destination),
            str(source),
        ],
        openscad,
    )
    if re.search(r"^(WARNING|ERROR):", diagnostics, re.MULTILINE):
        raise BuildError(f"Preview diagnostics for {source}:\n{diagnostics}")
    if not destination.is_file():
        raise BuildError(f"Preview was not produced: {destination}")
    with Image.open(destination) as picture:
        extrema = picture.convert("RGB").getextrema()
        if all(high - low < 2 for low, high in extrema):
            raise BuildError(f"Preview is blank: {destination}")
    return diagnostics


def asset_preview(catalog, asset, output_dir, view, renderer_version, openscad):
    output_dir = Path(output_dir)
    cache = output_dir / "thumbnails"
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f"v1:{asset['sha256']}:{view}:{renderer_version}".encode()).hexdigest()
    destination = cache / f"{key}-{view}.png"
    if not destination.exists():
        path = preview_source(catalog, asset, cache)
        wrapper = cache / f"{key}.scad"
        wrapper.write_text(f"import({json.dumps(str(path), ensure_ascii=False)});\n")
        render_source(wrapper, destination, view, openscad)
    return destination


def contact_sheet(assets, thumbnails, destination, views, start):
    width, height = 400 * len(views), 386
    columns = min(3, len(assets))
    rows = (len(assets) + columns - 1) // columns
    picture = Image.new("RGB", (columns * width, rows * height + 44), "#edf0f2")
    draw = ImageDraw.Draw(picture)
    font = ImageFont.load_default(size=15)
    small = ImageFont.load_default(size=12)
    draw.text(
        (12, 12),
        "PRIVATE LIBRARY | measured geometry, fit and printability unverified",
        fill="#26313d",
        font=font,
    )
    for index, asset in enumerate(assets):
        x, y = (index % columns) * width, (index // columns) * height + 44
        for offset, view in enumerate(views):
            with Image.open(thumbnails[asset["id"]][view]) as thumb:
                picture.paste(thumb.convert("RGB"), (x + offset * 400, y))
            draw.text((x + offset * 400 + 10, y + 280), view, fill="white", font=small)
        draw.text(
            (x + 10, y + 306),
            f"{start + index + 1}. {asset['name']}"[:105],
            fill="#17202b",
            font=font,
        )
        draw.text((x + 10, y + 327), asset["collection"], fill="#47586b", font=small)
        dimensions = " x ".join(f"{n:.1f}" for n in asset["extents_mm"])
        draw.text(
            (x + 10, y + 347), f"{dimensions} mm | {asset['category']}", fill="#47586b", font=small
        )
        draw.text((x + 10, y + 366), asset["id"][:125], fill="#47586b", font=small)
    picture.save(destination)


def preview_library(catalog, assets, output_dir, views=("iso", "top"), openscad="openscad"):
    if not assets:
        raise ValueError("No matching assets to preview")
    if not views or any(view not in CAMERAS for view in views):
        raise ValueError("Views must be iso, top or underside")
    output_dir = Path(output_dir).resolve()
    version = openscad_version(openscad)
    thumbnails = {}
    for asset in assets:
        # Verify even when the thumbnail is already cached.
        if sha256(source_path(catalog, asset)) != asset["sha256"]:
            raise ValueError(f"Source changed; reindex: {asset['id']}")
        thumbnails[asset["id"]] = {
            view: asset_preview(catalog, asset, output_dir, view, version, openscad)
            for view in views
        }
    sheets = []
    for offset in range(0, len(assets), 12):
        path = output_dir / f"contact-sheet-{offset // 12 + 1:03}.png"
        contact_sheet(assets[offset : offset + 12], thumbnails, path, views, offset)
        sheets.append(path)
    selection = output_dir / "selection.json"
    write_json(
        selection,
        {
            "notes": catalog["notes"],
            "assets": [
                {**asset, "previews": {k: str(v) for k, v in thumbnails[asset["id"]].items()}}
                for asset in assets
            ],
            "sheets": list(map(str, sheets)),
        },
    )
    return {"selected": len(assets), "sheets": sheets, "selection": selection}
