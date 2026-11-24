"""Local, read-only discovery of third-party meshes. No geometry repair or rescaling."""

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import trimesh

FORMATS = {".stl", ".3mf"}
UNKNOWN_LICENSE = {"name": "unknown", "modify": None, "redistribute": None}


def read_json(path):
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError) as error:
        raise ValueError(f"Unable to read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_catalog(path):
    catalog = read_json(path)
    if catalog.get("schema_version") != 1 or not isinstance(catalog.get("assets"), list):
        raise ValueError(f"Unsupported library catalog: {path}")
    return catalog


def source_path(catalog, asset):
    root = Path(catalog["root"]).resolve()
    path = (root / asset["path"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Asset path is outside library: {asset['path']}")
    if path.suffix.lower() not in FORMATS:
        raise ValueError(f"Unsupported model format: {path}")
    return path


def read_mesh(path):
    loaded = trimesh.load(path, process=False)
    native_units = loaded.units
    if Path(path).suffix.lower() == ".3mf" and native_units:
        # Interpret the file's declared units, not an artistic/mechanical rescale.
        loaded = loaded.convert_units("mm")
    if isinstance(loaded, trimesh.Scene):
        # geometry.values() loses scene-node instances and their transforms.
        loaded = loaded.to_mesh()
    if not isinstance(loaded, trimesh.Trimesh) or loaded.is_empty:
        raise ValueError("Empty or unsupported mesh")
    if not np.isfinite(loaded.vertices).all():
        raise ValueError("Mesh has nonfinite coordinates")
    loaded.metadata["source_units"] = native_units
    return loaded


def tokens(text):
    text = re.sub(r"sci[\s-]*fi", "sciencefiction", text.lower())
    aliases = {"lab": "laboratory", "piping": "pipe", "pipes": "pipe"}
    return {aliases.get(word, word) for word in re.findall(r"[a-z0-9]+", text)}


def category_for(name):
    for category, words in {
        "connector": ("clip", "peg", "connector"),
        "doorway": ("doorway", "bulkhead", "hatch", "door"),
        "wall": ("wall", "junction"),
        "floor": ("floor", "platform", "walkway"),
        "structure": ("building", "roof", "frame", "stairs", "canopy"),
        "greeble": ("panel", "console", "pipe", "piping", "vent", "fan", "widget", "tank"),
    }.items():
        if tokens(name).intersection(words):
            return category
    return "scenery"


def license_notices(root):
    notices = []
    for path in sorted(root.rglob("*.txt")):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            continue
        text = path.read_text(errors="replace")
        if "personal use only" in text.lower():
            notices.append(
                (
                    path.parent,
                    {
                        "name": "Personal use only (source notice)",
                        "modify": False
                        if "may not share, modify or sell" in text.lower()
                        else None,
                        "redistribute": False,
                        "notice_path": path.relative_to(root).as_posix(),
                        "notice_text": text.strip(),
                    },
                )
            )
    return notices


def annotations_for(metadata, relative, collection):
    result = {}
    tags = []
    for layer in (
        metadata.get("defaults", {}),
        metadata.get("collections", {}).get(collection, {}),
        metadata.get("assets", {}).get(relative, {}),
    ):
        if not isinstance(layer, dict):
            raise ValueError(f"Invalid annotations for {relative}")
        result.update(layer)
        layer_tags = layer.get("tags", [])
        if not isinstance(layer_tags, list) or not all(isinstance(t, str) for t in layer_tags):
            raise ValueError(f"tags must be a list of strings: {relative}")
        tags.extend(layer_tags)
    result["tags"] = sorted(set(tags))
    printed = result.get("printed")
    if printed is not None and (type(printed) is not int or printed < 0):
        raise ValueError(f"printed must be a nonnegative integer or null: {relative}")
    return result


def index_library(root, destination, metadata_path=None):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if not root.is_dir():
        raise ValueError(f"Library is not a directory: {root}")
    previous = load_catalog(destination) if destination.exists() else {}
    if metadata_path is None and previous.get("root") == str(root):
        metadata_path = previous.get("metadata")
    if metadata_path and Path(metadata_path).resolve() == destination:
        raise ValueError("Catalog cannot overwrite annotation metadata")
    metadata = read_json(metadata_path) if metadata_path else {}
    for key in ("defaults", "collections", "assets"):
        if not isinstance(metadata.get(key, {}), dict):
            raise ValueError(f"Invalid metadata section: {key}")
    old = (
        {a["id"]: a for a in previous.get("assets", [])}
        if previous.get("measurement_version") == 2
        else {}
    )
    notices = license_notices(root)
    assets = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in FORMATS:
            continue  # Do not unpack ZIPs or execute anything supplied with a model.
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            continue
        relative = path.relative_to(root).as_posix()
        collection = Path(relative).parts[0] if "/" in relative else root.name
        annotations = annotations_for(metadata, relative, collection)
        license_info = {**UNKNOWN_LICENSE, **annotations.get("license", {})}
        for parent, notice in notices:
            if path.is_relative_to(parent):
                license_info.update(notice)
        asset = {
            "id": relative,
            "path": relative,
            "name": re.sub(r"[_-]+", " ", path.stem),
            "collection": collection,
            "category": annotations.get("category", category_for(path.stem)),
            "description": annotations.get("description", ""),
            "tags": annotations["tags"],
            "visual_review": annotations.get("visual_review", "pending"),
            "author": annotations.get("author", ""),
            "license": license_info,
            "printed": annotations.get("printed"),
            "units": "mm",
            "units_confirmed": annotations.get("units_confirmed", False),
            "connectors": annotations.get(
                "connectors", {"system": "unknown", "status": "unverified"}
            ),
            "print_validation": "not_checked",
        }
        try:
            asset["sha256"] = sha256(path)
            cached = old.get(relative, {})
            if cached.get("sha256") == asset["sha256"] and not cached.get("error"):
                for key in ("bounds_mm", "extents_mm", "triangles", "native_units"):
                    asset[key] = cached[key]
            else:
                mesh = read_mesh(path)
                asset.update(
                    bounds_mm=mesh.bounds.tolist(),
                    extents_mm=mesh.extents.tolist(),
                    triangles=len(mesh.faces),
                    native_units=mesh.metadata.get("source_units"),
                )
        except (OSError, ValueError, TypeError, IndexError) as error:
            asset["error"] = str(error)
        assets.append(asset)
    catalog = {
        "schema_version": 1,
        "measurement_version": 2,
        "root": str(root),
        "metadata": str(Path(metadata_path).resolve()) if metadata_path else None,
        "notes": [
            "Local/private catalog; no source files were changed or uploaded.",
            "STL units are assumed millimetres, not inferred or silently corrected.",
            "Measurements do not certify connector compatibility or printability.",
        ],
        "assets": assets,
    }
    write_json(destination, catalog)
    failed = sum("error" in a for a in assets)
    return {"catalog": destination, "indexed": len(assets) - failed, "failed": failed}


def search_assets(catalog, query="", collection=None, limit=0):
    if limit < 0:
        raise ValueError("limit must be nonnegative (0 means all)")
    wanted = tokens(query)
    matches = [
        asset
        for asset in catalog["assets"]
        if not asset.get("error")
        and (collection is None or asset["collection"] == collection)
        and wanted
        <= tokens(
            " ".join(
                [
                    asset["id"],
                    asset["name"],
                    asset["description"],
                    asset["category"],
                    *asset["tags"],
                ]
            )
        )
    ]
    return matches[:limit] if limit else matches
