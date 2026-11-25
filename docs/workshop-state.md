# Staged workshop contract, version 1

`terrain workshop init scenes/<slug>` exclusively creates a workshop and records its
identity in `.terrain-staged.json`, `scene.json`, and `workshop-state.json`. The
catalog path is stored but not loaded. An incomplete creation is not a standalone scene:
do not remove the marker to bypass recovery. `workshop status` lists candidates; pass a
path to inspect the authoritative state. `design.md` is a readable journal, not a gate.

The state records the version, UUID, slug, name, brief, confirmed facts, assumptions,
open questions, stage, exact pending decision, revision references and typed gate
evidence. Version 1 currently accepts only `intake`, null revision references and an
empty evidence list. This deliberately denies all 3D work; the next implementation
must define and validate the 2D revision and explicit approval evidence before adding
any allowed transition. Unknown versions, missing files, mismatched identities and
malformed records fail closed. Scene markers travel with snapshots. Legacy unmarked
workshops continue to support 3D history, but their journal is not an approval.

Update intake fields with `terrain.workshop.update_workshop_state(path, expected, updated)`,
passing the complete state read previously as `expected` and a modified copy as `updated`.
It takes the workshop lock, validates identity and prior state, rejects stale writers,
and atomically replaces the complete state via a flushed temporary file. Do not directly
edit the state file. Future transitions must preserve those guarantees.
Bind any future evidence to an exact immutable revision and its content hash; require
an explicit user confirmation recorded as typed evidence. The app records that
confirmation, it does not authenticate who typed it. Never infer it from silence,
rendering, an older revision, or a legacy journal. Do not advance a gate on failure.
