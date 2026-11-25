"""Sample and finished-board gate records, bound to immutable workshop artifacts."""

import html
import json
import math
import os
import re
import tempfile
from pathlib import Path

from terrain.library import read_json, sha256


def quality(state):
    return state.get(
        "quality",
        {
            "history": [],
            "sample": None,
            "sample_verdict": None,
            "finished_play": None,
            "finished_visual": None,
        },
    )


def validate_quality(root, state):
    q = quality(state)
    if (
        not isinstance(q, dict)
        or set(q) != {"history", "sample", "sample_verdict", "finished_play", "finished_visual"}
        or not isinstance(q["history"], list)
    ):
        raise ValueError("Invalid quality gate state")
    for item in q["history"]:
        if not isinstance(item, dict) or set(item) != {"number", "sha256"}:
            raise ValueError("Invalid quality history")
        n = item["number"]
        if (
            type(n) is not int
            or n < 1
            or sha256(root / "quality" / f"{n:04}.json") != item["sha256"]
        ):
            raise ValueError("Quality history changed")


def commit_quality(root, state, q, event):
    folder = root / "quality"
    folder.mkdir(exist_ok=True)
    existing = [int(p.stem) for p in folder.glob("*.json") if p.stem.isdigit()]
    number = max(existing, default=0) + 1
    record = {"schema_version": 1, "workshop_id": state["workshop_id"], **event}
    dest = folder / f"{number:04}.json"
    with dest.open("x") as stream:
        json.dump(record, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    q["history"] = [*q["history"], {"number": number, "sha256": sha256(dest)}]
    state["quality"] = q
    from terrain.staged import atomic_state

    atomic_state(root, state)


def sample_current(root, state):
    """Validate the saved sample and the original rough source, not a cached verdict."""
    from terrain.scene import resolve_placements

    q = quality(state)
    sample = q["sample"]
    if not isinstance(sample, dict):
        raise ValueError("No sample has been built")
    rough = sample["rough"]
    accepted = sample["rough_acceptance"]
    if (
        state["stage"] != "3d"
        or rough["layout_sha256"] != state["revisions"]["layout"]["sha256"]
        or accepted
        != {
            "type": "rough_acceptance",
            "workshop_id": state["workshop_id"],
            "revision": rough["number"],
            "sha256": rough["sha256"],
            "confirmation": f"I accept rough revision {rough['number']} for sample review",
        }
    ):
        raise ValueError("Sample does not have current accepted rough evidence")
    original = root / "revisions" / f"{rough['number']:04}.json"
    if sha256(original) != rough["sha256"]:
        raise ValueError("Accepted rough snapshot changed")
    resolve_placements(original)
    scene_path = root / "samples" / f"{sample['number']:04}.json"
    if sha256(scene_path) != sample["sha256"]:
        raise ValueError("Sample source changed")
    resolve_placements(scene_path)
    for name, digest in sample["artifacts"].items():
        if not re.fullmatch(r"(iso|top|seated)\.png|index\.html", name):
            raise ValueError("Invalid sample artifact")
        if sha256(Path(sample["output"]) / name) != digest:
            raise ValueError("Sample preview changed")
    if set(sample["artifacts"]) != {"iso.png", "top.png", "seated.png", "index.html"}:
        raise ValueError("Sample preview is incomplete")
    working = read_json(root / "scene.json")
    rough_scene = read_json(original)
    if working.get("rough") != rough_scene.get("rough"):
        raise ValueError("Play inputs changed since the sample")
    old = {p["id"]: p for p in rough_scene["placements"]}
    current = {p["id"]: p for p in working.get("placements", [])}
    for identity in sample["ids"]:
        if old.get(identity) != current.get(identity) or identity not in current:
            raise ValueError("Sample placement changed")
    return sample


def sample_pass(root, state):
    sample = sample_current(root, state)
    verdict = quality(state)["sample_verdict"]
    expected = f"I would print the board if it matched sample {sample['number']}"
    if (
        not isinstance(verdict, dict)
        or verdict.get("type") != "approved"
        or (
            verdict.get("sample_sha256") != sample["sha256"]
            or verdict.get("confirmation") != expected
        )
    ):
        raise ValueError("Current sample requires an explicit positive visual verdict")
    return sample


def final_current(root, state):
    from terrain.scene import resolve_placements

    sample = sample_pass(root, state)
    current = state["revisions"]["scene"]
    if not current or current["number"] <= sample["rough"]["number"]:
        raise ValueError("Create a fresh finished-board checkpoint after sample approval")
    if not current or sha256(root / "scene.json") != current["working_sha256"]:
        raise ValueError("Finished working scene changed; checkpoint again")
    snapshot = root / "revisions" / f"{current['number']:04}.json"
    if sha256(snapshot) != current["sha256"]:
        raise ValueError("Finished snapshot changed")
    resolve_placements(snapshot)
    return current


def status(root, state):
    q = quality(state)
    result = {
        "rough_acceptance": "pending",
        "sample_verdict": "pending",
        "finished_play": "pending",
        "finished_visual": "pending",
        "handoff": False,
    }
    rough_accepted = len(state["gate_evidence"]) == 2
    if rough_accepted:
        ref = state["revisions"]["scene"]
        try:
            from terrain.scene import resolve_placements

            if not ref or sha256(root / "scene.json") != ref["working_sha256"]:
                raise ValueError("Working scene changed")
            resolve_placements(root / "revisions" / f"{ref['number']:04}.json")
            result["rough_acceptance"] = "accepted"
        except (OSError, ValueError, KeyError):
            result["rough_acceptance"] = "stale"
    elif q["sample"]:
        result["rough_acceptance"] = "accepted (historical)"
    if q["sample_verdict"]:
        result["sample_verdict"] = q["sample_verdict"]["type"]
        try:
            sample_current(root, state)
        except (OSError, ValueError, KeyError):
            result["sample_verdict"] = "stale"
    for field in ("finished_play", "finished_visual"):
        if q[field]:
            result[field] = "approved"
            try:
                current = final_current(root, state)
                if q[field].get("sha256") != current["sha256"]:
                    result[field] = "stale"
            except (OSError, ValueError, KeyError):
                result[field] = "stale"
    result["handoff"] = result["finished_play"] == result["finished_visual"] == "approved"
    return result


def build_sample(
    root,
    output,
    focal,
    architecture,
    miniature,
    reference,
    intent,
    missing,
    distance_mm=800,
    openscad="openscad",
):
    from terrain.scene import assemble_scene, resolve_placements
    from terrain.staged import read_state
    from terrain.visual import render_seated
    from terrain.workshop import prepare_output, workshop_lock

    root = Path(root).resolve()
    ids = [focal, architecture, miniature]
    if len(set(ids)) != 3 or any(
        not isinstance(s, str) or not s.strip() for s in [*ids, reference, intent, missing]
    ):
        raise ValueError(
            "Three distinct placements, reference, intent and missing items are required"
        )
    if not math.isfinite(distance_mm) or not 400 <= distance_mm <= 2000:
        raise ValueError("Seated camera distance must be between 400 and 2000 mm")
    with workshop_lock(root):
        state = read_state(root)
        if len(state["gate_evidence"]) != 2:
            raise ValueError("Current rough acceptance is required before sample work")
        rough = state["revisions"]["scene"]
        if sha256(root / "scene.json") != rough["working_sha256"]:
            raise ValueError("Working scene changed since rough acceptance")
        original = root / "revisions" / f"{rough['number']:04}.json"
        scene, _, resolved = resolve_placements(original)
        selected = [p for p in scene["placements"] if p["id"] in ids]
        if len(selected) != 3:
            raise ValueError("Sample roles must name three existing rough placements")
        if len(scene["placements"]) <= 3:
            raise ValueError("The sample must be a subset, not the whole board")
        proxies = set(scene.get("rough", {}).get("proxies", []))
        sample_scene = {**scene, "placements": selected}
        folder = root / "samples"
        folder.mkdir(exist_ok=True)
        number = (
            max((int(p.stem) for p in folder.glob("*.json") if p.stem.isdigit()), default=0) + 1
        )
        sample_path = folder / f"{number:04}.json"
        with sample_path.open("x") as stream:
            json.dump(sample_scene, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
        output = Path(output).resolve()
        prepare_output(root, output, [(sample_path, sample_scene)])
        destination = output / f"sample-{number:04}"
        if destination.exists():
            raise ValueError("Sample output already exists")
        with tempfile.TemporaryDirectory(dir=output, prefix=".sample-") as tmp:
            tmp = Path(tmp)
            assembled = assemble_scene(
                sample_path, tmp, preview=True, views=["iso", "top"], openscad=openscad
            )
            # Bounds of the exact transformed meshes, not a guessed board centre.
            bounds = read_json(assembled["report"])["bounds_mm"]
            center = [(bounds[0][axis] + bounds[1][axis]) / 2 for axis in range(3)]
            render_seated(assembled["source"], tmp / "seated.png", center, distance_mm, openscad)
            actual = ", ".join(p["id"] for p in selected if p["id"] not in proxies) or "none"
            proxy = ", ".join(p["id"] for p in selected if p["id"] in proxies) or "none"
            page = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Sample review</title></head>
<body><h1>Actual-mesh sample {number}, not the finished board</h1>
<p>Focal: {html.escape(focal)}; adjacent architecture: {html.escape(architecture)};
miniature scale cue: {html.escape(miniature)}</p>
<p>Actual meshes: {html.escape(actual)}. Simplified/proxy meshes: {html.escape(proxy)}.</p>
<p>Agreed reference: {html.escape(reference)}</p><p>Simplified intent: {html.escape(intent)}</p>
<p>Missing: {html.escape(missing)}</p>
<p>Neutral perspective camera distance: {distance_mm:g} mm.
Inspect this alongside the other views.</p>
<img src="seated.png" alt="Seated table distance perspective">
<img src="iso.png" alt="Isometric view"><img src="top.png" alt="Top view">
<p>Would you print the board if the rest matched this sample?
This is not a custom import approval or a billable commitment.</p>
</body></html>"""
            (tmp / "index.html").write_text(page)
            tmp.rename(destination)
        q = quality(state)
        sample = {
            "number": number,
            "sha256": sha256(sample_path),
            "rough": rough,
            "rough_acceptance": state["gate_evidence"][1],
            "ids": ids,
            "focal_proxy": focal in proxies,
            "output": str(destination),
            "artifacts": {
                name: sha256(destination / name)
                for name in ("iso.png", "top.png", "seated.png", "index.html")
            },
            "reference": reference,
            "intent": intent,
            "missing": missing,
            "distance_mm": distance_mm,
        }
        q.update(sample=sample, sample_verdict=None, finished_play=None, finished_visual=None)
        commit_quality(root, state, q, {"type": "sample", "sample": sample})
        return {"sample": sample, "review": str(destination / "index.html")}


def decide_sample(root, number, digest, verdict, confirmation, mismatch=""):
    from terrain.staged import read_state
    from terrain.workshop import workshop_lock

    root = Path(root).resolve()
    with workshop_lock(root):
        state = read_state(root)
        sample = sample_current(root, state)
        if sample["number"] != number or sample["sha256"] != digest:
            raise ValueError("Sample reference is stale")
        if verdict == "approved":
            if sample["focal_proxy"]:
                raise ValueError("A proxy focal piece cannot be approved as finished")
            if confirmation != f"I would print the board if it matched sample {number}":
                raise ValueError("Exact positive sample confirmation is required")
        elif verdict in ("rejected", "inconclusive"):
            if not mismatch.strip() or not confirmation.strip():
                raise ValueError(
                    "A negative or inconclusive response needs a mismatch and response"
                )
        else:
            raise ValueError("Unknown sample verdict")
        q = quality(state)
        record = {
            "type": verdict,
            "sample_sha256": digest,
            "confirmation": confirmation,
            "mismatch": mismatch,
        }
        q.update(sample_verdict=record, finished_play=None, finished_visual=None)
        commit_quality(root, state, q, {"type": "sample_verdict", "verdict": record})
        return record


def decide_finished(root, revision, digest, kind, confirmation):
    from terrain.layout import verify_revision
    from terrain.rough import evidence
    from terrain.scene import resolve_placements
    from terrain.staged import read_state
    from terrain.workshop import workshop_lock

    root = Path(root).resolve()
    with workshop_lock(root):
        state = read_state(root)
        current = final_current(root, state)
        if (current["number"], current["sha256"]) != (revision, digest):
            raise ValueError("Finished verdict must identify the current snapshot")
        q = quality(state)
        if kind == "play":
            phrase = f"I approve finished play revision {revision}"
            snapshot = root / "revisions" / f"{revision:04}.json"
            scene, catalog, resolved = resolve_placements(snapshot)
            play = evidence(
                scene, catalog, resolved, verify_revision(root, state["revisions"]["layout"])
            )
            if (
                play["material_changes"]
                or play["unresolved_features"]
                or any(gap["status"] != "resolved" for gap in play["gaps"])
            ):
                raise ValueError("Finished play evidence has blocking issues")
            record = {"sha256": digest, "confirmation": confirmation, "evidence": play}
            q["finished_play"] = record
            q["finished_visual"] = None
        elif kind == "visual":
            phrase = f"I approve finished board revision {revision}"
            if not q["finished_play"] or q["finished_play"]["sha256"] != digest:
                raise ValueError("Fresh finished play approval is required first")
            record = {"sha256": digest, "confirmation": confirmation}
            q["finished_visual"] = record
        else:
            raise ValueError("Unknown finished gate")
        if confirmation != phrase:
            raise ValueError(f"Explicit confirmation required: {phrase}")
        commit_quality(root, state, q, {"type": f"finished_{kind}", "record": record})
        return record
