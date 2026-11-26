# M0-A1: offline named-frame fixture

This is a disposable engineering probe for [M0-A1](https://github.com/JohannesKlauss/terrain/issues/20).
The app goal is to go from rough 2D layout to finished terrain with existing assets
and new originals. This probe tests whether one original can change in scene context
without moving its neighbors or changing its fit. The CLI and comparison page do
not prove the later integrated app workflow, and the fixed edit is not an agent response.

## Bootstrap and verify

Use a fresh checkout from the remote outside any private terrain workspace. Do not
mount or copy a local catalog, purchased meshes, project data, credentials or external
scripts. The verifier accepts no model, script or provider input. It creates and removes
a temporary workspace, or copies only its checked synthetic artifacts to a new directory
when `--output` is supplied. Keep generated evidence out of Git.

Tested with macOS 26.0.1 arm64, CPython 3.11.7, uv 0.11.9, Blender 5.3.0 in
`/Applications/Blender.app`, and the system `sandbox-exec`. The full repository
regression suite also uses OpenSCAD 2026.10.11 with Manifold and attributed, tracked
OpenLOCK fixtures. The M0 example and its own tests need neither those assets nor OpenSCAD.

From the checkout root:

```bash
uv sync --locked --dev
uv run --no-sync python examples/m0_a1/verify.py
uv run --no-sync pytest -q tests/test_m0_a1.py
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
# Optional larger fixture and local inspection; the output directory must not exist.
mkdir -p build
uv run --no-sync python examples/m0_a1/verify.py --grid 16 --output build/m0-a1
# Full regression suite includes trusted existing Blender and OpenSCAD tests.
uv run --no-sync pytest -q
```

Open `build/m0-a1/compare.html` locally to see matched oblique and top views. Click
geometry or **Select frame** to highlight its stable ID in both revisions. The default
grid is better for close inspection. To retain that run, omit `--grid 16` and use a
different new output directory.

## Fixture and checks

- The author-created baseline has a closed rectangular frame, separately named body
  and hands, a plinth, and repeated context blocks. There are 5 distinct assets,
  $5+n^2$ instances and $80+12n^2$ triangles for grid width $n$ (1 to 16). No purchased
  geometry or third-party imagery is used. The generated PNG carries a distinct motif
  deliberately absent from `prompt.txt`.
- The known geometry control changes only the top of `frame` from 22 to 23 mm.
  Blender reopens both editable files independently and exports the frame in each.
  Host checks compare the actual evaluated meshes and world transforms, including
  every protected component. They check the aperture and base interface, an explicitly
  bounded frame, and the independent STL dimensions, topology and analytical volume.
  Intentional hand, landing-interface and envelope changes must fail. STL dimensions
  allow four float32 ULP at 24 mm; these generated mesh coordinates otherwise compare
  exactly. The manifest records evidence SHA-256s, tool/profile versions and scope.
  Reproducibility uses normalized geometry JSON and PNG bytes, not cross-run Blender
  container byte equality.
- Before running the fixture, an independent positive control proves the benign
  operations can work. The same canary code under Blender must allow fixture reads
  and stage writes, deny input changes, outside reads and cross-boundary symlink access,
  reject writes to synthetic canonical and approval files, and deny a loopback
  connection and spawning another executable. The supervisor checks protected bytes
  and tests cancellation by reaping a ready Blender process before any candidate exists.

## Foundation evidence and limits

| Boundary | What this probe tests | What it does not establish |
| --- | --- | --- |
| Launch/shell | A local Python supervisor launches fixed headless Blender operations, captures results, and kills/reaps a ready worker. The browser opens an offline evidence file with no worker controls. | No desktop shell, app-owned consent or worker supervision from the UI. No browser-only substitute for the process boundary. |
| Renderer | An SVG projection of evaluated meshes tests stable component IDs, shared camera extents and linked selection across revisions. The existing `src/terrain/review.py` WebGL inspector is another baseline for orbit and full scene inspection, not tested by this fixture. | No GPU renderer comparison, generalized 3D picking, production renderer choice, or performance claim. |
| Storage | A staged file remains invisible until atomic replacement, but the file probe does not fence another writer. SQLite tests a blocked second writer, rollback and a stale revision predicate using the real baseline digest. | No product store choice, power-loss durability claim or app-owned approval API. The Blender worker sees no such API; the tested result is denial of synthetic filesystem writes. |
| Isolation | Kernel-enforced checks on this installed macOS version. The viewer and host validation are not inside the worker profile. | Not a sandbox for an agent, arbitrary generated Python, unknown `.blend` files, or other hosts. OS metadata and required runtime reads remain visible. The Apple-private `dyld-support.sb` bootstrap can change after OS updates; rerun controls and stop on failure. No unsandboxed Blender fallback. |

Keep live provider transport, agent tools, arbitrary generated Blender scripts and any
unverified desktop shell disabled. A real provider route needs a separately approved
data and spend policy and proof of its actual execution boundary. This probe does not
select the product stack, authorize calls, or close the M0 exit gate.
