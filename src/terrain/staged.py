"""Fail-closed identification and validation for staged workshops."""

import json
import os
import tempfile
import uuid
from contextvars import ContextVar
from functools import wraps
from pathlib import Path

from terrain.layout import verify_revision
from terrain.library import read_json

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
        or state["revisions"]["scene"] is not None
        or not isinstance(state.get("gate_evidence"), list)
    ):
        raise ValueError(f"Invalid or unsupported staged workshop state: {path}")
    reference = state["revisions"]["layout"]
    evidence = state["gate_evidence"]
    if state["stage"] == "intake":
        if reference is not None or evidence:
            raise ValueError("Intake state cannot contain layout approval")
        return
    record = verify_revision(path, reference)
    if record.get("workshop_id") != state["workshop_id"]:
        raise ValueError("Layout belongs to a different workshop")
    if state["stage"] == "layout_review":
        if evidence:
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
    if not option or evidence != [expected] or option not in record["checks"]:
        raise ValueError("Missing or stale explicit layout approval")
    checks = record["checks"][option]
    if checks["footprint"] != "fits" or any(
        r["status"] == "unverified" for r in checks["interactions"]
    ):
        raise ValueError("Approved layout has unchecked footprint or interactions")
    if not any(r["status"] != "blocked" and r["from_entry"] for r in checks["routes"]):
        raise ValueError("Approved layout has no usable route")


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


def guard_workshop(path):
    path = Path(path).resolve()
    scene = read_json(path / "scene.json")
    if staged_root(path) is not None or "staged_workshop" in scene:
        state = read_state(path)
        if scene.get("staged_workshop") != state["workshop_id"]:
            raise ValueError("Staged scene belongs to a different workshop")
        if state["stage"] != "3d":
            raise ValueError("3D work requires an explicitly approved 2D layout revision")
