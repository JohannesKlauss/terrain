# M0-B2: local native-protocol host follow-up

Related to [#22](https://github.com/JohannesKlauss/terrain/issues/22). This is a
disposable local slice of B2, not B2 acceptance and not a shipping adapter. Every
run here is **simulated**: the host talks NDJSON over stdio to a bundled synthetic
peer. No Codex, pi or Maki process, model, account or network is used, and no
thread, turn or account request is sent to an installed agent.

## Previous live evidence (not rerun here)

The tracked [#22 issue text](https://github.com/JohannesKlauss/terrain/issues/22)
records three approved synthetic turns on native Codex App Server `0.171.0` and
its configured default route:

| Turn | Input | Observed outcome |
| --- | --- | --- |
| 1 | Synthetic image | Motif identified; zero tool calls |
| 2 | Text only | One allowed and one host-denied call to the fixed tool, correlated |
| 3 | Synthetic image | Motif identified plus the exact receipt from one fixed-tool call |

All three completed and the workers exited cleanly on stdin EOF. That tool returned
only fixed results. Model, provider egress, outbound byte counts and containment
profile for those runs are not recorded here and remain unknown for this slice.
Active cancellation, worker interruption, reconnect/recovery, a real Blender edit
and live pi/Maki trials were not exercised then.

## What this slice adds

`native_host.py` is the host side of a Codex App Server-shaped session
(`initialize`, `thread/start`, `turn/start`, `turn/interrupt`, `thread/resume`,
server request `item/tool/call`). Message shapes follow the pinned `0.171.0`
protocol sources listed in the [B1 audit](../../docs/m0-agent-integration-audit.md);
they were not revalidated against the binary in this slice.

- Responses are correlated by request ID. Unmatched or duplicate responses,
  replies that arrive after their request timed out, invalid JSON and lines
  over 64 KiB are recorded as violations and ignored.
- One fixed named tool, `stage_frame({component_id, base_revision})`. The host
  refuses calls for another thread, a non-active or interrupted turn, another
  tool name, extra or missing fields, a component other than `frame` and any
  base other than the accepted digest. Allowed calls only record a staged
  receipt. Nothing is executed, and no tool name maps to a command.
- Approval requests are declined; other server requests get JSON-RPC `-32601`.
- `interrupt()` fences the active turn before `turn/interrupt`, so a late call
  for it is refused. `close()` sends EOF, then `SIGTERM`, then `SIGKILL` to the
  worker's process group, and fails unless the group is confirmed gone.
- `recover()` reaps the old worker, reconnects and calls `thread/resume`. The
  resumed thread must contain the last turn the host journaled as completed.
  If the new worker exits or times out, the resume reply is an error or
  malformed, or the journal does not match, it reaps the new worker and raises
  `RecoveryFailed` without starting a turn. Accepted state is app-owned and
  never changed by the worker.

The worker is always `synthetic_app_server.py`, launched with `python -I`, a
minimal environment and its own scratch state directory. The entry point takes
no arguments, so no executable, provider or path can be supplied.

## Run

From the checkout root:

```bash
uv sync --locked --dev
uv run --no-sync python examples/m0_b2/run.py
uv run --no-sync pytest -q tests/test_m0_b2.py
uv run --no-sync ruff check examples/m0_b2 tests/test_m0_b2.py
uv run --no-sync ruff format --check examples/m0_b2 tests/test_m0_b2.py
```

`run.py` prints one JSON report and exits nonzero if any scenario fails:
correlation and notifications, tool refusals, cancellation with a late call,
forced reap of a worker that ignores EOF and `SIGTERM`, crash then native resume,
and failed recovery from missing worker state.

## Not established

| Gap | Status |
| --- | --- |
| Real Codex behavior for interrupt, late calls, resume and reap | Not exercised; needs an authorized live run |
| Image handling | Previous live evidence only; not part of this slice |
| Provider egress, payload bytes, profile and containment | Unknown |
| Real A1 worker or Blender edit from a tool call | Not exercised |
| pi and Maki routes | Not exercised |
| Complete native lifecycle or B2 acceptance | Not claimed |
