# Staged workshop and 2D contract

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
