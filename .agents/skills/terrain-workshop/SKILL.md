---
name: terrain-workshop
description: Interview the user about a pen-and-paper encounter, turn story and antagonist choices into playable terrain, and iterate together using saved layouts, local interactive 3D reviews, multiple camera angles, and per-iteration printing lists. Use for collaborative scenery design, encounter battlefields, or resuming a terrain workshop.
---

# Terrain workshop

Be a collaborative encounter designer, not a questionnaire followed by a final render.
Use a research → plan → implement → validate loop, then return to the conversation.
Staged workshops must first obtain explicit approval of an exact 2D layout revision.
Never treat a draft, a successful render, or silence
as artistic, print, or physical-fit approval.

Read `.agents/skills/printable-terrain/SKILL.md` and follow its library, licensing,
source-hash, modelling, and physical-release rules. This workflow orchestrates that
capability; it does not replace its modelling and approval gates.

## 1. Resume before interviewing

Run `terrain workshop status` to discover staged workshops, then
`terrain workshop status scenes/<slug>` to resume the exact pending decision. Ask which workshop
only if more than one is plausible. Do not restart answered questions or invent a prior
conversation. Summarize the current intent and the most important unresolved decision.
Read the persisted state rather than inferring approval from the journal. `workshop review`
is only for existing 3D history, not discovery or resume.

For a new project, start with what the players should see and what meaningful choice
the encounter should give them. Reuse confirmed answers. Ask about opponents and
constraints only when they affect the next choice. Use the user's words.
Ask one focused question at a time, or at most three closely related questions. If a
question tool is available, use it for blocking choices with plausible recommendations
and room for the user's own answer.

Do not give the user a long intake form. Follow interesting answers and probe trade-offs.
Offer a concrete recommendation when they do not know. Clearly label your assumptions.

## 2. Research the story and its practical limits

Discover these progressively, when each answer affects the next draft:

- **Place and context:** setting, room's original/current purpose, approach, adjacency,
  story before the party arrives, mood, defining visual image, important reveal.
- **Antagonists:** identity, character, desire, fears, resources, how they fight or
  negotiate, allies, starting position, reinforcements, retreat/surrender conditions.
- **Players:** party size, miniature/base sizes, game/grid conventions, mobility,
  expected ranged/melee play, abilities that invalidate an assumed obstacle.
- **Encounter:** goals beyond killing, interactable objectives, stakes, time pressure,
  hazards and their telegraphing, escalation, alternate solutions and escape.
- **Physical table:** maximum footprint in millimetres, access from seated positions,
  sight lines, reusable versus bespoke pieces, printed stock and print budget,
  storage/transport, permitted height, and any known printer limits.

Do not ask for game statistics that do not change the terrain. Do not require the user
to invent villain lore before showing anything. Unknown story details can stay open;
unknown dimensions that determine fit must be asked or explicitly marked provisional.

After the 2D gate is explicitly approved, for missing assets, index the existing collection if needed, search targeted candidates,
render actual mesh contact sheets, **open those sheets**, and inspect the chosen shapes.
Filename/category matches are not visual review. Never upload the private collection.

## 3. Plan the playable space

Translate character and story into spatial decisions, not decorative labels:

| Story or play intent | Possible terrain consequence to discuss |
|---|---|
| A controlling, cautious villain | A defensible command position with a visible fallback route |
| A reckless brute | A readable direct charge lane, with player routes around it |
| A ritual or machine the party can stop | An accessible objective that competes with attacking |
| A place repurposed by an invader | Old circulation and architecture interrupted by new equipment |
| A dangerous process or unstable environment | A telegraphed hazard with ways to avoid or exploit it |

These are suggestions, not rules. Tie each chosen feature to a specific player decision.
Consider entrances, initial reveal, routes/flanks, open standing areas, sight lines,
cover, interaction access, verticality, villain movement and escape. Do not force every
encounter to have two routes or the same cover pattern if its fiction calls for another
trade-off. Explain intentional choke points and any resulting dead ends.

For the first composition, present two or three genuinely different top-down directions
on one comparison sheet. Use the example and contract in `docs/workshop-state.md`.
Take a pick, mix or feature move in ordinary chat. Record it in a new numbered 2D
revision, keeping earlier revisions unchanged. Tell the GM what changed, what it clarified,
and the next decision; show the SVG and pause. Do not create near-duplicate candidates
or make successive revisions without feedback. Do not implement a 3D draft before
explicit approval of the exact 2D layout revision.
Prioritize the distinctive focal silhouette and playable negative space over scatter.
Missing hero sculpts remain explicit gaps, not crude blocks presented as finished art.
When an original custom piece is needed, use the printable-terrain Blender draft workflow.
Place it with `terrain scene add-custom ... --draft <draft.json> --id <piece-id> --at X Y Z`.
Custom drafts appear purple and explicitly unindexed in scene reviews and stay outside
`assets`. Draft freely, then pause for feedback. **Adding a custom model to the library
requires separate, explicit user approval of that model revision**, even when the user
already approved the scene composition. Never invoke `custom approve` on your own.

## 4. Persist the discussion

Initialize once, after enough discussion to name the project:

```bash
uv run terrain workshop init scenes/<slug> --name "<name>" --brief "<current intent>"
```

Add `--catalog /absolute/path/catalog.json` when not using the default index.
Initialization does not validate the catalog or invoke a renderer or model tool.
Before approval, do not call standalone
`library preview`, `custom create`, `custom preview`, `generate`, mesh tools, or other
model/render tools on behalf of a staged workshop before its 2D gate is approved.
The agent edits the files; the user need not manipulate JSON.
Record each answer in the state through `terrain.workshop.update_workshop_state` as
documented in `docs/workshop-state.md`, preserving the exact next decision. Do not
edit the state file directly.

- `scene.json`: current editable scene, pinned assets and structured encounter intent.
- `workshop-state.json`: versioned authoritative resume and gate state; see
  `docs/workshop-state.md`. Never infer confirmation from `design.md` or legacy history.
- `layouts/NNNN.json` and `layouts/NNNN.svg`: immutable checked 2D comparison and sheet.
- `design.md`: living discussion journal, confirmed choices, assumptions, open questions,
  feedback and next step. Record meaningful user answers and their spatial consequences.
- `revisions/NNNN.json`: immutable source snapshots created by checkpoints. Each records
  layout, encounter, art direction, feedback, change summary and a copy of the journal.
- `build/workshops/<slug>/`: private disposable 3D review pages, real geometry images,
  assembly reports and printing lists. Never put embedded purchased geometry in `scenes/`.

Use the initialized `encounter` keys. A villain entry can record name, personality,
motivation, tactics and retreat conditions. `terrain_beats` should map narrative/play
intent to features and stable `placement_ids`, plus unresolved review questions.
`space.footprint_mm` is the available [width, depth], not a claim that the scene fits.
Keep confirmed decisions separate from assumptions. Preserve unanswered questions.

Maintain stable placement IDs so feedback such as “move `pressure-objective`” has an
unambiguous target. Use `terrain scene add scenes/<slug>/scene.json ...` for initial
placements, and edit those placements to move/remove pieces. Keep pinned source hashes
and rigid-body transforms. No scaling, fusion, source repair or invented inventory.

Use `terrain workshop layout ...` to save each 2D iteration. Select the GM's chosen
option in the plan, but do not confuse that pick with permission to start 3D. Show the
revision number, digest, checks and comparison, then ask for explicit unconditional
approval of that exact selected revision. Record only the GM's actual approval using
`terrain workshop approve-layout`; its required confirmation phrase is documented in
`docs/workshop-state.md`. Generic assent, silence, a choice, or conditional approval is
not enough. If the GM uses different words, clarify and obtain the exact confirmation,
never fabricate it. If library fit requires a material change, save a new 2D comparison
and obtain fresh approval before continuing. The software records the statement, not
the identity of the person who supplied it.

Report active time and known usage where the environment exposes them, including retries
and child calls where available. State what coverage is unknown; label estimates as
unverified. There is no fixed round, time or dollar cap. Do not make new billable
commitments without the user's permission.

## 5. Implement a small, visible iteration

Make a coherent first arrangement early, then change one design hypothesis or a small
related group at a time. Avoid a hidden batch of revisions before the user sees anything.

```bash
uv run terrain workshop checkpoint scenes/<slug> \
  --title "The first approach" \
  --changes "Offset the control point and leave the foreground open"
```

For subsequent iterations, record actual user feedback, not fabricated approval:

```bash
uv run terrain workshop checkpoint scenes/<slug> \
  --title "A safer flank" \
  --feedback "The approach feels too exposed" \
  --changes "Move the side cover to break the approach sight line"
```

Checkpoints build four actual mesh views (iso, reverse, top, front), a local interactive
WebGL review, reports and a printing list. They save the source revision only after the
build succeeds. Failed attempts must not be presented as saved iterations.

The local review supports orbit, pan, zoom, camera presets and piece visibility.
Its 50 mm reference grid is a ruler, not inferred asset dimensions or the gameplay grid.
Hiding a piece changes inspection only, never the saved layout or printing quantities.
The page has no chat/backend connection. The user pastes feedback into the conversation,
or downloads a note and supplies it to the agent. Do not claim to receive browser notes
automatically.

## 6. Validate, show, and pause

For **every** iteration:

1. Open at least iso and top previews yourself, adding reverse/front for occlusion.
   Inspect actual geometry, not only a concept image or successful exit code.
2. Read `report.json`, `print-list.csv`, and `assembly.md`. Compare conservative scene
   extents with the agreed footprint, and flag anything that exceeds it. Review overlaps,
   access, standing room, silhouette, missing assets and physical checks. AABB overlap
   is not an exact collision test. Do not assert measured route widths or line-of-sight
   clearance unless you actually checked them.
3. Give the user a link/path to `build/workshops/<slug>/index.html`, and embed iso/top
   images in chat using absolute workspace paths. Open the review in the available local
   browser when possible. The index browses earlier revisions, not just the current draft.
4. Briefly explain what changed, why it affects play, and what is unresolved.
5. Summarize printing quantities: required copies per original asset, confirmed printed
   stock, remaining copies. Unknown stock means **unknown**, never zero. CSV source
   paths identify the unchanged originals to open in the slicer. Keep missing/non-library
   pieces separate from this list. Unindexed Blender drafts have their own purple section
   with quantities and review hashes; they are not part of the printable library list.
6. Ask for focused visual feedback: what to keep, what to change, and the next meaningful
   decision. Refer to a camera angle and stable piece IDs. **Stop and wait.**

Update the journal and encounter on the next answer, revise the working scene, checkpoint,
and repeat. Do not silently drop confirmed choices when fixing a new concern. If the
user picks an older direction, apply its relevant scene/brief fields to the working draft,
keep the working catalog path correctly rebased, and save a new revision. Never edit
previous snapshots to pretend the history was different.

To resume/recreate private review artifacts:

```bash
uv run terrain workshop review scenes/<slug>
```

This reuses complete matching artifacts and rebuilds missing revision directories.
For a fresh rendering, use `--output-dir build/workshops/<slug>-rebuilt` rather than
overwriting an edited or incomplete folder. Snapshots require the indexed library and
matching source hashes. A changed source stops the process for deliberate review.

## 7. Finish deliberately

The user decides when the composition is good enough. Deliver the chosen revision,
review page, editable source, assembly instructions, per-asset printing list, missing
pieces and remaining checks. Artistic approval is separate from rights, units, stability,
connector fit, slicer inspection and physical approval. Do not mark those gates passed
without independent evidence. Never start printing or heating.
