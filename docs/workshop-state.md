# Staged workshop and 2D contract

## Sample and finished-board decisions

After accepting the exact rough checkpoint, build one local sample from three existing,
distinct rough placements (focal piece, adjacent architecture and miniature-scale cue):

```bash
uv run terrain workshop sample-build scenes/<slug> --output-dir /private/review \
  --focal <id> --architecture <id> --miniature <id> \
  --reference "agreed reference" --intent "simplifications" --missing "missing details"
```

The result gives a sample number, digest and local review page. The page distinguishes
actual meshes from rough proxies and records the agreed reference, simplifications and
missing details. The seated perspective defaults to an 800 mm camera distance; adjust
`--distance-mm` to the agreed distance. It is not a physical fit or sightline certificate.
Ask separately: “Would you print the board if the rest matched this sample?”

Record a positive answer using `sample-verdict` with `--sample N`, `--sha256` from the
sample and `--verdict approved --confirmation "I would print the board if it matched sample N"`.
Record a negative or inconclusive answer with `--verdict rejected` or `inconclusive`,
the actual answer in `--confirmation`, and one mismatch in `--mismatch`. Neither
silence nor conditional agreement is approval. A proxy focal piece cannot pass. A
failed sample does not erase the accepted rough layout. These decisions do not approve
`terrain custom approve` and do not authorize purchases, printing or billable work.

Only after sample approval may staged placements be added as detail. Checkpoint the
finished board, then use `finished-play` and `finished-visual` with its `--revision N`
and `--sha256`, respectively confirming `I approve finished play revision N` and
`I approve finished board revision N`. Play evidence is recomputed for that snapshot.
`workshop status` reports rough, sample, finished play, finished visual and handoff
separately. Handoff is true only while both finished verdicts, the sample and their
source bytes remain current. A changed rough input or sample placement requires a new
rough/sample pass; material changes may require a new 2D revision. A changed finished
scene requires a new checkpoint and fresh finished verdicts. The numbered quality
history preserves decisions even when newer gates replace them. Local preview images
are not a substitute for the hashes or for physical inspection.

`terrain workshop init scenes/<slug> --name ... --brief ...` creates a staged workshop
without inspecting a catalog or invoking modelling tools. `terrain workshop status`
lists candidates; `status scenes/<slug>` resumes facts, assumptions, questions, stage,
pending decision, exact current revision and evidence. `design.md` is a readable
journal, not approval. Legacy unmarked workshops still support 3D history; their
journal is not a staged approval.

## 2D comparison

Start from `examples/workshop-2d-plan.json`. Adapt it to the discussion; never treat
example dimensions as confirmed. The plan specifies one shared top-down coordinate
system, north up, millimetres, with x right and y down. Each of two or three different
options has named rectangular features: entry, reveal, cover, interaction, height band,
and stairs. Set `blocks` for obstacles that physically occupy space. Give each interaction
an `approach_at` point. Routes are orthogonal centre-line polylines with a declared
width; start or end at an entry. An alternate requires two routes. An intentional
choke must be labelled and discussed. The grid count, game pitch, miniature scale, base
diameter, viewer ruler and library pitch are separate fields. The outer dimensions,
table footprint limit, confirmed statements, assumptions, and physical unknowns must
be explicit. Base dimensions without confirmation are provisional.
List every expected base diameter in `base_diameters_mm`; the concentric circles show
them and checks use the largest. The legacy singular field identifies one displayed base.

Set `selected_option` to null before a choice, or the selected option ID after the GM
chooses. Selection alone is not approval. Describe `changes`, `clarified`, and the exact
`pending_decision` in every revision. Use stable feature IDs and edit a copy of the plan
when a user asks to move or combine features. Save it with:

```bash
uv run terrain workshop layout scenes/<slug> --plan /path/to/plan.json --expect-revision 0
```

Use the current number instead of 0 for later revisions. The command checks the plan,
writes immutable `layouts/NNNN.json` and one `layouts/NNNN.svg` comparison, then atomically
updates state. A stale writer is rejected. Failed or interrupted saves may leave an
unreferenced numbered pair, never a committed approval; do not overwrite these files.
The returned checks report footprint and route clearance, and whether each interaction
has an entry-connected, nonblocked route ending within one base diameter. Clearance is
the minimum of declared route width and twice the centre line's distance from the
outer boundary and blocking rectangles. Less than one base is blocked, less than 1.25
bases is tight, otherwise feasible. These simplified sketch checks do not account for
actual meshes, other bases, vertical clearance, overhangs, walls not drawn as blockers,
or physical fit. Mark provisional inputs and unknowns; never claim a fit certificate.

Show the sheet and checks, explain material changes and ask the pending question. A pick
or refinement does not authorize 3D. After a selected current option has a fitting
footprint, at least one nonblocked entry route and all interaction checks connected,
request the following *unconditional* confirmation from the GM, substituting the actual
number and option ID:

```text
I approve 2D revision 1 option direct for 3D
```

Only if the GM supplies that exact statement, record it with the current returned digest:

```bash
uv run terrain workshop approve-layout scenes/<slug> --revision 1 \
  --sha256 <current-revision-sha256> \
  --confirmation "I approve 2D revision 1 option direct for 3D"
```

The application records the statement, not the identity of its author. The guard binds
the current workshop UUID, option, revision, plan bytes, checked evidence and SVG bytes.
It rejects stale, wrong-workshop, changed or missing artifacts and generic or conditional
assent. Saving any new 2D revision clears approval and blocks staged 3D again. In
particular, a material library-fit compromise requires a new revision and explicit
approval before 3D work resumes. Physical, print, and library-import approvals are
separate gates.

Use `terrain.workshop.update_workshop_state(path, expected, updated)` for discussion
fields only. The API takes the workshop lock and compares the expected prior state; it
cannot change the gate or identity. Do not directly edit state. Unknown versions,
missing files and identity mismatches fail closed. State and its staged markers must
not be deleted to bypass recovery. Standalone scene tools remain independent.

## Rough 3D and sample review

Once the exact current 2D option is approved, search the owned catalog and inspect real
local contact sheets before choosing parts. Keep sources intact, pin their hashes and use
rigid transforms. Add `height_mm` to each 2D height and stairs feature before approval;
it is the intended top elevation in millimetres. Missing heights remain unresolved, not
an implicit zero. A height change beyond the stated tolerance requires a new 2D revision.

Place pieces in `scene.json` and supply a `rough` object there. The agent manages this;
it is not a new user-facing questionnaire. Example:

```json
{
  "bindings": {"cover": "cover-piece", "altar": "altar-piece",
               "dais": "dais-piece", "steps": "steps-piece"},
  "tolerance_mm": 1,
  "clearance_height_mm": 30,
  "proxies": ["cover-piece"],
  "occupied_bases": [{"at": [100, 110], "diameter_mm": 25}],
  "gaps": [],
  "sourcing": [],
  "physical_unknowns": ["Hand access, material fit and stair traversal"]
}
```

Bindings map approved 2D feature IDs to actual placement IDs. Check all key cover,
interaction, height and stairs features; missing bindings stay unresolved. For each
blocking gap record `role`, `envelope_interface`, `quantity`, `substitutes`,
`decision_deadline` and `status`. For each read-only sourcing candidate record
`vendor_link`, `price_date`, `contents`, `size_interface_evidence`, `license`, `unknowns`,
`recommendation` and `fallback`. Candidates are not owned or fit-confirmed. Do not buy,
download, import, remodel restricted assets or upload private geometry without permission.
Proxy IDs identify placements that stand in for unresolved pieces, not stock or visual
proof. Confirmed printed quantities come only from inventory annotations; null is
unknown, zero is confirmed zero, and shortfall is computed only for known quantities.

`terrain workshop checkpoint` uses actual transformed source triangles to project each
placement to XY and test a swept base along the approved routes. The route result is
conservative: any intersecting projection is a possible blocker, even when part of the
mesh is above the clearance band. The report records the base size, clearance band,
tolerance, optional occupied-base intersections and feature world bounds. It does not
prove exact collisions, occlusion, stair function, hand access, sight lines, physical fit
or visual quality. AABB overlaps are broad-phase warnings, not collision evidence.
The interaction check reports the nearest projected obstacle and clearance after
subtracting the expected base radius, including the explicitly positioned occupied
bases. Cover/reveal checks list XY projections crossing an entry-to-feature line; these
are not 3D line-of-sight judgments. Human hand size and vertical access remain unknown.
Inspect the private labelled top and iso views, and explain unknowns to the GM.
`report.json`, `assembly.md` and `print-list.csv` are internal feasibility artifacts;
the local review summarizes their evidence, not a release verdict.

A placement outside its approved feature envelope, a changed approved height, a
previously clear route obstructed by mesh projection, or an exceeded outer footprint
invalidates 2D approval and records the difference. Further staged rough operations
are blocked until a *new* 2D revision is approved. Discuss the smallest viable change,
including when a conservative projection needs closer physical inspection. Source
changes, placement changes, and new snapshots invalidate their old rough acceptance.
Failed renders leave the prior committed snapshot and pending decision intact.

Only after reviewing the exact current rough snapshot and resolving blocking gaps ask
for the user's unconditional statement `I accept rough revision N for sample review`.
If supplied, record it using:

```bash
uv run terrain workshop accept-rough scenes/<slug> --revision N --sha256 <snapshot-sha256> \
  --confirmation "I accept rough revision N for sample review"
uv run terrain workshop sample-review scenes/<slug>
```

The second command checks whether sample review is unlocked; it does not create samples,
approve appearance, approve printing, or release a design. Both commands recheck the
current snapshot, scene bytes and source hashes. Approval records a statement, not the
identity of its author. Rebuilt or old review files never constitute acceptance.
