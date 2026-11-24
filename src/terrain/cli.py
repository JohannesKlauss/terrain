import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from terrain.build import ROOT, BuildError, generate_model, generate_mvp
from terrain.catalog import named_spec, part_contract
from terrain.library import index_library, load_catalog, search_assets
from terrain.mesh import MeshRules, inspect_mesh
from terrain.scene import add_placement, assemble_scene, init_scene
from terrain.visual import preview_library
from terrain.workshop import checkpoint, init_workshop, review_workshop

DEFAULT_CATALOG = ROOT / "build" / "library" / "catalog.json"


def create_parser():
    parser = argparse.ArgumentParser(prog="terrain")
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate")
    generate.add_argument("part", nargs="?")
    generate.add_argument("--all", action="store_true", dest="all_parts")
    generate.add_argument("--genre", default="plain")
    generate.add_argument("--seed", type=int, default=42)
    generate.add_argument("--output-dir", type=Path, default=ROOT / "build")
    generate.add_argument("--openscad", default="openscad")
    generate.add_argument("--preview", action="store_true")

    library = commands.add_parser("library", help="Index and visually browse local model files")
    library_commands = library.add_subparsers(dest="action", required=True)
    index = library_commands.add_parser("index")
    index.add_argument("root", type=Path)
    index.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    index.add_argument("--metadata", type=Path)
    for action in ("search", "preview"):
        sub = library_commands.add_parser(action)
        sub.add_argument("query", nargs="?", default="")
        sub.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
        sub.add_argument("--collection")
        sub.add_argument("--limit", type=int, default=24)
        if action == "preview":
            sub.add_argument("--output-dir", type=Path, default=ROOT / "build/library/selection")
            sub.add_argument(
                "--views", nargs="+", choices=("iso", "top", "underside"), default=("iso", "top")
            )
            sub.add_argument("--openscad", default="openscad")

    scene = commands.add_parser("scene", help="Arrange intact library assets using JSON scenes")
    scene_commands = scene.add_subparsers(dest="action", required=True)
    init = scene_commands.add_parser("init")
    init.add_argument("path", type=Path)
    init.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    init.add_argument("--name", required=True)
    init.add_argument("--brief", required=True)
    add = scene_commands.add_parser("add")
    add.add_argument("path", type=Path)
    add.add_argument("--asset", required=True)
    add.add_argument("--id", required=True)
    add.add_argument("--at", nargs=3, type=float, required=True)
    add.add_argument("--rotate", nargs=3, type=float, default=(0, 0, 0))
    add.add_argument("--role", default="architecture")
    build = scene_commands.add_parser("build")
    build.add_argument("path", type=Path)
    build.add_argument("--output-dir", type=Path)
    build.add_argument("--preview", action="store_true")
    build.add_argument("--openscad", default="openscad")

    workshop = commands.add_parser(
        "workshop", help="Iterate on encounters with saved drafts and local interactive 3D review"
    )
    workshop_commands = workshop.add_subparsers(dest="action", required=True)
    start = workshop_commands.add_parser("init")
    start.add_argument("path", type=Path)
    start.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    start.add_argument("--name", required=True)
    start.add_argument("--brief", required=True)
    for action in ("checkpoint", "review"):
        sub = workshop_commands.add_parser(action)
        sub.add_argument("path", type=Path)
        sub.add_argument("--output-dir", type=Path)
        sub.add_argument("--openscad", default="openscad")
        if action == "checkpoint":
            sub.add_argument("--title", required=True)
            sub.add_argument("--changes", required=True)
            sub.add_argument("--feedback", default="")

    validate = commands.add_parser("validate")
    validate.add_argument("artifacts", nargs="+", type=Path)
    validate.add_argument("--allow-degenerate", type=int)
    return parser


def run_generate(args):
    if args.all_parts == bool(args.part):
        print("generate requires a part or --all", file=sys.stderr)
        return 2
    if args.all_parts:
        results = generate_mvp(args.output_dir, args.openscad, args.preview, args.seed)
    else:
        spec = named_spec(args.part, args.genre, args.seed)
        results = [generate_model(spec, args.output_dir, args.openscad, args.preview)]
    summary = {
        "generated": len(results),
        "manifests": [str(item["manifest"]) for item in results],
    }
    print(json.dumps(summary))
    return 0


def run_library(args):
    if args.action == "index":
        result = index_library(args.root, args.catalog, args.metadata)
        print(json.dumps(result, default=str))
        return 1 if result["failed"] else 0
    catalog = load_catalog(args.catalog)
    assets = search_assets(catalog, args.query, args.collection, args.limit)
    if args.action == "search":
        result = {"matched": len(assets), "assets": assets}
    else:
        result = preview_library(catalog, assets, args.output_dir, args.views, args.openscad)
    print(json.dumps(result, indent=2, default=str))
    return 0


def run_scene(args):
    if args.action == "init":
        result = init_scene(args.path, args.catalog, args.name, args.brief)
    elif args.action == "add":
        result = add_placement(
            args.path,
            args.asset,
            args.id,
            args.at,
            args.rotate,
            args.role,
        )
    else:
        output = args.output_dir or ROOT / "build/scenes" / args.path.stem
        result = assemble_scene(args.path, output, args.preview, args.openscad)
    print(json.dumps(result, indent=2, default=str))
    return 0


def validation_rules(path, degenerate_override):
    try:
        rules = part_contract(path.name.split("-", 1)[0]).rules()
    except ValueError:
        rules = MeshRules()
    if degenerate_override is not None:
        rules = replace(rules, allowed_degenerate=degenerate_override)
    return rules


def run_workshop(args):
    if args.action == "init":
        result = init_workshop(args.path, args.catalog, args.name, args.brief)
    else:
        output = args.output_dir or ROOT / "build/workshops" / args.path.resolve().name
        if args.action == "checkpoint":
            result = checkpoint(
                args.path, output, args.title, args.changes, args.feedback, args.openscad
            )
        else:
            result = review_workshop(args.path, output, args.openscad)
    print(json.dumps(result, indent=2, default=str))
    return 0


def run_validate(args):
    reports = [
        inspect_mesh(path, validation_rules(path, args.allow_degenerate)) for path in args.artifacts
    ]
    print(json.dumps(reports, indent=2))
    return 0 if all(report["valid"] for report in reports) else 1


def main(argv=None):
    args = create_parser().parse_args(argv)
    try:
        if args.command == "generate":
            return run_generate(args)
        if args.command == "library":
            return run_library(args)
        if args.command == "scene":
            return run_scene(args)
        if args.command == "workshop":
            return run_workshop(args)
        return run_validate(args)
    except (BuildError, ValueError, OSError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
