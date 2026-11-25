"""Fail-closed identification and validation for staged workshops."""

import json
import os
import tempfile
import uuid
from pathlib import Path

from terrain.library import read_json

MARKER = ".terrain-staged.json"
STATE = "workshop-state.json"


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
        or state.get("stage") != "intake"
        or any(not isinstance(state.get(k), str) or not state[k] for k in
               ("name", "brief", "pending_decision"))
        or any(not isinstance(state.get(k), list) or
               any(not isinstance(v, str) or not v for v in state[k]) for k in
               ("confirmed_facts", "assumptions", "open_questions"))
        or state.get("revisions") != {"layout": None, "scene": None}
        or state.get("gate_evidence") != []
    ):
        raise ValueError(f"Invalid or unsupported staged workshop state: {path}")


def staged_root(path):
    path = Path(path).resolve()
    for parent in (path, *path.parents):
        if (parent / MARKER).exists() or (parent / STATE).exists():
            return parent
    return None


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
    raise ValueError("3D work requires an explicitly approved 2D layout revision")


def guard_workshop(path):
    path = Path(path).resolve()
    scene = read_json(path / "scene.json")
    if staged_root(path) is not None or "staged_workshop" in scene:
        read_state(path)
        raise ValueError("3D work requires an explicitly approved 2D layout revision")
