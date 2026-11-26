# terrain

Library-first, agent-driven tabletop scene design for 28–32 mm miniatures. Browse your actual meshes visually, choose an art direction, and arrange intact pieces in an editable scene. A separate deterministic OpenSCAD generator preserves the official OpenLOCK mechanical core for original additions.
Original Blender models can join a scene as clearly labelled, unindexed drafts.
Only explicit approval imports them into the local library and `assets/custom/`.

**Status: software prototype, not print-approved.** Library measurements and assembly previews do not certify connector fit, miniature clearance, stability, or printability. Slicer review and physical tests remain mandatory.

## Design an encounter together

Start a new workshop with this literal prompt in a session with the skill loaded:

> /terrain-workshop Help me design a battlefield for my next pen-and-paper session.
> Interview me in short rounds about the place, antagonist, their character and tactics,
> the party, and what should happen here. Show me distinct tactical layouts and pause
> for my decisions. Do not treat assumptions or silence as approval.

Resume in a fresh session with:

> /terrain-workshop Resume my saved workshop. Run workshop status, show the current
> stage and pending decision, and continue from the last explicitly approved revision.
> Ask which workshop only if more than one could be meant.

`workshop init` creates a fresh slug, state and journal without approving a design or
requiring the catalog to exist. `workshop status` lists saved workshops; `status
scenes/<slug>` reads the current state. At intake, discuss the brief and save a checked
2D comparison. At layout review, show it and wait for explicit approval of the exact
revision. Only then build a rough 3D layout from local assets. At rough review, inspect
play evidence and wait for exact rough acceptance. After that, show one actual-mesh
sample and ask separately whether the rest of the board matching it would be printable
in the GM's judgment. A negative, conditional or missing answer does not allow detail.
After a positive sample and current play pass, detail, checkpoint the final board, and
obtain separate finished-play and finished-visual verdicts. See
`docs/workshop-state.md` for commands and exact confirmation phrases.

The loop is **discuss → research the library → plan → build a draft → inspect → discuss**.
The agent asks focused questions instead of giving you an intake form. It connects
fiction to player choices: a villain's retreat route, an interruptible ritual, a
dangerous approach, a useful flank, or a room repurposed by its occupants. It pauses
at each approval gate before progressing. Unconfirmed ideas stay labelled as
assumptions, not decisions.

Each workshop has an editable scene and a design journal. Each checkpoint saves a new
source snapshot, the feedback that prompted it, and its change summary. The local review
page lets you browse revisions, **orbit/pan/zoom actual library geometry**, use isometric,
reverse, top and front cameras, and hide pieces to inspect interiors. Four mesh PNGs
remain available if WebGL 2 is unavailable. The 50 mm viewer grid is a reference ruler,
not an inferred asset module or game grid. Original Blender drafts can appear alongside
library pieces, in purple and explicitly unindexed until separate model approval.

The agent runs these commands on your behalf:

```bash
uv run terrain workshop init scenes/my-encounter \
  --name "The pressure chapel" --brief "A ritual inside a failing industrial shrine"

# Discuss and save a checked 2D comparison, then wait for exact 2D approval.
# Only after approval, index and inspect the library and arrange rough pieces.

uv run terrain workshop checkpoint scenes/my-encounter \
  --title "The first approach" --changes "Offset the control point and open the foreground"

# Review and explicitly accept this rough revision before building a visual sample.
```

After the sample and finished-board decisions, generate and recheck a private pack:

```bash
uv run terrain workshop status scenes/my-encounter
uv run terrain workshop handoff scenes/my-encounter --revision <finished-number> \
  --sha256 <finished-snapshot-sha256> --output-dir build/handoffs/my-encounter
uv run terrain workshop verify-handoff scenes/my-encounter \
  --pack build/handoffs/my-encounter/handoff-<zero-padded-number>
```

The separate handoff includes keyed assembly views, print table, exclusions and a
release checklist. Re-run `verify-handoff` before relying on it; changed inputs, gate
evidence, source files or pack files invalidate it. Pending release checks mean **for
slicing and verification**, not ready to print. No command here purchases, uploads,
slices, prints or heats anything. To link genuine existing physical or slicer evidence,
use `--evidence` with the local, snapshot-bound JSON described in
`docs/workshop-state.md`. The program checks file hashes, not the truth of a person's
physical test.

Open `build/workshops/my-encounter/index.html` directly in your browser. No server, CDN,
API key, external model upload, or browser network request is needed. The review embeds
private geometry, so **do not publish or share its files**.

The review page is not a second chat client. Discuss changes with the agent in your
normal conversation, using camera angles and piece IDs. You can also download feedback
notes from the page and supply them to the agent. Browser notes are not sent automatically.
Hiding pieces changes the view only, not the layout or printing quantities.

### Printing list and saved iterations

Every revision includes a visible printing table and `print-list.csv`: original source
path, required copies, recorded printed stock, remaining copies, and license. Unknown
inventory remains **unknown**, not zero. Missing hero sculpts or other unbuilt pieces stay
in the art direction, not in the printable inventory. Print the unchanged original files,
not geometry extracted from the viewer.

```text
scenes/my-encounter/
  scene.json              # Working layout, art direction, structured encounter brief
  design.md               # Decisions, assumptions, open questions, feedback, next step
  revisions/0001.json     # Saved source, feedback, change summary, journal snapshot
  revisions/0002.json
build/workshops/my-encounter/
  index.html              # Revision browser
  0001/review.html         # Interactive 3D, printing table, angles and encounter notes
  0001/print-list.csv
  0001/report.json         # Provenance, conservative bounds, overlaps, pending gates
  0001/assembly.md
  0001/iso.png             # Also reverse.png, top.png, front.png
```

Source snapshots contain references, not purchased meshes, and can be version-controlled.
Previews stay under Git-ignored `build/`. Failed rendering does not save a new revision.
To rebuild missing previews from saved revisions or reopen the revision browser:

```bash
uv run terrain workshop review scenes/my-encounter
```

Existing complete, matching artifact directories are reused. For a full fresh rendering,
pass `--output-dir build/workshops/my-encounter-rebuilt`. Outputs owned by another workshop
or incomplete/edited revision folders are not overwritten. Source files and their indexed
hashes must still match. Review pages are inspection artifacts, not collision/clearance
proof, print-ready combined models, or slicer approval.

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

The former block-based Vark props, fixed arena, and `generate-set vark_lab` command have been retired. Online discovery, automatic connector detection and automatic figure generation remain future capabilities.

An inspected example is `scenes/pressure-transept.json`; build it with `uv run terrain scene build scenes/pressure-transept.json --preview` after indexing. It is an artistic draft, roughly 240 × 320 × 79 mm, not a complete or print-approved lab. Three selected original files report non-watertight processed topology; see `scenes/README.md` and the manifest's fit notes. No automatic repair or exact Boolean union is used for previews.

## Original models in Blender

Ask the agent to model an original piece, inspect it with you, and add it to the library
**only after you approve that particular revision**. The terrain skills follow this gate.
Scene approval, silence, or a successful render never count as library approval.

```bash
# Runs a trusted local script inside Blender, starting with an empty scene.
uv run terrain custom create drafts/plinth-v1 \
  --script examples/blender/stepped_plinth.py \
  --name "Stepped plinth" --brief "An original standalone raised platform"
```

Blender is auto-detected on PATH or at `/Applications/Blender.app`; use `--blender` for
another installation. OpenSCAD still renders the neutral PNG previews. The Python script
creates mesh objects using **one coordinate unit per millimetre**. The runner saves an
editable `model.blend`, exports evaluated mesh objects with world transforms and modifiers,
and records hashes, the source script, license, and mesh diagnostics. Render-hidden objects
are excluded; scripts must convert curves/text to meshes. Scripts run as local Python,
**not in a sandbox**. Never run untrusted model-pack scripts.

Open `drafts/plinth-v1/preview/review.html`. Orbit the actual mesh and inspect the four
PNG views and `validation.json`. Unapproved custom pieces appear **purple**, labelled
**Custom · unindexed · approval pending**, with a separate quantity list and review hash.
They are not library entries or printable-inventory items. Nothing from creation or
preview is copied into `assets`.

To inspect a draft in a scene alongside purchased pieces:

```bash
uv run terrain scene add-custom scenes/my-lab.json \
  --draft drafts/plinth-v1/draft.json --id ritual-platform --at 80 40 0
uv run terrain scene build scenes/my-lab.json --preview
# Or save a normal workshop checkpoint for an interactive scene review.
```

Use `scene init ... --no-library` or `workshop init ... --no-library` for a custom-only
scene without an existing catalog. Saved workshop revisions pin draft manifests and
source hashes, rebase references, and preserve the distinction between drafts and library
assets. Keep the original draft directories to rebuild those revisions.

**After you explicitly approve the reviewed model**, the agent runs:

```bash
uv run terrain custom approve drafts/plinth-v1/draft.json --id plinth \
  --review-sha256 <manifest-hash-shown-in-review> \
  --approval "<your explicit confirmation for this revision>"
```

Approval checks the reviewed manifest and all source hashes, validates mesh topology, and
copies `model.blend`, `model.stl`, `build.py`, and `provenance.json` into
`assets/custom/plinth/`. It indexes the approved STL without replacing the purchased
library or its annotations. Approved roots are remembered during normal reindexing.
With no catalog, approval initializes a custom-only catalog. `--catalog` selects another
catalog and `--assets-root` selects another approved destination.

The command returns the indexed asset ID. The agent deliberately replaces draft references
in the working scene with this ID, retaining placement IDs and transforms. Existing
snapshots stay unchanged and still show their original unindexed drafts. Approval records
the confirmation supplied by the caller; it is a human workflow gate, not authentication.

Create revisions in new directories (`plinth-v2`, etc.). Existing drafts and approved IDs
are never overwritten. If modelling succeeds but PNG rendering fails, the draft remains;
retry with `uv run terrain custom preview drafts/plinth-v1/draft.json`.
`drafts/` and `assets/custom/` are local and Git-ignored. Library approval does not publish
anything, start printing, or approve slicer settings or physical fit. The default license
is original personal-use work without redistribution; use `--license` to record the actual
license. Purchased meshes must not be edited or copied into new original models.
The example plinth has no connectors and makes no OpenLOCK compatibility claim.

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

For the disposable macOS M0-A1 fixture, see the [offline Blender verification
recipe](examples/m0_a1/README.md). It uses only synthetic inputs and does not run an agent.

## Prompt an agent

The shared skills live in `.agents/skills/`, discovered by Maki, Pi, and Droid's compatible
skill loader:

- `terrain-workshop/SKILL.md`: adaptive encounter interviews, persistent decisions,
  visible iterations, interactive 3D review and printing lists.
- `printable-terrain/SKILL.md`: library inspection, immutable geometry, mechanical
  contracts, generation, validation and the physical-release gate.

In Droid, use `/terrain-workshop` or ask for it by name. Start a new session if a newly
added skill is not yet visible; `/skills` shows discovered skills.

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
- `src/terrain/workshop.py`: saved encounter iterations and reproducible private reviews.
- `src/terrain/custom.py`, `blender_runner.py`: original Blender drafts and explicit approval import.
- `examples/blender/`: original modelling scripts using millimetre coordinates.
- `src/terrain/review.py`, `templates/`: offline interactive WebGL review and revision browser.
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
