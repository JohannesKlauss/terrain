"""Private, snapshot-bound workshop handoffs and independent release evidence."""

import csv
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from terrain.layout import verify_revision
from terrain.library import read_json, sha256, source_path, write_json
from terrain.quality import commit_quality, final_current, quality
from terrain.rough import evidence as play_evidence
from terrain.scene import assemble_scene, resolve_placements
from terrain.staged import read_state
from terrain.workshop import prepare_output, workshop_lock

CHECKS = (
    "rights_units",
    "miniature_clearance",
    "stability",
    "interfaces",
    "slicer_profile",
    "physical_tests",
    "openlock_coupon",
    "openlock_assembly",
)


def requires_openlock_checks(resolved):
    for _, asset, _, _ in resolved:
        connectors = asset.get("connectors")
        if not isinstance(connectors, dict):
            return True
        system = connectors.get("system")
        if not isinstance(system, str) or system.strip().lower() in ("", "unknown"):
            return True
        if "openlock" in json.dumps(connectors).lower():
            return True
    return False


def approved_final(root, state):
    """Recheck current inputs, exact confirmations and their immutable event records."""
    ref = final_current(root, state)
    q = quality(state)
    events = {}
    for item in q["history"]:
        event = read_json(root / "quality" / f"{item['number']:04}.json")
        if event.get("workshop_id") != state["workshop_id"]:
            raise ValueError("Quality evidence belongs to another workshop")
        events[event.get("type")] = event
    for name, key in (
        ("sample", "sample"),
        ("sample_verdict", "verdict"),
        ("finished_play", "record"),
        ("finished_visual", "record"),
    ):
        if events.get(name, {}).get(key) != q.get(name):
            raise ValueError(f"Missing or stale {name} history")
    for kind in ("play", "visual"):
        record = q[f"finished_{kind}"]
        phrase = (
            f"I approve finished play revision {ref['number']}"
            if kind == "play"
            else f"I approve finished board revision {ref['number']}"
        )
        if not isinstance(record, dict) or (
            record.get("sha256") != ref["sha256"] or record.get("confirmation") != phrase
        ):
            raise ValueError(f"Current finished {kind} approval is required")
    snapshot = root / "revisions" / f"{ref['number']:04}.json"
    scene, catalog, resolved = resolve_placements(snapshot)
    play = play_evidence(
        scene, catalog, resolved, verify_revision(root, state["revisions"]["layout"])
    )
    if play != q["finished_play"]["evidence"]:
        raise ValueError("Finished play evidence changed; recheck and approve it")
    return ref, snapshot, scene, catalog, resolved, play


def release_evidence(path, workshop_id, snapshot_sha, needs_openlock):
    """Validate explicit local evidence references; never infer a physical result."""
    supplied = read_json(path) if path else {}
    if supplied and (
        supplied.get("schema_version") != 1
        or supplied.get("workshop_id") != workshop_id
        or supplied.get("snapshot_sha256") != snapshot_sha
        or not isinstance(supplied.get("checks"), dict)
    ):
        raise ValueError("Release evidence must identify this workshop and finished snapshot")
    checks = supplied.get("checks", {})
    if set(checks) - set(CHECKS):
        raise ValueError("Unknown release evidence check")
    result = {}
    for name in CHECKS:
        item = checks.get(name)
        required = needs_openlock or not name.startswith("openlock_")
        if item is None:
            result[name] = {"status": "pending" if required else "not applicable", "evidence": []}
            continue
        if not isinstance(item, dict) or item.get("status") not in ("pending", "verified"):
            raise ValueError(f"Invalid release check: {name}")
        links = item.get("evidence", [])
        if not isinstance(links, list):
            raise ValueError(f"Invalid release evidence links: {name}")
        if item["status"] == "verified" and (
            not links or not isinstance(item.get("note"), str) or not item["note"].strip()
        ):
            raise ValueError(f"Verified {name} needs a note and local evidence")
        for link in links:
            if not isinstance(link, dict) or set(link) != {"path", "sha256"}:
                raise ValueError(f"Invalid release evidence link: {name}")
            evidence_path = Path(link["path"])
            if not evidence_path.is_absolute() or not evidence_path.is_file():
                raise ValueError(f"Release evidence is missing: {name}")
            if sha256(evidence_path) != link["sha256"]:
                raise ValueError(f"Release evidence changed: {name}")
        result[name] = {"status": item["status"], "note": item.get("note", ""), "evidence": links}
    return result


def label_view(path, name, placements):
    with Image.open(path) as image:
        image = image.convert("RGB")
    lines = [f"{name.upper()} - finished snapshot; not physical release approval"]
    lines.extend(f"{p['id']}: {p['position_mm']} mm" for p in placements)
    header = 24 + 18 * len(lines)
    labelled = Image.new("RGB", (max(500, image.width), image.height + header), "white")
    labelled.paste(image, (0, header))
    draw = ImageDraw.Draw(labelled)
    font = ImageFont.load_default(size=12)
    for index, line in enumerate(lines):
        draw.text((6, 6 + index * 18), line, font=font, fill="#172332")
    labelled.save(path)


def inventory(scene, catalog, resolved, play):
    proxies = set(play["proxy_placements"])
    counts = Counter(asset["id"] for p, asset, _, _ in resolved if p["id"] not in proxies)
    assets = {asset["id"]: asset for _, asset, _, _ in resolved}
    rows, excluded = [], []
    stock = scene.get("iteration", {}).get("printed_inventory", {})
    for identity, count in counts.items():
        asset = assets[identity]
        name = asset.get("license", {}).get("name", "unknown")
        draft = asset.get("library_status") == "custom_unindexed"
        if draft or not isinstance(name, str) or name.strip().lower() in ("", "unknown"):
            excluded.append(
                {
                    "asset": identity,
                    "required": count,
                    "reason": "unapproved draft" if draft else "unknown license",
                }
            )
            continue
        printed = stock.get(identity)
        rows.append(
            {
                "asset": identity,
                "source": str(source_path(catalog, asset)),
                "acquisition": asset.get("source_url") or "unknown",
                "version_or_sha256": asset["sha256"],
                "size_mm": asset["extents_mm"],
                "units": asset.get("units", "unknown"),
                "units_confirmed": asset.get("units_confirmed", False),
                "license": asset["license"],
                "required": count,
                "physical_stock": printed,
                "outstanding": None if printed is None else max(0, count - printed),
            }
        )
    excluded += [
        {"placement": p, "reason": "simplified proxy, not printable stock"} for p in proxies
    ]
    return rows, excluded


def handoff(root, output, revision, digest, evidence_path=None, openscad="openscad"):
    root, output = Path(root).resolve(), Path(output).resolve()
    with workshop_lock(root):
        state = read_state(root)
        ref, snapshot, scene, catalog, resolved, play = approved_final(root, state)
        if (ref["number"], ref["sha256"]) != (revision, digest):
            raise ValueError("Handoff must identify the current finished snapshot and digest")
        catalog_path = (
            (snapshot.parent / scene["catalog"]).resolve() if scene.get("catalog") else None
        )
        catalog_digest = sha256(catalog_path) if catalog_path else None
        openlock = requires_openlock_checks(resolved)
        checks = release_evidence(evidence_path, state["workshop_id"], ref["sha256"], openlock)
        rows, excluded = inventory(scene, catalog, resolved, play)
        prepare_output(root, output, [(snapshot, scene)])
        destination = output / f"handoff-{ref['number']:04}"
        if destination.exists():
            raise ValueError("Handoff output already exists; choose a fresh output directory")
        with tempfile.TemporaryDirectory(prefix=".handoff-", dir=output) as temporary:
            stage = Path(temporary)
            assembled = assemble_scene(
                snapshot, stage, preview=True, openscad=openscad, views=("top", "iso")
            )
            # The generic scene list includes rough proxies and unknown-license models.
            # It is not a release inventory and must not accompany this pack.
            (stage / "print-list.csv").unlink()
            report = read_json(assembled["report"])
            report["print_list"] = rows
            report["excluded_from_print_table"] = excluded
            report["previews"] = [str(destination / Path(p).name) for p in report["previews"]]
            write_json(assembled["report"], report)
            # These are temporary preview inputs, not production models or handoff artifacts.
            (stage / "assembly.scad").unlink()
            (stage / "assembly.md").unlink()
            if (stage / "cache").exists():
                shutil.rmtree(stage / "cache")
            for name in ("top", "iso"):
                label_view(stage / f"{name}.png", name, scene["placements"])
            fields = (
                "asset",
                "source",
                "acquisition",
                "version_or_sha256",
                "size_mm",
                "units",
                "units_confirmed",
                "license",
                "required",
                "physical_stock",
                "outstanding",
            )
            with (stage / "print-table.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for row in rows:
                    writer.writerow(
                        {
                            k: json.dumps(v, ensure_ascii=False)
                            if isinstance(v, (list, dict))
                            else v
                            for k, v in row.items()
                        }
                    )
            notes = scene.get("handoff", {})
            if not isinstance(notes, dict):
                raise ValueError("Scene handoff notes must be an object")
            lines = [
                f"# Assembly for finished revision {ref['number']}",
                "",
                "Private inspection only; use original source files, not this assembly.",
                "Views: top.png and iso.png, labelled by placement ID.",
                "Coordinates are millimetres; rotations are XYZ degrees. Follow the keyed order.",
                "",
            ]
            for i, (p, asset, _, _) in enumerate(resolved, 1):
                lines.append(
                    f"{i}. {p['id']} ({asset['id']}): {p['position_mm']} mm, "
                    f"rotation {p.get('rotation_deg', [0, 0, 0])}; "
                    f"role {p.get('role', 'unknown')}; "
                    f"connector {json.dumps(asset.get('connectors', 'unknown'))}."
                )
            lines += [
                "",
                "## Handedness, removability and nonprinted components",
                *[
                    f"- {key}: {json.dumps(notes.get(key, 'unknown'), ensure_ascii=False)}"
                    for key in ("handedness", "removable", "nonprinted", "connector_notes")
                ],
                "",
                "## Heights, landing steps, gaps and outside acquisition",
                json.dumps(
                    {
                        "features": play["feature_measurements"],
                        "gaps": play["gaps"],
                        "sourcing": scene["rough"]["sourcing"],
                        "physical_unknowns": play["physical_unknowns"],
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                "",
                "## Not printable inventory",
                json.dumps(excluded, indent=2),
            ]
            (stage / "handoff-assembly.md").write_text("\n".join(lines) + "\n")
            complete = not excluded and all(
                v["status"] in ("verified", "not applicable") for v in checks.values()
            )
            checklist = {
                "status": "evidence recorded" if complete else "pending",
                "instruction": "For slicing and verification, not ready to print. "
                "No automatic printing or production authorization.",
                "checks": checks,
            }
            write_json(stage / "release-checklist.json", checklist)
            checklist_lines = [
                "# Release evidence checklist",
                "",
                checklist["instruction"],
                "",
            ]
            for name, item in checks.items():
                checklist_lines.append(f"- {name}: {item['status']} - {item.get('note', '')}")
                for link in item["evidence"]:
                    checklist_lines.append(f"  - {link['path']} (SHA-256 {link['sha256']})")
            if excluded:
                checklist_lines.append(
                    "- Unprintable or missing inputs remain; see handoff assembly."
                )
            (stage / "release-checklist.md").write_text("\n".join(checklist_lines) + "\n")
            manifest = {
                "schema_version": 1,
                "workshop_id": state["workshop_id"],
                "revision": ref,
                "catalog_sha256": catalog_digest,
                "release": checklist,
                "print_table": rows,
                "excluded": excluded,
                "source_report_sha256": sha256(assembled["report"]),
                "artifacts": {
                    name: sha256(stage / name)
                    for name in (
                        "top.png",
                        "iso.png",
                        "print-table.csv",
                        "handoff-assembly.md",
                        "release-checklist.json",
                        "release-checklist.md",
                        "report.json",
                    )
                },
            }
            write_json(stage / "handoff.json", manifest)
            # Recheck after rendering, before publishing the directory.
            if approved_final(root, read_state(root))[0] != ref:
                raise ValueError("Finished snapshot changed during handoff")
            if catalog_path and sha256(catalog_path) != catalog_digest:
                raise ValueError("Catalog changed during handoff")
            release_evidence(evidence_path, state["workshop_id"], ref["sha256"], openlock)
            stage.rename(destination)
        state["pending_decision"] = (
            "Verify the handoff and address the release checklist before any production decision."
        )
        commit_quality(
            root,
            state,
            quality(state),
            {
                "type": "handoff",
                "path": str(destination),
                "snapshot_sha256": ref["sha256"],
                "manifest_sha256": sha256(destination / "handoff.json"),
            },
        )
        return {"handoff": str(destination), "revision": ref, "release": checklist}


def verify_handoff(root, pack):
    root, pack = Path(root).resolve(), Path(pack).resolve()
    with workshop_lock(root):
        state = read_state(root)
        ref, snapshot, scene, _, _, _ = approved_final(root, state)
        manifest = read_json(pack / "handoff.json")
        if manifest.get("workshop_id") != state["workshop_id"] or manifest.get("revision") != ref:
            raise ValueError("Handoff belongs to a different or stale finished board")
        catalog_path = (
            (snapshot.parent / scene["catalog"]).resolve() if scene.get("catalog") else None
        )
        if manifest.get("catalog_sha256") != (sha256(catalog_path) if catalog_path else None):
            raise ValueError("Handoff catalog changed")
        recorded = any(
            read_json(root / "quality" / f"{item['number']:04}.json")
            == {
                "schema_version": 1,
                "workshop_id": state["workshop_id"],
                "type": "handoff",
                "path": str(pack),
                "snapshot_sha256": ref["sha256"],
                "manifest_sha256": sha256(pack / "handoff.json"),
            }
            for item in quality(state)["history"]
        )
        if not recorded:
            raise ValueError("Handoff manifest is not recorded in this workshop")
        names = {
            "top.png",
            "iso.png",
            "print-table.csv",
            "handoff-assembly.md",
            "release-checklist.json",
            "release-checklist.md",
            "report.json",
        }
        if set(manifest.get("artifacts", {})) != names:
            raise ValueError("Handoff artifact list is incomplete")
        for name, digest in manifest["artifacts"].items():
            if sha256(pack / name) != digest:
                raise ValueError(f"Handoff artifact changed: {name}")
        for item in manifest["release"]["checks"].values():
            for link in item.get("evidence", []):
                if sha256(link["path"]) != link["sha256"]:
                    raise ValueError("Release evidence changed")
        return {"valid": True, "revision": ref, "release": manifest["release"]["status"]}
