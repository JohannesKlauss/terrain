"""Fail-closed identification and validation for staged workshops."""

import json
import os
import tempfile
import uuid
from contextvars import ContextVar
from functools import wraps
from pathlib import Path

from terrain.layout import verify_revision
from terrain.library import read_json, sha256
from terrain.quality import validate_quality

MARKER = ".terrain-staged.json"
STATE = "workshop-state.json"
HELD_WORKSHOP = ContextVar("held_workshop", default=None)


def atomic_state(path, state):
    """Replace a state record atomically; the caller must hold the workshop lock."""
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix=".state-", dir=path)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(state, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path / STATE)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def new_state(path, name, brief):
    return {
        "schema_version": 1,
        "workshop_id": str(uuid.uuid4()),
        "slug": path.name,
        "name": name,
        "brief": brief,
        "confirmed_facts": [],
        "assumptions": [],
        "open_questions": [],
        "stage": "intake",
        "pending_decision": (
            "Discuss the defining scene, antagonist, player choices, and table constraints."
        ),
        "revisions": {"layout": None, "scene": None},
        "gate_evidence": [],
    }


def read_state(path):
    path = Path(path).resolve()
    marker = read_json(path / MARKER)
    state = read_json(path / STATE)
    validate_state(path, marker, state)
    return state


def validate_state(path, marker, state):
    validate_quality(path, state)
    if (
        marker.get("schema_version") != 1
        or not isinstance(marker.get("workshop_id"), str)
        or not marker["workshop_id"]
        or state.get("schema_version") != 1
        or state.get("workshop_id") != marker["workshop_id"]
        or state.get("slug") != path.name
        or state.get("stage") not in ("intake", "layout_review", "3d")
        or any(
            not isinstance(state.get(k), str) or not state[k]
            for k in ("name", "brief", "pending_decision")
        )
        or any(
            not isinstance(state.get(k), list)
            or any(not isinstance(v, str) or not v for v in state[k])
            for k in ("confirmed_facts", "assumptions", "open_questions")
        )
        or not isinstance(state.get("revisions"), dict)
        or set(state["revisions"]) != {"layout", "scene"}
        or not isinstance(state.get("gate_evidence"), list)
    ):
        raise ValueError(f"Invalid or unsupported staged workshop state: {path}")
    reference = state["revisions"]["layout"]
    evidence = state["gate_evidence"]
    if state["stage"] == "intake":
        if reference is not None or evidence or state["revisions"]["scene"] is not None:
            raise ValueError("Intake state cannot contain layout approval")
        return
    record = verify_revision(path, reference)
    if record.get("workshop_id") != state["workshop_id"]:
        raise ValueError("Layout belongs to a different workshop")
    if state["stage"] == "layout_review":
        if evidence or state["revisions"]["scene"] is not None:
            raise ValueError("Pending layout cannot carry approval")
        return
    option = record["plan"].get("selected_option")
    expected = {
        "type": "layout_approval",
        "workshop_id": state["workshop_id"],
        "revision": reference["number"],
        "sha256": reference["sha256"],
        "sheet_sha256": reference["sheet_sha256"],
        "option": option,
        "confirmation": f"I approve 2D revision {reference['number']} option {option} for 3D",
    }
    if not option or not evidence or evidence[0] != expected or option not in record["checks"]:
        raise ValueError("Missing or stale explicit layout approval")
    checks = record["checks"][option]
    if checks["footprint"] != "fits" or any(
        r["status"] == "unverified" for r in checks["interactions"]
    ):
        raise ValueError("Approved layout has unchecked footprint or interactions")
    if not any(r["status"] != "blocked" and r["from_entry"] for r in checks["routes"]):
        raise ValueError("Approved layout has no usable route")
    rough = state["revisions"]["scene"]
    if rough is None:
        if len(evidence) != 1:
            raise ValueError("Rough acceptance has no current snapshot")
        return
    if (
        not isinstance(rough, dict)
        or set(rough) != {"number", "sha256", "working_sha256", "layout_sha256"}
        or type(rough["number"]) is not int
        or rough["number"] < 1
    ):
        raise ValueError("Invalid rough snapshot reference")
    if rough["layout_sha256"] != reference["sha256"]:
        raise ValueError("Rough snapshot belongs to another 2D revision")
    snapshot = path / "revisions" / f"{rough['number']:04}.json"
    if sha256(snapshot) != rough["sha256"]:
        raise ValueError("Rough snapshot changed")
    if len(evidence) > 2:
        raise ValueError("Invalid rough acceptance evidence")
    if len(evidence) == 2:
        expected_rough = {
            "type": "rough_acceptance",
            "workshop_id": state["workshop_id"],
            "revision": rough["number"],
            "sha256": rough["sha256"],
            "confirmation": f"I accept rough revision {rough['number']} for sample review",
        }
        if evidence[1] != expected_rough:
            raise ValueError("Invalid or stale rough acceptance")


def staged_root(path):
    path = Path(path).resolve()
    for parent in (path, *path.parents):
        if (parent / MARKER).exists() or (parent / STATE).exists():
            return parent
    return None


def scene_operation(function):
    """Hold the same lock as gate changes throughout a staged 3D operation."""

    @wraps(function)
    def guarded(path, *args, **kwargs):
        root = staged_root(path)
        if root is None or HELD_WORKSHOP.get() == root:
            return function(path, *args, **kwargs)
        from terrain.workshop import workshop_lock

        with workshop_lock(root, state_update=True):
            if function.__name__ in ("add_placement", "add_custom_placement"):
                state = read_state(root)
                if len(state["gate_evidence"]) == 2 or state.get("quality", {}).get("sample"):
                    from terrain.quality import sample_pass

                    sample_pass(root, state)
            return function(path, *args, **kwargs)

    return guarded


def guard_scene(path):
    """Reject 3D operations on staged working scenes and their snapshots."""
    path = Path(path).resolve()
    root = staged_root(path)
    scene = read_json(path)
    marker = scene.get("staged_workshop")
    if root is None and marker is None:
        return
    if root is None:
        raise ValueError("Staged scene is missing its workshop state")
    state = read_state(root)
    if marker != state["workshop_id"]:
        raise ValueError("Staged scene belongs to a different workshop or is missing its marker")
    if state["stage"] != "3d":
        raise ValueError("3D work requires an explicitly approved 2D layout revision")
    if path.parent == root / "samples" and (
        len(state["gate_evidence"]) != 2
        or sha256(root / "scene.json") != state["revisions"]["scene"]["working_sha256"]
    ):
        raise ValueError("A current rough acceptance is required for sample work")
    if path == root / "scene.json" and scene.get("placements"):
        from terrain.scene import resolve_placements
        from terrain.workshop import check_material_change

        _, catalog, resolved = resolve_placements(path)
        if not scene.get("rough"):
            layout = verify_revision(root, state["revisions"]["layout"])["plan"]
            selected = next(o for o in layout["options"] if o["id"] == layout["selected_option"])
            ids = {placement["id"] for placement in scene["placements"]}
            scene = {
                **scene,
                "rough": {
                    "bindings": {f["id"]: f["id"] for f in selected["features"] if f["id"] in ids},
                    "tolerance_mm": 0,
                    "clearance_height_mm": layout["dimensions"]["mini_scale"],
                    "gaps": [],
                    "sourcing": [],
                    "proxies": [],
                    "physical_unknowns": ["Provisional clearance band and unbound features"],
                },
            }
        check_material_change(root, state, scene, catalog, resolved)


def guard_workshop(path):
    path = Path(path).resolve()
    scene = read_json(path / "scene.json")
    if staged_root(path) is not None or "staged_workshop" in scene:
        state = read_state(path)
        if scene.get("staged_workshop") != state["workshop_id"]:
            raise ValueError("Staged scene belongs to a different workshop")
        if state["stage"] != "3d":
            raise ValueError("3D work requires an explicitly approved 2D layout revision")
