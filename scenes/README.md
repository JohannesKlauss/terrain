# Scene design, not another fixed tile set

Scene JSON files reference private library assets by relative ID and SHA-256. They
contain no purchased mesh data. Run the library index command before building.
Coordinate paths to the catalog are relative to the scene JSON, so the repository
can move; reindex after moving the private library.

## Collaborative encounter workshops

Use `.agents/skills/terrain-workshop/SKILL.md` to develop a scene through short interviews
and visible drafts. A workshop is a directory, unlike the standalone example below:

```bash
uv run terrain workshop init scenes/my-encounter --name "My encounter" --brief "The defining scene"
```

The agent maintains `scene.json` and `design.md`, then uses `terrain workshop checkpoint`
to save numbered source snapshots in `revisions/`. Each records encounter context,
villains, objectives, spatial choices, assumptions, feedback and a change summary.
Private interactive reviews and printing lists go under `build/workshops/my-encounter/`.
Open its `index.html` to browse iterations, rotate the 3D scene, hide pieces, inspect
four fixed views, and see which original files and quantities to print.

Do not add generated review HTML to this directory: it embeds private purchased geometry.
Keep only source JSON and the design journal here. The page does not send feedback to the
agent automatically; discuss it in chat or supply the downloaded notes.

## Vark laboratory: three directions

These are composition proposals, not print-approved designs. No new monster or
hero sculpt is being claimed.

1. **The pressure transept.** A process chamber treated like a cathedral: a strong
   axial threshold opens onto an asymmetric bank of industrial services. Leave
   one route broad and empty; place the control point off-axis. Existing
   industrial architecture supplies the silhouette, rather than a generic
   central cylinder with decorative spheres.
2. **The breach at the sump.** An L-shaped maintenance route leads past a cramped
   control station into a wider chamber. Frame a deliberately empty breach as the
   narrative focus. A future original rift sculpt would occupy that reserved
   space, not be replaced with a crude placeholder declared complete.
3. **The extraction gantry.** A vertically organized chamber with overhead
   machinery and a low service route. This has the most dramatic potential
   silhouette, but needs extra investigation of supported stacking, access,
   visibility and physical stability before it is a sensible first assembly.

The first trial uses the pressure-transept direction as a **draft** to exercise
asset selection, neutral previews, placement transforms and print accounting.
The user still chooses the final artistic direction before production.

## Fit is collection-specific

The inspected catalog measures tunnel frames at approximately 80 mm module
increments. Do not force them onto the official E-floor's 50.8 mm footprint,
rescale them, or assume their interfaces match another collection. An assembly
can illustrate placement without proving the parts connect or stand securely.

Use `art_direction.missing_assets` for genuinely missing narrative pieces. Use
the report's pending gates and overlap warnings to track unresolved interfaces.

The first source inspection found non-watertight processed/welded topology in
`Frame 2x1 A`, `Frame 2x1 D`, and `Bulkhead 24 (Doorway Closed)`. An exact OpenSCAD
Boolean-render experiment also reported open-mesh errors. The originals were not
repaired or changed. The draft uses raw-surface inspection previews, not a
Boolean-unioned production mesh; slicer verification remains required.
