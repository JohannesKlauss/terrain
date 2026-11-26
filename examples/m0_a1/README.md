# M0-A1: offline named-frame fixture

This is a disposable engineering probe for [M0-A1](https://github.com/JohannesKlauss/terrain/issues/20).
The app goal is to go from rough 2D layout to finished terrain with existing assets
and new originals. This probe tests whether one original can change in scene context
without moving its neighbors or changing its fit. The offline staging shell does
not prove the later integrated app workflow, and the fixed edit is not an agent response.

## Bootstrap and verify

Use a fresh checkout from the remote outside any private terrain workspace. Do not
mount or copy a local catalog, purchased meshes, project data, credentials or external
scripts. The verifier accepts no model, script or provider input. It creates and removes
a temporary workspace, or copies its checked synthetic artifacts to a new directory
when `--output` is supplied. Use an exclusive output parent you just created. The
CLI's final rename is not a concurrent no-replace operation. Keep evidence out
of Git. The shell creates an exclusive temporary parent for each job automatically.

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
# Optional larger fixture and local inspection in exclusive scratch.
scratch="$(mktemp -d)"
uv run --no-sync python examples/m0_a1/verify.py --grid 16 --output "$scratch/m0-a1"
# Full regression suite includes trusted existing Blender and OpenSCAD tests.
uv run --no-sync pytest -q
```

Open `m0-a1/compare.html` in the scratch parent to see matched oblique and top views.
**Highlight frame** marks its stable ID in both revisions. Geometry clicks do not
select components in SVG. Open `m0-a1/depth.html` for the same views with WebGL 2
depth-tested selection. At oblique projection coordinates $(u,v)=(12,-5)$, the
protected front block occludes the frame. The upper rail at $(0,-19)$ is still
selectable. Both renderers use the same bounds. The default grid is better for
close inspection; to retain that run, omit `--grid 16` and use a new output.

## Run and cancel in the local shell

```bash
uv run --no-sync python examples/m0_a1/app.py
```

Open the printed `127.0.0.1` URL in a local browser. Choose **Run fixed Blender
edit** to run the trusted synthetic operation, observe progress, and open the
paired comparators once the candidate is staged. Start another run and use **Cancel
staging** while it is active; the previous preview remains available. Stop the
shell with Ctrl+C. No provider, file upload, arbitrary Python, approval, or commit
route is present. This shell listens only on loopback and validates mutation origin,
intent header and request shape. It does not authenticate local processes.

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
  The verifier validates the evaluated baseline snapshot and millimetre export
  before candidate execution, and keeps them with the accepted Blender file and
  scope contract in worker-read-only inputs. The later Blender candidate process
  must be denied write access to all four.
- Before running the fixture, an independent positive control proves the benign
  operations can work. The same canary code under Blender must allow fixture reads
  and stage writes, deny input changes, outside reads and cross-boundary symlink access,
  reject writes to synthetic canonical and approval files, and deny a loopback
  connection and spawning another executable. The listener must accept no
  connection, not merely receive no bytes. The supervisor checks protected bytes
  and reaps a ready Blender canary on cancellation. A regression also stops the
  supervisor with `SIGTERM` during candidate staging and checks that it reaps the
  worker and discards scratch without publishing partial evidence.

## Foundation evidence and limits

| Boundary | What this probe tests | What it does not establish |
| --- | --- | --- |
| Launch/shell | CLI runs and reports the same trusted operation. The disposable browser shell owns the supervisor and exposes progress, scoped cancellation and a staged preview. Candidates cannot be accepted from the shell. | No packaged desktop shell, real app consent/approval, or agent-tool protocol. Browser isolation is not the worker boundary. |
| Renderer | SVG shows two matched views and a linked frame highlight, with geometry picking disabled. The WebGL 2 alternative uses the same meshes and cameras but resolves picking at overlap with a depth buffer. | No general 3D editor, orbit workflow, production renderer choice or performance claim. If WebGL is unavailable, SVG is inspection-only. |
| Storage | Separate CLI-only probes use the real baseline and candidate `.blend` digests. Two requests start from the same accepted digest; one commits, both stores reopen on that digest, reject the pending stale request, and preserve the digest after interruption. SQLite additionally fences a competing writer; the file alternative assumes one exclusive writer. | No production persistence, power-loss durability, production store choice or approval API. The shell never runs the commit probe. |
| Isolation | Kernel-enforced checks on this installed macOS version. The viewer and host validation are not inside the worker profile. | Not a sandbox for an agent, arbitrary generated Python, unknown `.blend` files, or other hosts. OS metadata and required runtime reads remain visible. The Apple-private `dyld-support.sb` bootstrap can change after OS updates; rerun controls and stop on failure. No unsandboxed Blender fallback. |

Keep live provider transport, agent tools, arbitrary generated Blender scripts and any
unverified desktop shell disabled. A real provider route needs a separately approved
data and spend policy and proof of its actual execution boundary. This probe does not
select the product stack, authorize calls, or close the M0 exit gate.
