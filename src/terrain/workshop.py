"""Source-controlled encounter drafts and private, reproducible visual checkpoints."""

import copy
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from terrain.library import catalog_roots, read_json, sha256, write_json
from terrain.review import build_review, write_history
from terrain.scene import assemble_scene, init_scene, resolve_placements, scene_catalog

VIEWS = ("iso", "reverse", "top", "front")
DESIGN_NOTES = """# Encounter design journal

## Current intent
{brief}

## Confirmed decisions

## Assumptions (not user decisions)

## Open questions

## Feedback log

## Next step
Discuss the defining scene, antagonist, player choices, and table constraints.
"""


def init_workshop(path, catalog, name, brief):
    path = Path(path).resolve()
    if any((path / filename).exists() for filename in ("scene.json", "design.md", "revisions")):
        raise ValueError(f"Workshop already exists: {path}")
    init_scene(path / "scene.json", catalog, name, brief)
    scene = read_json(path / "scene.json")
    scene["encounter"] = {
        "context": "",
        "villains": [],
        "party": {},
        "space": {"footprint_mm": None, "base_sizes_mm": [], "grid_mm": None},
        "objectives": [],
        "terrain_beats": [],
        "decisions": [],
        "assumptions": [],
        "open_questions": [],
    }
    write_json(path / "scene.json", scene)
    (path / "design.md").write_text(DESIGN_NOTES.format(brief=brief))
    return {"workshop": path, "scene": path / "scene.json", "journal": path / "design.md"}


def revisions(path):
    result = []
    for snapshot in sorted((path / "revisions").glob("*.json")):
        if not re.fullmatch(r"\d{4,}\.json", snapshot.name):
            continue
        scene = read_json(snapshot)
        iteration = scene.get("iteration", {})
        number = int(snapshot.stem)
        if number < 1 or snapshot.name != f"{number:04}.json" or iteration.get("number") != number:
            raise ValueError(f"Invalid iteration metadata: {snapshot}")
        result.append((snapshot, scene))
    return sorted(result, key=lambda item: item[1]["iteration"]["number"])


@contextmanager
def workshop_lock(path):
    if not (path / "scene.json").is_file() or not (path / "design.md").is_file():
        raise ValueError(f"Not a workshop: {path}")
    lock = path / ".checkpoint-lock"
    try:
        lock.mkdir()
    except FileExistsError as error:
        raise ValueError(
            f"Workshop is locked: {lock}. If a previous process crashed, "
            "confirm it has stopped before removing this empty lock directory."
        ) from error
    try:
        yield
    finally:
        lock.rmdir()


def prepare_output(path, output, scenes):
    # Never create private preview geometry in a source tree or over an input.
    inputs = [path]
    for source, scene in scenes:
        catalog = scene_catalog(source, scene)
        inputs.extend(catalog_roots(catalog).values())
        if scene.get("catalog"):
            inputs.append((source.parent / scene["catalog"]).resolve())
        inputs.extend(
            Path(asset["draft_manifest"]).resolve().parent
            for asset in catalog["assets"]
            if asset.get("draft_manifest")
        )
        if catalog.get("metadata"):
            inputs.append(Path(catalog["metadata"]).resolve())
    if any(output.is_relative_to(p) or p.is_relative_to(output) for p in inputs):
        raise ValueError("Workshop output must be separate from workshop and library inputs")
    marker = output / ".terrain-workshop.json"
    if (
        output.exists()
        and any(output.iterdir())
        and (not marker.is_file() or read_json(marker).get("workshop") != str(path))
    ):
        raise ValueError("Workshop output is not owned by this workshop; choose an empty output")
    output.mkdir(parents=True, exist_ok=True)
    write_json(marker, {"workshop": str(path)})


def materialize(snapshot, destination, openscad):
    if destination.exists():
        raise ValueError(f"Revision output already exists: {destination}")
    with tempfile.TemporaryDirectory(prefix=".draft-", dir=destination.parent) as temporary:
        stage = Path(temporary)
        assemble_scene(snapshot, stage, preview=True, openscad=openscad, views=VIEWS)
        report_path = stage / "report.json"
        report = read_json(report_path)
        report["previews"] = [str(destination / Path(p).name) for p in report["previews"]]
        write_json(report_path, report)
        # A 3MF preview may refer to a flattened cache in the staging directory.
        source = stage / "assembly.scad"
        source.write_text(
            source.read_text().replace(
                json.dumps(str(stage))[1:-1], json.dumps(str(destination))[1:-1]
            )
        )
        build_review(snapshot, stage)
        write_json(stage / ".snapshot.json", {"sha256": sha256(snapshot)})
        stage.rename(destination)


def materialize_history(history, output, openscad):
    for snapshot, scene in history:
        # Verify even cached revisions; source changes must not be hidden by a cache.
        resolve_placements(snapshot)
        destination = output / f"{scene['iteration']['number']:04}"
        if not destination.exists():
            materialize(snapshot, destination, openscad)
            continue
        marker = destination / ".snapshot.json"
        if not marker.is_file() or read_json(marker).get("sha256") != sha256(snapshot):
            raise ValueError(f"Revision output differs from saved source: {destination}")
        expected = (
            "review.html",
            "report.json",
            "print-list.csv",
            "assembly.scad",
            "assembly.md",
            *(f"{view}.png" for view in VIEWS),
        )
        if not all((destination / filename).is_file() for filename in expected):
            raise ValueError(
                f"Incomplete revision output: {destination}; "
                "use a new empty --output-dir to rebuild without overwriting files"
            )


def checkpoint(path, output_dir, title, changes, feedback="", openscad="openscad"):
    path, output = Path(path).resolve(), Path(output_dir).resolve()
    if not title.strip() or not changes.strip():
        raise ValueError("A checkpoint needs a title and a change summary")
    with workshop_lock(path):
        working = path / "scene.json"
        scene, _, resolved = resolve_placements(working)
        history = revisions(path)
        prepare_output(path, output, [(working, scene), *history])
        materialize_history(history, output, openscad)
        number = history[-1][1]["iteration"]["number"] + 1 if history else 1
        folder = path / "revisions"
        folder.mkdir(exist_ok=True)
        snapshot = folder / f"{number:04}.json"
        draft = copy.deepcopy(scene)
        if scene.get("catalog"):
            draft["catalog"] = os.path.relpath((path / scene["catalog"]).resolve(), folder)
        if scene.get("custom_models"):
            draft["custom_models"] = {
                identity: os.path.relpath((path / reference).resolve(), folder)
                for identity, reference in scene["custom_models"].items()
            }
        draft["iteration"] = {
            "number": number,
            "title": title,
            "changes": changes,
            "feedback": feedback,
            "created_at": datetime.now(UTC).isoformat(),
            "design_notes": (path / "design.md").read_text(),
            "printed_inventory": {asset["id"]: asset["printed"] for _, asset, _, _ in resolved},
        }
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".draft-", suffix=".json") as stream:
            pending = Path(stream.name)
            write_json(pending, draft)
            materialize(pending, output / f"{number:04}", openscad)
            # Keep the temporary file for its context manager to clean up.
            with snapshot.open("x") as saved:
                saved.write(pending.read_text())
        history.append((snapshot, draft))
        write_history(output, history)
    return {
        "revision": number,
        "snapshot": snapshot,
        "index": output / "index.html",
        "review": output / f"{number:04}/review.html",
        "print_list": output / f"{number:04}/print-list.csv",
    }


def review_workshop(path, output_dir, openscad="openscad"):
    path, output = Path(path).resolve(), Path(output_dir).resolve()
    with workshop_lock(path):
        history = revisions(path)
        if not history:
            raise ValueError("Workshop has no saved iterations; create a checkpoint first")
        prepare_output(path, output, history)
        materialize_history(history, output, openscad)
        write_history(output, history)
    return {"revisions": len(history), "index": output / "index.html"}
