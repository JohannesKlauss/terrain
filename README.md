# terrain

Library-first, agent-driven tabletop scene design for 28–32 mm miniatures. Browse your actual meshes visually, choose an art direction, and arrange intact pieces in an editable scene. A separate deterministic OpenSCAD generator preserves the official OpenLOCK mechanical core for original additions.

**Status: software prototype, not print-approved.** Library measurements and assembly previews do not certify connector fit, miniature clearance, stability, or printability. Slicer review and physical tests remain mandatory.

## Start with your library

Purchased files stay local in `assets/saucermen/`, which is Git-ignored. Indexing never edits or uploads them. Their included notices prohibit modification and sharing: this workflow only places intact meshes, does not fuse them, and does not export combined production meshes.

```bash
uv sync --dev
uv run terrain library index assets/saucermen --metadata library/saucermen.json
uv run terrain library search "laboratory pipe"
uv run terrain library preview --collection "Scif Greebles 02" --limit 0 \
  --output-dir build/library/greebles
```

The private catalog is `build/library/catalog.json`. Preview commands render real geometry in isometric and top views, create numbered PNG contact sheets (12 assets/page), and write a `selection.json` mapping labels to exact source IDs, hashes, dimensions, and permissions. Add `--views iso top underside` for interfaces. Preview only the candidates you need; `--limit 0` selects every match. No Blender, database service, web server, external model API, or training is needed.

Search uses filenames, categories, descriptions and tags, not an embedding model. Initial collection tags are broad hints, **not visual judgments**. The agent must inspect the contact sheets before choosing pieces.

### Editable annotations and printed inventory

`library/saucermen.json` stores collection hints and per-asset annotations separately from source meshes. Edit its `assets` object, then rerun the index command:

```json
{
  "assets": {
    "Scif Greebles 02/Console.stl": {
      "description": "Describe what the rendered geometry actually shows",
      "tags": ["control station"],
      "visual_review": "reviewed",
      "printed": 2
    }
  }
}
```

Merge this into the existing metadata; do not replace the collection settings. `printed` counts physical copies, not digital ownership. Omit it when unknown. Unknown inventory produces blank CSV counts and JSON `null`, never an invented zero. Unit scale and connector metadata remain explicitly unverified unless independently confirmed. STL is unitless; the initial millimetre assumption is never silently corrected by scaling.

Reindexing refreshes changed/deleted files, reuses unchanged measurements, and reapplies annotations. It remembers the previous annotation file when `--metadata` is omitted. Invalid models remain in the catalog with an error and cause a nonzero index exit. ZIP files are not extracted. STL and 3MF are supported, including transformed/repeated 3MF scene instances and conversion of declared 3MF units into millimetres. This interprets the file's units; it is not permission to resize a part.

### Compose a scene

The agent proposes three contrasting compositions from your description and inspected library, then assembles the chosen direction. A scene is editable JSON, not a hard-coded genre function:

```bash
uv run terrain scene init scenes/my-lab.json --name "The pressure chapel" \
  --brief "A forbidden laboratory built inside a ruined shrine"
uv run terrain scene add scenes/my-lab.json \
  --asset "Scif Greebles 02/Console.stl" --id control-station \
  --at 80 40 0 --rotate 0 0 90 --role objective
uv run terrain scene build scenes/my-lab.json --preview
```

Edit `art_direction` to record the mood, focal point, composition, alternatives and missing assets. Placements pin the source SHA-256; changed sources require deliberate review and repinning. Position/rotation are rigid-body transforms only. `bottom_center` anchors the source mesh at its XY bounds centre and lowest Z before rotation and translation; use `source` to retain the original coordinate frame. Scaling and unknown placement fields are rejected.

`build/scenes/<scene-name>/` contains:

- `iso.png`, `top.png`: neutral geometry previews when `--preview` is requested.
- `assembly.scad`: private inspection-only references to intact assets, not a production plate.
- `report.json`: world bounds, placements, per-asset licenses, quantities, pending gates, and broad-phase AABB overlap warnings.
- `print-list.csv`: required copies, recorded printed stock, and remaining copies.
- `assembly.md`: asset IDs, positions, rotations and unresolved checks.

The 3MF preview adapter may create a private flattened STL cache, preserving instance transforms. This is not a repaired or production-approved model. Originals stay unchanged. No assembly receives the official templates' license by inheritance. AABB overlap is not an exact collision test, and no connector alignment is inferred from a pack name.

The former block-based Vark props, fixed arena, and `generate-set vark_lab` command have been retired. Online discovery, Blender-based original modelling, automatic connector detection and figure generation are later stages, not implemented capabilities of this milestone.

An inspected example is `scenes/pressure-transept.json`; build it with `uv run terrain scene build scenes/pressure-transept.json --preview` after indexing. It is an artistic draft, roughly 240 × 320 × 79 mm, not a complete or print-approved lab. Three selected original files report non-watertight processed topology; see `scenes/README.md` and the manifest's fit notes. No automatic repair or exact Boolean union is used for previews.

## Quick start

Requirements: macOS, `uv`, and OpenSCAD with the Manifold backend. The verified configuration uses OpenSCAD 2026.10.11 and openscad-mcp 0.6.1.

```bash
brew install --cask openscad@snapshot
uv sync --dev

uv run terrain generate coupon --preview
uv run terrain generate e_floor --genre mork_borg --seed 42 --preview
uv run terrain generate --all --preview
uv run pytest
```

Outputs are written under `build/<genre>/` as STL, 3MF, PNG when requested, and a JSON manifest. `build/` is disposable and Git-ignored. Every manifest records the model specification, dimensions/topology reports, OpenSCAD version, source/input SHA-256, license, and `physical_validation: pending`.

Validate existing artifacts:

```bash
uv run terrain validate build/plain/*.stl build/plain/*.3mf
uv run ruff check .
uv run ruff format --check .
```

Use `generate --all` only for the complete mechanical/style regression matrix, not as the default creative workflow.

## Prompt an agent

The shared skill is `.agents/skills/printable-terrain/SKILL.md`; both Maki and Pi discover project `.agents/skills` directories. It contains the mechanical contract, generation loop, validation requirements, and physical-release gate.

Example prompt:

> Use the printable-terrain skill. Design a forbidden laboratory inside a ruined shrine using my Saucermen collection. Inspect actual mesh contact sheets, propose three distinct compositions, and assemble the chosen direction with a strong focal silhouette and open movement routes. Keep purchased meshes intact, list missing pieces instead of substituting generic blocks, and report unresolved compatibility and print checks.

### Maki

Project MCP configuration: `.maki/mcp.toml`. Trust the project when prompted, run `/reload`, and inspect `/mcp`. The server is restricted to this repository and uses the pinned `openscad-mcp@0.6.1` command.

### Pi

Project MCP configuration: `.pi/mcp.json`. Current Pi versions provide built-in MCP support. An installed `pi-mcp-adapter` can replace built-in session MCP behavior, so either configure that adapter or deliberately use built-in MCP; no global package change is required by this repository. Run `/reload` after changing configuration.

The MCP integration exposes 12 tools for rendering, measurement, geometry/printability checks, assembly checks, and export. No custom Maki Lua plugin or Pi TypeScript extension is required.

## MVP catalog

| Part ID | Purpose | Export contract |
|---|---|---|
| `e_floor` | 2×2-inch E floor | 50.8 × 50.8 × 7 mm, one solid |
| `a_wall` | Separate low A wall | 50.8 × 12.7 × 25.4 mm, one solid |
| `doorway` | Fixed-open doorway | Same envelope; accepts a 32 mm base gauge |
| `l_corner` | Low L corner derived from the official column | 11.538 × 11.538 × 25.4 mm, one solid |
| `clip` | Official OpenLOCK clip 5.4 | Unmodified geometry, one solid |
| `coupon` | Two cropped port stubs plus a separate clip | Three solids in a print layout |
| `assembly` | Four floors, wall, doorway and corner | Seven solids for inspection, not a print plate |

Genre IDs are `plain`, `mork_borg`, `cyberpunk`, and `expanse`. These small original surface modules remain mechanical fixtures and possible starting points for original additions, not the scene's primary visual vocabulary. Generation is deterministic by part, genre, and seed. Decoration is subtractive and confined to approved upper/surface regions; connector occupancy is regression-tested.

The mechanical fixture assembly uses a 0.01 mm presentation gap to preserve independent watertight solids. Export individual original parts for printing. Do not treat its combined assembly STL as a production plate.

## Source layout

- `src/terrain.scad`: public OpenSCAD entry point; accepts `part`, `genre`, and `seed` overrides.
- `src/core/mechanical.scad`: shared dimensions, official floor/clip adapters, and coupon.
- `src/core/parts.scad`: walls, doorway, low corner, and assembly.
- `src/styles/styles.scad`: original bounded genre modules and dispatch.
- `src/terrain/library.py`: immutable library indexing, annotations, provenance and search.
- `src/terrain/visual.py`: real mesh thumbnails and contact sheets.
- `src/terrain/scene.py`: hash-pinned scene placement, previews and print lists.
- `src/terrain/`: mechanical catalog, OpenSCAD build pipeline, mesh inspection, and CLI.
- `library/saucermen.json`: editable metadata, not copies of purchased meshes.
- `scenes/`: editable scene briefs and placements referencing the private library.
- `assets/openlock/provenance.json`: immutable source hashes, attribution, license, and known vendor topology findings.
- `tests/`: asset, catalog, source, geometry, reproducibility, doorway-gauge, export, and failure-path tests.

## Validation and known limitations

The normal gate checks source diagnostics, expected millimetre extents, positive volume, component count, consistent winding, processed/welded watertight topology, and zero-area-facet budgets. It also checks 3MF after re-import, byte-deterministic STL regeneration, protected connector occupancy, all genre envelopes, the 32 mm doorway gauge, and known-bad input rejection.

### Official E-floor topology discrepancy

With openscad-mcp 0.6.1, the **untouched official** `E-TRP-v7.6.stl` reports 49 open edges and 19 zero-area triangles. The generated plain STL reports the identical baseline. Trimesh's processed/welded topology reports watertight. This discrepancy is recorded in provenance and export warnings rather than hidden. The per-E-floor budget permits 20 zero-area facets because 3MF coordinate serialization can add one numerical degenerate; any excess fails validation. Verify the actual artifact in the target slicer.

### Supports and clip fit

The official templates include sacrificial support bars at the outer port mouths. Remove those external bars after printing, while retaining the inner dividers that provide clip retention. Follow Printable Scenery's [support-removal guide](https://www.printablescenery.com/2024/11/30/removing-supports-from-the-openlock-ports/).

Rigid-body clip interference checks are **not** a fit certificate for a flexing retention clip. For this E template, use the coupon to test the quarter-edge positions at 19.05 and 31.75 mm rather than assuming the 25.4 mm midpoint. Do not alter the official ports to force a software PASS. The coupon includes both candidate regions.

Use rigid material for bases. Evaluate PETG for clips if repeated flexing makes PLA unsuitable. No autonomous printer or heater control is configured.

## Required physical-release gate

1. Inspect the coupon and parts in the real slicer, including layers, overhangs, scale, and material profile.
2. Print the coupon. Remove only the external sacrificial bars and test both candidate port centers.
3. Check insertion, audible/tactile retention, removal, flush contact faces, surrounding-tile access, and repeated cycles.
4. Print two E floors, clips, a wall, doorway, and corner, including decorated examples from each genre and intended original additions.
5. Test 25, 27, and 32 mm bases on standing areas, through doorways, and along each scene's routes. Check fragility, freestanding stability, line-of-sight cover, and support cleanup.
6. Do not batch-generate for production until these physical checks pass and the manifests' pending status is updated deliberately.

## License and attribution

Purchased Saucermen files retain their own personal-use-only restrictions. Their included notices prohibit sharing, modification and sale. The private library and previews are not project assets to publish. New original work may use broad design vocabulary, not copied vendor sculpts. Online discoveries must retain their own licenses, with explicit permission for any remix.

OpenLOCK templates and derived connector geometry are by **Printable Scenery — https://www.printablescenery.com/**, licensed under **CC BY-NC 4.0**. Preserve attribution and noncommercial restrictions. Commercial use requires a separate license from Printable Scenery. See `assets/openlock/provenance.json` and the [developer information](https://www.printablescenery.com/2017/04/26/openlock-developer-information/).

Genre geometry is original and uses broad gothic, urban, and industrial motifs. Do not add copied game art, logos, proprietary typography, emblems, deck plans, or third-party sculpts. Public branded distribution and commercial use require a separate licensing review.
