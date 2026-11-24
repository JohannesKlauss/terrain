---
name: printable-terrain
description: Design library-first tabletop scenes from local terrain collections, inspect real mesh contact sheets, arrange intact pieces, track print quantities, and create mechanically validated original OpenLOCK additions.
---

# Printable terrain

Work from the repository root. Default to designing scenes from the user's actual library, not generating a room of primitive blocks. Treat purchased meshes and the official OpenLOCK STLs as immutable inputs. Original genre modules may change only approved decorative regions of the official templates.

## Library-first scene workflow (default)

1. Read the scene request as an art brief. Establish the defining image, narrative, mood, focal silhouette, space available, miniature bases and movement needs. Ask about decisions that change the composition or fit.
2. Index the library with `uv run terrain library index assets/saucermen --metadata library/saucermen.json`. Purchased files are private and Git-ignored. Do not edit, upload, publish, fuse, repair or rescale them. Their notices prohibit modification and sharing. Inventory means printed copies, not owning an STL.
3. Search candidates with `uv run terrain library search "laboratory pipe"` or `--collection`. Render real candidates with `uv run terrain library preview --collection "Scif Greebles 02" --limit 0 --output-dir build/library/greebles`. Use separate output folders for selections; `--limit 0` means all matches.
4. **Open and inspect the numbered PNG contact sheets.** Initial names/categories/tags are filename or collection hints, not visual understanding. Read `selection.json` for the exact ID/hash, bounds and rights. Inspect iso/top, and add `--views iso top underside` for interfaces. Do not say a part matches a silhouette without looking at it.
5. Propose three meaningfully different compositions, not three seed variants. Explain the defining image, main asset choices, empty space, sight lines, routes and missing pieces. Design the unusual focal element first; build architecture around it. Prefer purposeful asymmetry and grouped detail over evenly spaced scatter and identical rectangular rooms.
6. Ask the user to choose a direction before a production-scale build. A clearly labelled draft may demonstrate a recommended composition. Never substitute crude primitives for a missing hero sculpt and call it finished. Record unresolved pieces in `art_direction.missing_assets`.
7. Use `terrain scene init`, `terrain scene add`, and editable scene JSON. Run `uv run terrain scene --help` and subcommand help as needed. Each placement pins a source SHA-256; if it changes, stop and review before repinning. The default anchor is XY bounds centre and lowest Z before XYZ rotation and translation. Scaling is not supported. Connector compatibility remains unknown until independently checked, even inside a nominal OpenLOCK collection.
8. Build with `uv run terrain scene build scenes/<name>.json --preview`. Inspect both `iso.png` and `top.png`. Review silhouette, coherent visual vocabulary, negative space, scene readability, actual-scale detail and support/stability concerns. Neutral mesh previews matter more than an attractive concept image.
9. Inspect `report.json`, `print-list.csv` and `assembly.md`. AABB overlap warnings are only a broad phase, not proof of collision or clearance. Unknown inventory stays null. No fit, accessibility or print approval is inferred from successful rendering. Preserve pending physical and slicer gates.
10. Refine the manifest and rerender. Deliver preview paths, asset provenance, a clear assembly plan, missing original pieces and unresolved human checks. Contact sheets and scene previews are private working artifacts, not permission to redistribute purchased work.

Store reviewed descriptions, visual-review status, tags and printed counts under `assets` in `library/saucermen.json`, keyed by source-relative asset ID; reindex to apply them. Never invent printed inventory, unit confirmation or connector measurements. Do not infer units from appearance.

The available first-stage tools index STL/3MF, search annotated text, render contact sheets and assemble rigid-body scenes. They do **not** implement online downloading, automatic connector detection, Blender sculpting, model training or figure generation. Identify these as gaps rather than pretending they exist. New original work can share broad motifs, not reproduce restricted sculpts. Future online sourcing must track each model's actual license; free download does not imply remix rights. External 3D services need explicit permission before uploading private assets.

## Defaults

- Units: millimetres
- New original OpenLOCK geometry grid: 25.4 mm. Library collections retain their native dimensions and interfaces; do not force them onto this grid.
- E floor: 50.8 × 50.8 mm
- Low walls: 25.4 mm high on a 12.7 mm base
- Process: FDM, PLA parts, 0.4 mm nozzle, 0.2 mm layers
- Seed: 42 when not specified
- Usage: personal/noncommercial; preserve each asset's license. CC BY-NC 4.0 applies to the official Printable Scenery templates and their derivatives, not the purchased library.

Ask for missing requirements that change fit or geometry. Do not silently scale finished OpenLOCK parts, alter ports, add top pins, introduce magnets, or add new connector systems.

The official E-floor has a documented topology discrepancy: openscad-mcp 0.6.1 reports 49 open edges in both the untouched official STL and generated plain STL, while processed Trimesh topology is watertight. Preserve the baseline warning and require slicer verification; do not claim universal manifold validity.

Official port-mouth support bars must be removed after printing without damaging the inner retention dividers. For the E-floor coupon, test the 19.05 and 31.75 mm candidate centers instead of assuming the midpoint. Rigid-body clip interference is not a fit certificate for a flexing retention clip. Never edit official ports to force a software PASS.

## Source of truth

- `src/terrain.scad`: public model entry point
- `src/core/`: mechanical constants, official-template adapters and protected regions
- `src/styles/`: original bounded genre decoration
- `assets/openlock/provenance.json`: source, license and immutable hashes
- `assets/saucermen/`: private, immutable purchased meshes
- `library/saucermen.json`: editable collection/asset metadata and printed inventory
- `src/terrain/library.py`, `visual.py`, `scene.py`: catalog, previews and scene assembly
- `scenes/`: editable scene briefs and hash-pinned placements
- `tests/`: source contract and exported-artifact regression gates
- `build/`: disposable previews, STL/3MF exports and reports

Core mechanical parts are `e_floor`, `a_wall`, `doorway`, `l_corner`, `clip`, `coupon` and `assembly`. Original fixture genres are `plain`, `mork_borg`, `cyberpunk` and `expanse`. The block-based Vark scene and fixed set generator have been removed. Do not recreate them as the default design method.

## Required workflow for new original mechanical geometry

1. Read the mechanical contract and relevant existing model before changing anything.
2. Confirm `openscad --version` and `uv run terrain --help`. When MCP is connected, also call `openscad__check_openscad`.
3. Edit original parametric source, never an exported STL/3MF as a substitute for source. Importing an intact licensed mesh into a scene is placement, not original modelling.
4. Run the focused failing test first when adding behavior, then make it pass.
5. Generate the requested model:
   `uv run terrain generate e_floor --genre mork_borg --seed 42 --preview`
6. Use `uv run terrain generate --all --preview` only for the full MVP matrix.
7. Inspect diagnostics. OpenSCAD may exit zero after an assertion, missing module or empty result; process exit status alone is not a pass.
8. Measure the exported mesh and check expected bounds, positive volume, one intended solid, consistent winding and watertight/manifold topology.
9. Render isometric/top previews for appearance and section/underside views for interfaces. With MCP use `render`, `measure`, `validate`, `check` and `export_model`; inspect every `errors`, `warnings` and `hints` field.
10. Check representative assemblies for connector alignment, forbidden interference, insertion access and standing/doorway clearance. Recheck all genres against the same protected geometry.
11. Run `uv run terrain validate <artifacts...>` and `uv run pytest` before reporting success.
12. Inspect the model in the real slicer before printing. A software mesh gate does not prove fit, support needs, strength or print success.

Never autonomously start a printer or heating command. A person must inspect slicer layers, material, temperatures and physical bed clearance.

## Decoration rules

- Keep connector ports, insertion paths, contact planes and protected standing/access masks unchanged.
- Use deterministic seeds; identical part, genre and seed must reproduce geometry.
- Keep standing areas substantially flat and test 25, 27 and 32 mm bases.
- Keep original additions inside the permitted decoration envelope. Do not copy game art, logos, typography, emblems, deck plans or third-party sculpts. Intact placement of user-owned meshes belongs to the separate library workflow and retains the source license.
- Use broad original motifs: cracked masonry for Mörk Borg, urban utility surfaces for cyberpunk, and restrained industrial deck systems for Expanse-style terrain.

## Response report

List source paths, preview/export paths, measured dimensions, checks run, warnings and unresolved physical tests. Clearly distinguish software-validated from physically printed. If any required check fails, stop and fix the source rather than declaring the model printable.

The connector coupon and a two-floor/wall/doorway/corner assembly must be physically printed and fit-tested before batch production. Record that human gate as pending until the user supplies the result.
