"""Source-controlled encounter drafts and private, reproducible visual checkpoints."""

import copy
import csv
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from terrain.layout import check_plan, sheet, verify_revision
from terrain.library import catalog_roots, read_json, sha256, write_json
from terrain.quality import quality
from terrain.quality import status as quality_status
from terrain.review import build_review, write_history
from terrain.rough import evidence as rough_evidence
from terrain.scene import assemble_scene, init_scene, resolve_placements, scene_catalog
from terrain.staged import (
    HELD_WORKSHOP,
    MARKER,
    atomic_state,
    guard_workshop,
    new_state,
    read_state,
    validate_state,
)
from terrain.visual import label_rough_preview

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
    if not name.strip() or not brief.strip():
        raise ValueError("A workshop needs a name and brief")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.mkdir()
    except FileExistsError as error:
        raise ValueError(f"Workshop already exists: {path}") from error
    state = new_state(path, name, brief)
    write_json(path / MARKER, {"schema_version": 1, "workshop_id": state["workshop_id"]})
    init_scene(path / "scene.json", None, name, brief)
    scene = read_json(path / "scene.json")
    scene["catalog"] = os.path.relpath(Path(catalog).resolve(), path) if catalog else None
    scene["staged_workshop"] = state["workshop_id"]
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
    atomic_state(path, state)
    return {
        "workshop": path,
        "scene": path / "scene.json",
        "journal": path / "design.md",
        "state": path / "workshop-state.json",
    }


def workshop_status(path=None):
    if path is None:
        scenes = Path("scenes")
        candidates = (
            sorted(
                p
                for p in scenes.iterdir()
                if p.is_dir()
                and (
                    (p / MARKER).exists()
                    or (p / "workshop-state.json").exists()
                    or ((p / "scene.json").exists() and (p / "design.md").exists())
                )
            )
            if scenes.is_dir()
            else []
        )
        return {"workshops": [str(p) for p in candidates]}
    path = Path(path).resolve()
    state = read_state(path)
    if read_json(path / "scene.json").get("staged_workshop") != state["workshop_id"]:
        raise ValueError("Staged scene belongs to a different workshop or is missing its marker")
    result = {"workshop": str(path), **state}
    if "quality" in state or len(state["gate_evidence"]) == 2:
        result["quality_status"] = quality_status(path, state)
    return result


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
def workshop_lock(path, *, state_update=False):
    path = Path(path).resolve()
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
        if not state_update:
            guard_workshop(path)
        token = HELD_WORKSHOP.set(path)
        try:
            yield
        finally:
            HELD_WORKSHOP.reset(token)
    finally:
        lock.rmdir()


def update_workshop_state(path, expected, updated):
    """Commit an intake update only if its caller read the current state."""
    path = Path(path).resolve()
    with workshop_lock(path, state_update=True):
        current = read_state(path)
        if current != expected:
            raise ValueError("Workshop state changed; reload before updating")
        validate_state(path, read_json(path / MARKER), updated)
        if any(updated[k] != current[k] for k in ("schema_version", "workshop_id", "slug")):
            raise ValueError("Workshop identity cannot change")
        if any(updated[k] != current[k] for k in ("stage", "revisions", "gate_evidence")):
            raise ValueError("Use the layout commands to change a gate")
        if updated.get("requires_new_layout") != current.get("requires_new_layout"):
            raise ValueError("Only a new layout can clear a required revision")
        if updated.get("quality") != current.get("quality"):
            raise ValueError("Use quality commands to update review gates")
        if read_json(path / "scene.json").get("staged_workshop") != current["workshop_id"]:
            raise ValueError("Staged scene belongs to a different workshop")
        atomic_state(path, updated)
    return updated


def save_layout(path, plan, expected_revision):
    """Save immutable comparison and invalidate any previous 3D approval."""
    path = Path(path).resolve()
    checks = check_plan(plan)
    selected = plan.get("selected_option")
    if selected is not None and (not isinstance(selected, str) or selected not in checks):
        raise ValueError("Selected option is not in this comparison")
    with workshop_lock(path, state_update=True):
        state = read_state(path)
        if read_json(path / "scene.json").get("staged_workshop") != state["workshop_id"]:
            raise ValueError("Staged scene belongs to a different workshop")
        current = state["revisions"]["layout"]
        if (current["number"] if current else 0) != expected_revision:
            raise ValueError("Layout changed; reload before saving")
        folder = path / "layouts"
        folder.mkdir(exist_ok=True)
        existing = [
            int(p.stem)
            for p in folder.iterdir()
            if p.suffix in (".json", ".svg") and p.stem.isdigit()
        ]
        number = max(existing, default=0) + 1
        source, svg = folder / f"{number:04}.json", folder / f"{number:04}.svg"
        record = {
            "schema_version": 1,
            "number": number,
            "workshop_id": state["workshop_id"],
            "plan": plan,
            "checks": checks,
        }
        for target, content in (
            (source, json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False) + "\n"),
            (svg, sheet(plan, checks, number)),
        ):
            with target.open("x") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        reference = {"number": number, "sha256": sha256(source), "sheet_sha256": sha256(svg)}
        state["revisions"]["layout"] = reference
        state["revisions"]["scene"] = None
        state["stage"] = "layout_review"
        state["gate_evidence"] = []
        if "quality" in state:
            q = quality(state)
            state["quality"] = {
                **q,
                "sample": None,
                "sample_verdict": None,
                "finished_play": None,
                "finished_visual": None,
            }
        state.pop("requires_new_layout", None)
        state["pending_decision"] = plan["pending_decision"]
        validate_state(path, read_json(path / MARKER), state)
        atomic_state(path, state)
    return {"revision": reference, "source": source, "sheet": svg, "checks": checks}


def approve_layout(path, revision, digest, confirmation):
    """Record only a specific, unconditional confirmation of the current checked layout."""
    path = Path(path).resolve()
    with workshop_lock(path, state_update=True):
        state = read_state(path)
        if state.get("requires_new_layout"):
            raise ValueError("A new 2D revision is required before approval")
        reference = state["revisions"]["layout"]
        if (
            state["stage"] != "layout_review"
            or not reference
            or (reference["number"] != revision or reference["sha256"] != digest)
        ):
            raise ValueError("Approval must reference the current layout revision and digest")
        if read_json(path / "scene.json").get("staged_workshop") != state["workshop_id"]:
            raise ValueError("Staged scene belongs to a different workshop")
        record = verify_revision(path, reference)
        option = record["plan"].get("selected_option")
        phrase = f"I approve 2D revision {revision} option {option} for 3D"
        if not option or confirmation != phrase:
            raise ValueError(f"Explicit confirmation required: {phrase}")
        state["gate_evidence"] = [
            {
                "type": "layout_approval",
                "workshop_id": state["workshop_id"],
                "revision": revision,
                "sha256": digest,
                "sheet_sha256": reference["sheet_sha256"],
                "option": option,
                "confirmation": confirmation,
            }
        ]
        state["stage"] = "3d"
        state["pending_decision"] = (
            "Develop the approved layout in 3D without materially changing it."
        )
        validate_state(path, read_json(path / MARKER), state)
        atomic_state(path, state)
    return {"workshop": path, "stage": state["stage"], "evidence": state["gate_evidence"][0]}


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
        iteration = read_json(snapshot).get("iteration", {})
        if "rough_evidence" in iteration:
            report["rough_evidence"] = iteration["rough_evidence"]
            for view in ("top", "iso"):
                label_rough_preview(
                    stage / f"{view}.png",
                    view,
                    report["placements"],
                    report["rough_evidence"]["proxy_placements"],
                )
            stock = {entry["asset"]: entry for entry in report["rough_evidence"]["stock"]}
            report["print_list"] = [
                {
                    **item,
                    "required": stock[item["asset"]]["required"],
                    "already_printed": stock[item["asset"]]["printed"],
                    "to_print": stock[item["asset"]]["shortfall"],
                }
                for item in report["print_list"]
                if item["asset"] in stock
            ]
            with (stage / "print-list.csv").open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(
                    ["asset", "required", "already_printed", "to_print", "source", "license"]
                )
                for item in report["print_list"]:
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


def check_material_change(path, state, scene, catalog, resolved):
    layout = verify_revision(path, state["revisions"]["layout"])
    play = rough_evidence(scene, catalog, resolved, layout)
    if play["material_changes"]:
        state["stage"] = "layout_review"
        state["gate_evidence"] = []
        if "quality" in state:
            q = quality(state)
            state["quality"] = {
                **q,
                "sample": None,
                "sample_verdict": None,
                "finished_play": None,
                "finished_visual": None,
            }
        state["revisions"]["scene"] = None
        state["requires_new_layout"] = True
        state["pending_decision"] = "Revise the 2D plan to address: " + json.dumps(
            play["material_changes"], ensure_ascii=False
        )
        atomic_state(path, state)
        raise ValueError(
            "Material change requires a new 2D revision: "
            + json.dumps(play["material_changes"], ensure_ascii=False)
        )
    return play


def checkpoint(path, output_dir, title, changes, feedback="", openscad="openscad"):
    path, output = Path(path).resolve(), Path(output_dir).resolve()
    if not title.strip() or not changes.strip():
        raise ValueError("A checkpoint needs a title and a change summary")
    with workshop_lock(path):
        working = path / "scene.json"
        scene, catalog, resolved = resolve_placements(working)
        state = read_state(path) if (path / MARKER).exists() else None
        play = None
        if state is not None:
            layout_ref = state["revisions"]["layout"]
            play = check_material_change(path, state, scene, catalog, resolved)
            from terrain.quality import sample_pass

            try:
                sample_pass(path, state)
                detail_ready = True
            except (OSError, ValueError, KeyError):
                detail_ready = False
                if "quality" in state:
                    q = quality(state)
                    state["quality"] = {
                        **q,
                        "sample": None,
                        "sample_verdict": None,
                        "finished_play": None,
                        "finished_visual": None,
                    }
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
        if state is not None:
            draft["iteration"]["layout_revision"] = layout_ref
            draft["iteration"]["rough_evidence"] = play
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".draft-", suffix=".json") as stream:
            pending = Path(stream.name)
            write_json(pending, draft)
            materialize(pending, output / f"{number:04}", openscad)
            # Keep the temporary file for its context manager to clean up.
            with snapshot.open("x") as saved:
                saved.write(pending.read_text())
        history.append((snapshot, draft))
        write_history(output, history)
        if state is not None:
            state["revisions"]["scene"] = {
                "number": number,
                "sha256": sha256(snapshot),
                "working_sha256": sha256(working),
                "layout_sha256": layout_ref["sha256"],
            }
            state["gate_evidence"] = state["gate_evidence"][:1]
            if detail_ready:
                state["quality"]["finished_play"] = None
                state["quality"]["finished_visual"] = None
                state["pending_decision"] = (
                    f"Review finished play and visuals for revision {number}."
                )
            else:
                state["pending_decision"] = (
                    f"Review rough revision {number} and decide whether to accept it "
                    "for sample review."
                )
            validate_state(path, read_json(path / MARKER), state)
            atomic_state(path, state)
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
        if (path / MARKER).exists():
            scene, catalog, resolved = resolve_placements(path / "scene.json")
            check_material_change(path, read_state(path), scene, catalog, resolved)
        history = revisions(path)
        if not history:
            raise ValueError("Workshop has no saved iterations; create a checkpoint first")
        prepare_output(path, output, history)
        materialize_history(history, output, openscad)
        write_history(output, history)
    return {"revisions": len(history), "index": output / "index.html"}


def accept_rough(path, revision, digest, confirmation):
    path = Path(path).resolve()
    with workshop_lock(path, state_update=True):
        state = read_state(path)
        rough = state["revisions"]["scene"]
        if (
            state["stage"] != "3d"
            or not rough
            or (rough["number"] != revision or rough["sha256"] != digest)
        ):
            raise ValueError("Acceptance must identify the current rough snapshot and digest")
        if sha256(path / "scene.json") != rough["working_sha256"]:
            raise ValueError("Working scene changed; checkpoint before acceptance")
        snapshot = path / "revisions" / f"{revision:04}.json"
        resolve_placements(snapshot)
        saved = read_json(snapshot)
        play = saved["iteration"]["rough_evidence"]
        if (
            play["material_changes"]
            or play["unresolved_features"]
            or any(gap["status"] != "resolved" for gap in play["gaps"])
        ):
            raise ValueError("Resolve blocking gaps and material changes before rough acceptance")
        phrase = f"I accept rough revision {revision} for sample review"
        if confirmation != phrase:
            raise ValueError(f"Explicit confirmation required: {phrase}")
        if "quality" in state:
            q = quality(state)
            if q["sample"] and q["sample"]["rough"]["sha256"] != digest:
                state["quality"] = {
                    **q,
                    "sample": None,
                    "sample_verdict": None,
                    "finished_play": None,
                    "finished_visual": None,
                }
        state["gate_evidence"] = state["gate_evidence"][:1] + [
            {
                "type": "rough_acceptance",
                "workshop_id": state["workshop_id"],
                "revision": revision,
                "sha256": digest,
                "confirmation": confirmation,
            }
        ]
        state["pending_decision"] = (
            "Review sample pieces; visual and release approval remain pending."
        )
        validate_state(path, read_json(path / MARKER), state)
        atomic_state(path, state)
    return {"workshop": path, "sample_review_ready": True, "revision": revision}


def sample_review_status(path):
    path = Path(path).resolve()
    with workshop_lock(path):
        state = read_state(path)
        rough = state["revisions"]["scene"]
        if not rough or len(state["gate_evidence"]) != 2:
            raise ValueError("Explicit acceptance of the current rough snapshot is required")
        if sha256(path / "scene.json") != rough["working_sha256"]:
            raise ValueError("Working scene changed; rough acceptance is stale")
        resolve_placements(path / "revisions" / f"{rough['number']:04}.json")
        return {"sample_review_ready": True, "rough": rough}
