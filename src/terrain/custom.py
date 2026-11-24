"""Original Blender drafts, kept out of the indexed library until explicit approval."""

import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from terrain.build import BuildError
from terrain.library import (
    catalog_roots,
    index_library,
    load_catalog,
    read_json,
    read_mesh,
    sha256,
    write_json,
)
from terrain.mesh import MeshRules, inspect_mesh

FILES = ("model.stl", "model.blend", "build.py")
DRAFT_LABEL = "Custom · unindexed · approval pending"


def blender_executable(value=None):
    candidate = value or shutil.which("blender")
    if not candidate and Path("/Applications/Blender.app/Contents/MacOS/Blender").is_file():
        candidate = "/Applications/Blender.app/Contents/MacOS/Blender"
    if not candidate:
        raise ValueError("Blender not found; pass --blender /absolute/path/to/blender")
    return str(candidate)


def outside_assets(path):
    if "assets" in Path(path).resolve().parts:
        raise ValueError("Unapproved custom models must stay outside assets")


def draft_asset(manifest):
    manifest = Path(manifest).resolve()
    outside_assets(manifest)
    draft = read_json(manifest)
    if draft.get("schema_version") != 1 or draft.get("status") != "custom_unindexed":
        raise ValueError(f"Not an unindexed custom draft: {manifest}")
    for name in FILES:
        path = manifest.parent / name
        if path.is_symlink() or sha256(path) != draft.get("files", {}).get(name):
            raise ValueError(f"Custom source changed since creation: {path}")
    mesh = read_mesh(manifest.parent / "model.stl")
    return {
        "id": f"custom-draft:{sha256(manifest)}",
        "path": "model.stl",
        "draft_manifest": str(manifest),
        "sha256": draft["files"]["model.stl"],
        "name": draft["name"],
        "description": draft["brief"],
        "collection": "Unindexed custom models",
        "category": "scenery",
        "tags": ["custom", "unindexed"],
        "library_status": "custom_unindexed",
        "license": draft["license"],
        "printed": None,
        "bounds_mm": mesh.bounds.tolist(),
        "extents_mm": mesh.extents.tolist(),
        "triangles": len(mesh.faces),
    }


def create_custom(path, script, name, brief, license_name, blender=None):
    path, script = Path(path).resolve(), Path(script).resolve()
    outside_assets(path)
    if path.exists():
        raise ValueError(f"Custom draft already exists; use a new revision directory: {path}")
    if not all(isinstance(value, str) and value.strip() for value in (name, brief, license_name)):
        raise ValueError("Custom drafts need a name, brief and license")
    executable = blender_executable(blender)
    source = script.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".blender-", dir=path.parent) as temporary:
        stage = Path(temporary)
        (stage / "build.py").write_bytes(source)
        try:
            result = subprocess.run(
                [
                    executable,
                    "--background",
                    "--factory-startup",
                    "--disable-autoexec",
                    "--python-exit-code",
                    "1",
                    "--python",
                    str(Path(__file__).with_name("blender_runner.py")),
                    "--",
                    str(stage / "build.py"),
                    str(stage),
                ],
                cwd=stage,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired as error:
            raise BuildError("Blender modelling timed out after 180 seconds") from error
        (stage / "blender.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            raise BuildError(
                f"Blender failed ({result.returncode}):\n{result.stdout}{result.stderr}"
            )
        # Check output, not just Blender's exit status.
        read_mesh(stage / "model.stl")
        validation = inspect_mesh(stage / "model.stl", MeshRules(expected_components=None))
        validation["path"] = str(path / "model.stl")
        write_json(stage / "validation.json", validation)
        write_json(
            stage / "draft.json",
            {
                "schema_version": 1,
                "status": "custom_unindexed",
                "name": name,
                "brief": brief,
                "created_at": datetime.now(UTC).isoformat(),
                "blender_version": next(
                    (line for line in result.stdout.splitlines() if line.startswith("Blender ")),
                    "See blender.log",
                ),
                "units": "mm",
                "license": {"name": license_name, "modify": True, "redistribute": False},
                "files": {filename: sha256(stage / filename) for filename in FILES},
                "software_validation": validation["valid"],
                "physical_validation": "pending",
            },
        )
        draft_asset(stage / "draft.json")
        stage.rename(path)
    return {
        "draft": path / "draft.json",
        "review_sha256": sha256(path / "draft.json"),
        "status": "custom_unindexed",
        "validation": path / "validation.json",
    }


def preview_custom(manifest, openscad="openscad"):
    from terrain.review import build_review
    from terrain.scene import add_custom_placement, assemble_scene, init_scene

    manifest = Path(manifest).resolve()
    asset = draft_asset(manifest)
    output = manifest.parent / "preview"
    output.mkdir(exist_ok=True)
    scene = output / "scene.json"
    if not scene.exists():
        init_scene(scene, None, asset["name"], asset["description"])
        add_custom_placement(scene, manifest, "custom-model", [0, 0, 0])
        data = read_json(scene)
        data["iteration"] = {
            "number": 1,
            "title": DRAFT_LABEL,
            "changes": f"Review SHA-256: {sha256(manifest)}",
            "feedback": "",
            "design_notes": "Library approval is separate from print approval.",
        }
        write_json(scene, data)
    result = assemble_scene(
        scene, output, preview=True, openscad=openscad, views=("iso", "reverse", "top", "front")
    )
    result.update(review=build_review(scene, output), review_sha256=sha256(manifest))
    return result


def approve_custom(manifest, identity, assets_root, catalog_path, approval, review_sha256):
    if not isinstance(approval, str) or not approval.strip():
        raise ValueError("Explicit user approval is required; record the user's confirmation")
    manifest = Path(manifest).resolve()
    if sha256(manifest) != review_sha256:
        raise ValueError("Draft changed since review; preview and approve the exact revision")
    asset = draft_asset(manifest)
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", identity):
        raise ValueError("Custom ID must use lowercase letters, numbers, hyphens or underscores")
    root = Path(assets_root).resolve()
    catalog_path = Path(catalog_path).resolve()
    catalog = load_catalog(catalog_path) if catalog_path.exists() else None
    roots = catalog_roots(catalog) if catalog else {}
    primary_custom = catalog is None or (catalog.get("primary_custom") and roots.get("") == root)
    if "custom" in roots and roots["custom"] != root:
        raise ValueError("Catalog already uses a different custom library root")
    if root == manifest.parent or root.is_relative_to(manifest.parent):
        raise ValueError("Approved library must be separate from draft inputs")
    if any(
        root.is_relative_to(path) or path.is_relative_to(root)
        for key, path in roots.items()
        if key != "custom" and not (key == "" and primary_custom)
    ) or catalog_path.is_relative_to(root):
        raise ValueError("Custom library must be separate from existing library and catalog inputs")
    destination = root / identity
    if destination.exists():
        raise ValueError(f"Approved custom asset already exists: {destination}")
    validation = inspect_mesh(manifest.parent / "model.stl", MeshRules(expected_components=None))
    if not validation["valid"]:
        raise ValueError(f"Custom mesh validation failed: {validation['errors']}")
    # Approval is a local human gate, not authentication. Never invent its evidence.
    draft = read_json(manifest)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".approval-lock"
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise ValueError("Custom library approval is locked by another operation") from error
    try:
        if destination.exists():
            raise ValueError(f"Approved custom asset already exists: {destination}")
        with tempfile.TemporaryDirectory(prefix=".approval-", dir=root.parent) as temporary:
            stage = Path(temporary)
            for name in FILES:
                shutil.copyfile(manifest.parent / name, stage / name)
                if sha256(stage / name) != draft["files"][name]:
                    raise ValueError(f"Custom source changed during approval: {name}")
            write_json(
                stage / "provenance.json",
                {
                    **draft,
                    "status": "approved",
                    "draft_sha256": review_sha256,
                    "approval": approval.strip(),
                    "approved_at": datetime.now(UTC).isoformat(),
                    "description": asset["description"],
                    "validation": validation,
                    "physical_validation": "pending",
                },
            )
            stage.rename(destination)
        try:
            # Preserve the purchased root, annotations and all previously approved models.
            if not primary_custom:
                index_library(catalog["root"], catalog_path, additional_roots={"custom": root})
            else:
                index_library(root, catalog_path, primary_custom=True)
        except Exception:
            shutil.rmtree(destination)  # Only this operation's newly created copy.
            raise
    finally:
        lock.rmdir()
    return {
        "asset": f"custom/{identity}/model.stl",
        "source": destination / "model.stl",
        "blend": destination / "model.blend",
        "catalog": catalog_path,
        "physical_validation": "pending",
    }
