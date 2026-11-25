import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from terrain.cli import main
from terrain.staged import atomic_state
from terrain.workshop import init_workshop, update_workshop_state, workshop_lock, workshop_status


def test_resume_and_discovery_without_catalog(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    first = tmp_path / "scenes/first"
    init_workshop(first, tmp_path / "missing-catalog", "First", "A dark room")
    init_workshop(tmp_path / "scenes/second", None, "Second", "A bright room")
    old = workshop_status(first)
    state = {k: v for k, v in old.items() if k != "workshop"}
    updated = copy.deepcopy(state)
    updated["confirmed_facts"] = ["A tower"]
    updated["assumptions"] = ["A grid"]
    updated["open_questions"] = ["How tall?"]
    updated["pending_decision"] = "Choose the tower height"
    update_workshop_state(first, state, updated)
    assert main(["workshop", "status"]) == 0
    assert json.loads(capsys.readouterr().out)["workshops"] == ["scenes/first", "scenes/second"]
    result = subprocess.run(
        [str(Path(sys.executable).parent / "terrain"), "workshop", "status", str(first)],
        text=True, capture_output=True, check=True,
    )
    loaded = json.loads(result.stdout)
    for key in ("confirmed_facts", "assumptions", "open_questions", "pending_decision"):
        assert loaded[key] == updated[key]
    with pytest.raises(ValueError, match="changed"):
        update_workshop_state(first, state, updated)
    with pytest.raises(ValueError, match="already exists"):
        init_workshop(first, None, "Other", "Other")
    assert workshop_status(first)["pending_decision"] == "Choose the tower height"


@pytest.mark.parametrize("damage", ["none", "missing", "malformed", "wrong", "stale"])
def test_staged_operations_fail_before_tools_or_output(tmp_path, monkeypatch, damage):
    path = tmp_path / "scenes/test"
    init_workshop(path, tmp_path / "missing", "Test", "A brief")
    state_path = path / "workshop-state.json"
    before = state_path.read_bytes()
    if damage == "missing":
        state_path.unlink()
    elif damage == "malformed":
        state_path.write_text("{")
    elif damage in ("wrong", "stale"):
        state = json.loads(before)
        state["workshop_id" if damage == "wrong" else "stage"] = "other"
        state_path.write_text(json.dumps(state))
    damaged = state_path.read_bytes() if state_path.exists() else None
    def forbidden(*args, **kwargs):
        pytest.fail("guard invoked a prohibited tool")
    monkeypatch.setattr("terrain.scene.scene_catalog", forbidden)
    monkeypatch.setattr("terrain.scene.render_source", forbidden)
    monkeypatch.setattr("terrain.custom.draft_asset", forbidden)
    output = tmp_path / "output"
    scene = str(path / "scene.json")
    commands = [
        ["workshop", "checkpoint", str(path), "--output-dir", str(output),
         "--title", "T", "--changes", "C"],
        ["workshop", "review", str(path), "--output-dir", str(output)],
        ["scene", "add", scene, "--asset", "x", "--id", "x", "--at", "0", "0", "0"],
        ["scene", "add-custom", scene, "--draft", "x", "--id", "x", "--at", "0", "0", "0"],
        ["scene", "build", scene, "--output-dir", str(output)],
    ]
    original = (path / "scene.json").read_bytes()
    for command in commands:
        assert main(command) == 1
    assert not output.exists()
    assert not (path / "revisions").exists()
    assert (path / "scene.json").read_bytes() == original
    assert (state_path.read_bytes() if state_path.exists() else None) == damaged


def test_lock_and_interrupted_atomic_write(tmp_path, monkeypatch):
    path = tmp_path / "scene"
    init_workshop(path, None, "Test", "Brief")
    original = (path / "workshop-state.json").read_bytes()
    state = json.loads(original)
    with workshop_lock(path, state_update=True), pytest.raises(ValueError, match="locked"):
        update_workshop_state(path, state, state)
    def fail(*args):
        raise OSError("interrupted")
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="interrupted"):
        atomic_state(path, state)
    assert (path / "workshop-state.json").read_bytes() == original
