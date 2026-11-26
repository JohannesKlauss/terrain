# M0-B1: Agent integration reuse audit

Related to [#21][b1]. Inspected 2026-11-26 on the macOS arm64 target. This is an
offline shortlist for [B2][b2], not an adapter or a framework choice. Release
metadata and tagged source establish what to test, not what works with an
account, model or containment profile. No agent executable, SDK or provider was run.

## Pins and provenance

| Surface to evaluate | Artifact and exact source | Installed observation |
| --- | --- | --- |
| Codex App Server | [CLI release `rust-v0.171.0`][c-release], peeled commit `ccf9be8cc458bd6b8336fe84d68d8893f2691a5e`. [npm `@openai/codex@0.171.0`][c-npm] declares target-specific optional packages; [publish provenance][c-att] points to this tag and commit. The release carries both the CLI and a standalone App Server. The CLI subcommand is the proposed route. | ARM64 standalone launcher resolves to a `0.171.0-aarch64-apple-darwin` release directory, beside Code Mode and exec-server helpers. Metadata, not a byte or runtime check. |
| codex-acp | [v2.12.0][ca-release], `2a627def45e1d228cdb7fd9a7cd454ac81281e6f`, matching [npm `gitHead`][ca-npm]. Node stdio adapter starts its bundled Codex CLI by default; [`CODEX_PATH`][ca-cli] can select a single audited executable. Pin both IDs even when they ship together. | Not on `PATH`; no install was attempted. |
| pi RPC and native SDK | [v1.6.0][p-release], `faac585884ae2c013a6b1400f3e9e77f10b34bac`. [npm `@earendil-works/pi-coding-agent@1.6.0`][p-npm] and [publish provenance][p-att] match it. This package provides the CLI and the TypeScript SDK, not two independently versioned agents. | Managed launcher points to `1.6.0`, confirmed in the installed package manifest. [v1.6.1][p-new] is a newer release, not the observed install or a qualified substitute. |
| pi-acp | [v0.0.35][pa-release], `41fb17a54f4599a0ca4723887cce0f40aaea325a`, matching [npm `gitHead`][pa-npm]. Separate Node process and separately pinned pi RPC child. No declared pi package dependency. | Not on `PATH`; no install was attempted. |
| Maki ACP and SDK wire mode | [v0.7.1][m-release], `6b1dc8db8b1b121dd24d4b8aaf00cc24ceea9733`. Both are subcommands/modes of the same published binary, not separately qualified SDK packages. [v0.7.3][m-new] is newer; its docs/code do not establish installed behavior. | ARM64 executable contains `maki/v0.7.1-g6b1dc8d` and `Maki/0.7.1` build strings, matching the release tag prefix. Not a cryptographic comparison of installed bytes to the release archive. |

The source commits are immutable links below. For example, the Maki release
lists the ARM64 macOS archive SHA-256 as
`60561c7c84faa015c2694b47064cd927dfdd244f6ee5909a83e337516daea1c9`.
The Codex and pi npm provenance payloads were read for their source revisions;
no local artifact or attestation signature was verified by this audit.

## Interfaces and B2 hypotheses

All rows are **blocked for live execution** until the gates below. The first
candidate per agent is native Codex App Server, native pi RPC, and Maki ACP.
The alternate paths are compatibility experiments only. A successful
handshake, a permission prompt, or an accepted image block is not a pass.

| Candidate | Transport, existing auth and image hypothesis | Scoped tool and denial hypothesis | Stop and recover hypothesis |
| --- | --- | --- | --- |
| **Codex App Server** | Local stdio JSONL ([`initialize`/`initialized`][c-wire], then thread/turn requests). Reuse authorized Codex ChatGPT login or API-key path, as described in the pinned [account types][c-account]. Prove the selected model sees the known PNG through [typed `Image` or allowlisted `LocalImage`][c-turn], not a URL fetch. | [Thread `dynamicTools`][c-thread] plus [`item/tool/call`][c-tool] are the narrow first probe; confirm the exact experimental-capability requirements and call behavior. Host registers a single typed tool; reject approval and unexpected requests. Configuration and Codex sandbox flags are not the outer boundary. | `turn/interrupt` the addressed turn, wait for terminal events and fence late tool requests. Reopen the same app-owned thread via `thread/resume` against isolated state; revalidate tool registration, permissions and accepted digest before allowing any activity. Missing state falls back to explicit rehydration, not a new unapproved turn. |
| **codex-acp** | [Adapter][ca-doc] translates ACP stdio to App Server. Existing ChatGPT/API-key path only, no custom gateway. Test image-to-Codex conversion with same model/control; confirm negotiated ACP version and capabilities. | [Adapter MCP config][ca-mcp] supports stdio/HTTP; [MCP-over-ACP][ca-moa] adds an authenticated HTTP bridge on loopback, not a no-socket guarantee. Probe only a host-owned fixed endpoint on a separately proved route. [Mode fallback][ca-perm] makes adapter defaults unsuitable as enforcement. | Test `session/cancel` translation to `turn/interrupt` and `session/load` to `thread/resume` using the [pinned client][ca-client] and [server][ca-server]. Supervise both processes and helpers; a client-side cancelled request alone proves nothing. |
| **pi RPC** | [`pi --mode rpc`][p-rpc] uses command/response/events over stdio, not ACP. [Existing Pi provider login or environment key][p-auth] only in agent profile. [Prompt `images`][p-commands] carries base64 PNG; verify provider/model acceptance and visibility. | Use one host-controlled [extension tool][p-ext] or native [MCP][p-mcp] declaration from isolated config, never discovered ambient resources. Explicitly suppress built-in shell/filesystem tools, unwanted extensions and additional MCP exposure; [`--tools` alone does not suppress MCP][p-cli]. Extension hooks/UI are not OS enforcement. The [Pi SDK][p-sdk] offers `customTools` and an explicit `SessionManager`/resource loader, but any SDK probe must live in its own supervised process, not the terrain host. | Stop accepting new work, clear queue, `abort`, then verify terminal idle and no pending dispatch. `switch_session` takes a host-owned JSONL path when persistence is explicitly enabled; use fresh synthetic workspaces and never accept a client/provider path. `--no-session` only supports explicit host rehydration after restart. |
| **pi-acp** | ACP stdio to a separately pinned pi via [`PI_ACP_PI_COMMAND`][pa-entry] and [RPC process wrapper][pa-rpc]. Reuses pi auth (adapter terminal auth launches pi); do not trigger it automatically. [Image translation][pa-image] forwards byte content to pi. | **ACP-supplied terrain tools blocked:** the [agent][pa-agent] stores `mcpServers` but does not wire them to pi. [Extension UI to ACP permissions][pa-session] is narrower than a general filesystem/tool permission boundary. Only reconsider with a separately contained and explicitly configured native pi tool, then prove that same path through ACP. | Adapter queues and clears its prompts then calls pi abort; test queued work in both layers. [Load][pa-agent] depends on adapter metadata and pi's isolated session files; cross-check app context separately. |
| **Maki ACP** | Local `maki acp` stdio. [Pinned ACP guide][m-doc] and [provider guide][m-auth] reuse normal Maki provider credentials (for example an authorized existing OpenAI login or API key). Verify actual image input conversion/motif via the [server][m-server]. | `session/new` accepts MCP; [server][m-server] and [MCP docs][m-mcp] show stdio and HTTP paths. Prefer one fixed host registration with no user-provided executables and no ambient tools/configuration. Deny in host and test [permission decision][m-perm] mapping. Reject alternate cwd, trust overrides, background tasks and unintended child processes; if the release cannot be confined this way, block it. | Test `session/cancel`, session load and EOF/signal termination separately. Require supervised process and tool teardown. Reload the same isolated session using `session/load` and verify the expected context without granting fresh authority. |
| **Maki SDK wire mode** | [`maki --print --input-format stream-json`][m-sdk] is a Claude Code-shaped interface, not proof of drop-in compatibility with any Claude SDK or of ACP parity. Code parses base64 image blocks; malformed ones may be dropped. Reuses Maki provider settings. | Probe only the same fixed MCP tool with app enforcement, no `--yolo` or bypass permission mode. Validate the chosen client against exact message shapes; no additional SDK or dependency proposed. | Check decoded control/interrupt behavior, then separately prove worker stop and native resume. The implementation explicitly has no SDK history replay for its live-only event mapping. Use app-owned rehydration or mark unsupported rather than counting live deltas as replay. |

## Dependencies, notices and extraction

These are manifest/lock observations, not a complete SBOM for shipped binaries.
Workspace locks include build, test, optional and other target dependencies;
do not assume all listed entries shipped or a floating npm install resolves
the same graph. Exact artifact/SBOM and redistribution checks are adoption gates.

- **Codex:** The [App Server manifest][c-manifest] depends on workspace
  core, App Server protocol/transport, login, exec and sandbox/proxy crates,
  plus runtime Tokio `1.52.3`, Serde `1.0.228`, Axum `0.8.8` and SQLx `0.9.0`
  in the [workspace and lock][c-lock]. The lock also includes Hyper `1.11.1`,
  rustls `0.23.46` and `rmcp` `3.6.0` from git revision
  `b11a40d889e022087d7f2b8cd23aa28e19ceaf5b`. The executable and helper
  distribution are a smaller evaluation commitment than extracting the Rust
  runtime. [Apache-2.0 license][c-license] and [NOTICE][c-notice] include a
  Ratatui MIT attribution; check bundled third-party notices before redistribution.
- **codex-acp:** [Manifest][ca-pkg] and [lock][ca-lock] resolve ACP SDK `2.9.1`,
  Codex `0.171.0` (and macOS ARM64 optional binary), `cross-spawn 7.0.6`,
  `diff 9.0.0`, `open 11.0.4`, `vscode-jsonrpc 9.0.3`, `zod 4.6.7`.
  Transitive examples: `path-key 3.1.1`, `shebang-command 2.0.0`, ISC
  `which 2.0.2`/`isexe 2.0.0` and `wsl-utils 1.0.1` from `open`.
  Use the release whole if ACP compatibility matters; extraction inherits
  Codex generated schemas, protocol drift, subprocess and session recovery.
  [Apache-2.0][ca-license] with JetBrains attribution; no separate source
  NOTICE found at the pin. `diff` is BSD-3-Clause; retain applicable bundled notices.
- **pi:** The [coding-agent manifest][p-pkg] has Node `>=22.19.0`, five same-pin
  workspace packages (`pi-agent-core`, `pi-ai`, `pi-codemode`, `pi-mcp`, `pi-tui`),
  plus `undici 8.12.4`, `quickjs-wasi 3.6.2`, and `photon-node 0.3.4` among its
  direct dependencies. [Workspace lock][p-lock] includes transitive provider
  SDKs (e.g. `openai 7.59.0` through `pi-ai`) and `cross-spawn`'s `path-key 3.1.1`
  and `which 2.0.2`. Keep the [MIT notice][p-license], including Mario
  Zechner's copyright; [pi-mcp has an Anthropic MIT notice][p-notice];
  [pi-schema has a TypeBox notice][p-typebox]. Prefer the maintained RPC
  executable to extracting its agent, provider and resource loading stack.
- **pi-acp:** [Manifest][pa-pkg] and [lock][pa-lock] resolve ACP SDK `0.26.0`,
  `zod 3.25.76`, `cross-spawn 7.0.6`, and the latter's `path-key`, `shebang-command`,
  `which` and `isexe` at the same versions above; separately requires the pi
  executable. Package minimum Node `20` does not satisfy the proposed pi pair's
  higher floor by itself. [MIT][pa-license], Sergii Kozak copyright; no separate
  source NOTICE found. The [ACP JS SDK `0.26.0`][sdk-old] (source
  `73bc30649b650de320340c782733bf69a545bd28`, [Apache-2.0][sdk-old-license])
  and [SDK `2.9.1`][sdk-new] (source `ab16fb07b4e7e5dd8e55633b42930857223c4cd0`,
  [Apache-2.0][sdk-license]) are not assumed interchangeable.
- **Maki:** [Workspace manifest][m-pkg], [ACP manifest][m-acp-pkg] and
  [lock][m-lock] connect `maki-acp` to `maki-agent`, config, providers, storage,
  telemetry, Tokio `1.54.1`, and [ACP schema `1.15.1`][m-schema] (Apache-2.0).
  Locked shared runtime examples include Reqwest `0.13.5`, rustls `0.23.46`,
  Lua binding `mlua 0.12.2` and tree-sitter `0.27.1`. The [CLI ACP entry][m-cmd]
  wires project trust, config and plugins; `maki-acp` is not a standalone
  terrain SDK. [MIT][m-license], Tony Solomonik copyright; no separate source
  NOTICE found. Prefer the pinned external binary over extracting Rust crates.

For redistribution, Apache-2.0 §4 calls for providing the license, prominent
notices in changed files, retaining relevant source attribution and carrying
applicable upstream NOTICE text in a readable form. MIT requires retaining the
copyright and permission notice in copies/substantial portions. Audit additional
licenses for the actual redistributed closure, including vendored code, native
payloads and optional dependencies. Linking for this audit copies none of them.

### HumanLayer: inspect the useful pieces, do not extract

| Exact source | Relevant interfaces, dependencies and fit |
| --- | --- |
| [`pro-0.20.0`][h-release], `5486c0ce95b12cfc2597c7e0e3233c608446d1fd` | [`claudecode-go` client][h-client] wraps Claude-specific CLI launch, streamed events, wait/interrupt and resume. [Go manifest][h-client-mod] and [sum][h-client-sum] contain test dependencies (Testify and indirect Go spew, difflib, YAML); production wrapper uses Go stdlib and the external Claude executable. Good reference for process lifecycle, wrong protocol for the target agents. [`hld` approval manager][h-approval] and [MCP server][h-mcp] depend on conversation store, event bus and approval state, not a generic terrain capability gate. [`hld` manifest][h-mod]/[sum][h-sum] use local `claudecode-go`, MCP Go `0.37.0`, SQLite `1.14.28` (CGO), UUID `1.6.0`, and daemon HTTP/config dependencies (Gin/Viper and their indirect dependencies). [Apache-2.0][h-license] at this pin; no separate NOTICE or narrower license found in these modules. Do not import dangerously-skip or edit-mode approval semantics. |
| Installed [npm `@humanlayer/cli@0.40.7`][hl-npm], registry `gitHead` `8e1e3f159a78d7c81f6e1abc0dcc2e70d8828d48` | Installed package manifest matches `0.40.7`, with optional platform payloads in npm metadata. [Source CLI manifest][hl-cli] says `0.40.0`; mapping is registry provenance, not a reproduction of packaging. The nearest relevant [pi extension][hl-pi] uses the native Pi extension API and [tool registration][hl-tools] coupled to HumanLayer cloud tasks. It mirrors transcripts, tool results, files and diffs; that is outside terrain's allowed disclosure. [Extension manifest][hl-pkg] pulls six workspace session SDK modules and Pi peers. [Base SDK][hl-base] uses the [riptide API contract][hl-api] and oRPC; [Bun lock][hl-lock] resolves oRPC `1.14.3`, Effect `4.0.0` and Zod `4.5.4` among the transitive graph. [Apache-2.0][hl-license] and [NOTICE][hl-notice] apply to the inspected source, with MIT exceptions for the listed vendored modules. The extension is not the installed CLI artifact. No separately qualified distribution of the internal SDK modules was established. |
| CLI-adjacent [Fold Codex `0.1.32`][fold-npm], registry `gitHead` `3110435925bc206f6d18d501d40580e9c459d6d7` | The CLI's [agent auth command][hl-auth] manages separate product auth stores, including Fold. [Fold manifest][fold-pkg]/[lock][fold-lock] tie it to `fold-core` and `effect-ai-openai` `0.1.32` in npm, with Effect-based auth/model plumbing, not a wrapper for the installed App Server. [MIT][fold-license], HumanLayer copyright; no separate source NOTICE found. The native Codex route is preferable because extracting this would introduce another credential/model path rather than reuse the authorized Codex one. |

Compare the wrapper, approval correlation and event handling as design ideas
only. Extracting either implementation brings different agent semantics, storage
or cloud coupling, and does not replace the app's authority checks. Maintained
native routes expose narrower surfaces for B2. None is approved for product use.

## B2 conformance recipe

1. **Gate the route.** [A1][a1] verifies the fixed offline Blender worker,
   not agents, MCP/helpers, general Python, or outbound inference. Before any
   launch, prove containment of the exact adapter, agent, tool helper and
   worker/profile with synthetic file/process/network controls. Require a
   cleared scratch cwd, isolated config/state, no ambient discovery/update,
   no private mounts, default-deny tools/egress, and supervised child cleanup.
   A route needing unproved privilege, unrestricted egress, alternate cwd or
   authentication handling stays blocked. Get separate owner authorization
   for exact provider/model, existing account, payload categories/limits and
   spend before any external request, including auth, discovery and refresh.
2. **Prove image input, not just transport.** Run with the
   [A1 synthetic reference][fixture] and cleared text. Ask for the motif absent from that
   text. Compare a fresh image run with text-only and a changed-motif image
   in independent sessions, under the same authorized provider/model. Verify
   the actual outbound image payload category/size and expected distinction.
   Missing image support, no permitted observation, or a model merely guessing
   the answer is not a verified route.
3. **Prove the tool boundary.** Offer one fixed schema, such as
   `stage_frame({component_id, base_revision})`, whose only allowed input
   requests the fixed synthetic frame edit from an exact app-owned revision.
   Host validates session/turn, scope and revision, then uses the known A1
   worker; return only cleared status. Verify candidate digest and scope
   independently. Deny a protected component, stale base and extra fields;
   try an unregistered tool and a benign out-of-scope sentinel under the
   synthetic containment profile. No side effect, credentials, accepted
   write or approval on denial. Even an allowed tool only stages, never
   accepts; the user's separate terrain decision is bound to exact state.
4. **Stop and recover.** Cancel an active model turn, a known running worker,
   and a run between staging and publication. Check no new requests/work
   after stop, confirm every owned child is reaped, reject late/duplicate
   results and preserve the accepted digest and prior preview. No claim
   about remote cancellation or billing beyond observed signals. Force a
   disconnect/restart; reopen matching synthetic state and verify a known
   context fact, or explicitly rehydrate only approved app-owned context
   into a fresh session. Missing/stale state must leave accepted state
   unchanged. A missing resume feature is not a resume pass.
5. **Record outcomes and stop conditions.** For each scenario and agent, record
   exact artifact, protocol version/profile, authorization category, request/
   result class, outbound category/byte count, timings, tool/worker verdict and
   unchanged accepted digest. Use `passed`, `failed`, `blocked`, or `not exercised`;
   do not retain credentials or transmitted content. Require at least one real
   image + tool route with enforced denial, cancellation and safe recovery
   behavior. If none qualifies, report no-go; no mock or unconstrained fallback.

**Updates:** Pin the executable/platform artifact integrity, source commit,
adapter, versioned child binaries, protocol/schema, dependency resolution and
profile as one record per route. Review release diffs (including auth, hooks,
permissions, state and egress), manifests, lock/SBOM and notices before changing
any of them. Re-run the route's synthetic and authorized conformance matrix
on each proposed update, including an old-state resume or explicit no-resume
path. Keep the last qualified pin or disable the route on mismatch, unknown
authority, unresolved licenses or regressions; never auto-update or fall back
to `main`, an unpinned binary or another provider.

[a1]: https://github.com/JohannesKlauss/terrain/issues/20
[b1]: https://github.com/JohannesKlauss/terrain/issues/21
[b2]: https://github.com/JohannesKlauss/terrain/issues/22
[fixture]: ../examples/m0_a1/README.md
[c-release]: https://github.com/openai/codex/releases/tag/rust-v0.171.0
[c-npm]: https://registry.npmjs.org/@openai%2Fcodex/0.171.0
[c-att]: https://registry.npmjs.org/-/npm/v1/attestations/@openai%2Fcodex@0.171.0
[c-wire]: https://github.com/openai/codex/blob/ccf9be8cc458bd6b8336fe84d68d8893f2691a5e/codex-rs/app-server-protocol/src/protocol/common.rs
[c-account]: https://github.com/openai/codex/blob/ccf9be8cc458bd6b8336fe84d68d8893f2691a5e/codex-rs/app-server-protocol/src/protocol/v2/account.rs
[c-thread]: https://github.com/openai/codex/blob/ccf9be8cc458bd6b8336fe84d68d8893f2691a5e/codex-rs/app-server-protocol/src/protocol/v2/thread.rs
[c-turn]: https://github.com/openai/codex/blob/ccf9be8cc458bd6b8336fe84d68d8893f2691a5e/codex-rs/app-server-protocol/src/protocol/v2/turn.rs
[c-tool]: https://github.com/openai/codex/blob/ccf9be8cc458bd6b8336fe84d68d8893f2691a5e/codex-rs/app-server-protocol/schema/json/DynamicToolCallParams.json
[c-manifest]: https://github.com/openai/codex/blob/ccf9be8cc458bd6b8336fe84d68d8893f2691a5e/codex-rs/app-server/Cargo.toml
[c-lock]: https://github.com/openai/codex/blob/ccf9be8cc458bd6b8336fe84d68d8893f2691a5e/codex-rs/Cargo.lock
[c-license]: https://github.com/openai/codex/blob/ccf9be8cc458bd6b8336fe84d68d8893f2691a5e/LICENSE
[c-notice]: https://github.com/openai/codex/blob/ccf9be8cc458bd6b8336fe84d68d8893f2691a5e/NOTICE
[ca-release]: https://github.com/agentclientprotocol/codex-acp/releases/tag/v2.12.0
[ca-npm]: https://registry.npmjs.org/@agentclientprotocol%2Fcodex-acp/2.12.0
[ca-cli]: https://github.com/agentclientprotocol/codex-acp/blob/2a627def45e1d228cdb7fd9a7cd454ac81281e6f/src/CodexCli.ts
[ca-doc]: https://github.com/agentclientprotocol/codex-acp/blob/2a627def45e1d228cdb7fd9a7cd454ac81281e6f/README.md
[ca-mcp]: https://github.com/agentclientprotocol/codex-acp/blob/2a627def45e1d228cdb7fd9a7cd454ac81281e6f/src/McpServerConfig.ts
[ca-moa]: https://github.com/agentclientprotocol/codex-acp/blob/2a627def45e1d228cdb7fd9a7cd454ac81281e6f/docs/mcp-over-acp.md
[ca-perm]: https://github.com/agentclientprotocol/codex-acp/blob/2a627def45e1d228cdb7fd9a7cd454ac81281e6f/docs/permission-profiles.md
[ca-client]: https://github.com/agentclientprotocol/codex-acp/blob/2a627def45e1d228cdb7fd9a7cd454ac81281e6f/src/CodexAppServerClient.ts
[ca-server]: https://github.com/agentclientprotocol/codex-acp/blob/2a627def45e1d228cdb7fd9a7cd454ac81281e6f/src/CodexAcpServer.ts
[ca-pkg]: https://github.com/agentclientprotocol/codex-acp/blob/2a627def45e1d228cdb7fd9a7cd454ac81281e6f/package.json
[ca-lock]: https://github.com/agentclientprotocol/codex-acp/blob/2a627def45e1d228cdb7fd9a7cd454ac81281e6f/package-lock.json
[ca-license]: https://github.com/agentclientprotocol/codex-acp/blob/2a627def45e1d228cdb7fd9a7cd454ac81281e6f/LICENSE
[p-release]: https://github.com/earendil-works/pi/releases/tag/v1.6.0
[p-npm]: https://registry.npmjs.org/@earendil-works%2Fpi-coding-agent/1.6.0
[p-att]: https://registry.npmjs.org/-/npm/v1/attestations/@earendil-works%2Fpi-coding-agent@1.6.0
[p-new]: https://github.com/earendil-works/pi/releases/tag/v1.6.1
[p-rpc]: https://github.com/earendil-works/pi/blob/faac585884ae2c013a6b1400f3e9e77f10b34bac/packages/coding-agent/docs/rpc.md
[p-auth]: https://github.com/earendil-works/pi/blob/faac585884ae2c013a6b1400f3e9e77f10b34bac/packages/coding-agent/docs/providers.md
[p-commands]: https://github.com/earendil-works/pi/blob/faac585884ae2c013a6b1400f3e9e77f10b34bac/packages/coding-agent/docs/rpc-commands.md
[p-ext]: https://github.com/earendil-works/pi/blob/faac585884ae2c013a6b1400f3e9e77f10b34bac/packages/coding-agent/docs/extensions.md
[p-mcp]: https://github.com/earendil-works/pi/blob/faac585884ae2c013a6b1400f3e9e77f10b34bac/packages/coding-agent/docs/mcp.md
[p-cli]: https://github.com/earendil-works/pi/blob/faac585884ae2c013a6b1400f3e9e77f10b34bac/packages/coding-agent/docs/cli.md
[p-sdk]: https://github.com/earendil-works/pi/blob/faac585884ae2c013a6b1400f3e9e77f10b34bac/packages/coding-agent/docs/sdk.md
[p-pkg]: https://github.com/earendil-works/pi/blob/faac585884ae2c013a6b1400f3e9e77f10b34bac/packages/coding-agent/package.json
[p-lock]: https://github.com/earendil-works/pi/blob/faac585884ae2c013a6b1400f3e9e77f10b34bac/package-lock.json
[p-license]: https://github.com/earendil-works/pi/blob/faac585884ae2c013a6b1400f3e9e77f10b34bac/LICENSE
[p-notice]: https://github.com/earendil-works/pi/blob/faac585884ae2c013a6b1400f3e9e77f10b34bac/packages/mcp/THIRD_PARTY_NOTICES/modelcontextprotocol-typescript-sdk.txt
[p-typebox]: https://github.com/earendil-works/pi/blob/faac585884ae2c013a6b1400f3e9e77f10b34bac/packages/schema/THIRD_PARTY_NOTICES/typebox-LICENSE
[pa-release]: https://github.com/svkozak/pi-acp/releases/tag/v0.0.35
[pa-npm]: https://registry.npmjs.org/pi-acp/0.0.35
[pa-entry]: https://github.com/svkozak/pi-acp/blob/41fb17a54f4599a0ca4723887cce0f40aaea325a/src/index.ts
[pa-rpc]: https://github.com/svkozak/pi-acp/blob/41fb17a54f4599a0ca4723887cce0f40aaea325a/src/pi-rpc/process.ts
[pa-image]: https://github.com/svkozak/pi-acp/blob/41fb17a54f4599a0ca4723887cce0f40aaea325a/src/acp/translate/prompt.ts
[pa-agent]: https://github.com/svkozak/pi-acp/blob/41fb17a54f4599a0ca4723887cce0f40aaea325a/src/acp/agent.ts
[pa-session]: https://github.com/svkozak/pi-acp/blob/41fb17a54f4599a0ca4723887cce0f40aaea325a/src/acp/session.ts
[pa-pkg]: https://github.com/svkozak/pi-acp/blob/41fb17a54f4599a0ca4723887cce0f40aaea325a/package.json
[pa-lock]: https://github.com/svkozak/pi-acp/blob/41fb17a54f4599a0ca4723887cce0f40aaea325a/package-lock.json
[pa-license]: https://github.com/svkozak/pi-acp/blob/41fb17a54f4599a0ca4723887cce0f40aaea325a/LICENSE
[sdk-old]: https://registry.npmjs.org/@agentclientprotocol%2Fsdk/0.26.0
[sdk-new]: https://registry.npmjs.org/@agentclientprotocol%2Fsdk/2.9.1
[sdk-old-license]: https://github.com/agentclientprotocol/typescript-sdk/blob/73bc30649b650de320340c782733bf69a545bd28/LICENSE
[sdk-license]: https://github.com/agentclientprotocol/typescript-sdk/blob/ab16fb07b4e7e5dd8e55633b42930857223c4cd0/LICENSE
[m-release]: https://github.com/tontinton/maki/releases/tag/v0.7.1
[m-new]: https://github.com/tontinton/maki/releases/tag/v0.7.3
[m-doc]: https://github.com/tontinton/maki/blob/6b1dc8db8b1b121dd24d4b8aaf00cc24ceea9733/site/docs/content/acp/_index.md
[m-auth]: https://github.com/tontinton/maki/blob/6b1dc8db8b1b121dd24d4b8aaf00cc24ceea9733/site/docs/content/providers/_index.md
[m-server]: https://github.com/tontinton/maki/blob/6b1dc8db8b1b121dd24d4b8aaf00cc24ceea9733/maki-acp/src/server.rs
[m-mcp]: https://github.com/tontinton/maki/blob/6b1dc8db8b1b121dd24d4b8aaf00cc24ceea9733/site/docs/content/mcp/_index.md
[m-perm]: https://github.com/tontinton/maki/blob/6b1dc8db8b1b121dd24d4b8aaf00cc24ceea9733/maki-acp/src/permissions.rs
[m-sdk]: https://github.com/tontinton/maki/blob/6b1dc8db8b1b121dd24d4b8aaf00cc24ceea9733/src/sdk_mode.rs
[m-pkg]: https://github.com/tontinton/maki/blob/6b1dc8db8b1b121dd24d4b8aaf00cc24ceea9733/Cargo.toml
[m-acp-pkg]: https://github.com/tontinton/maki/blob/6b1dc8db8b1b121dd24d4b8aaf00cc24ceea9733/maki-acp/Cargo.toml
[m-lock]: https://github.com/tontinton/maki/blob/6b1dc8db8b1b121dd24d4b8aaf00cc24ceea9733/Cargo.lock
[m-schema]: https://crates.io/crates/agent-client-protocol-schema/1.15.1
[m-cmd]: https://github.com/tontinton/maki/blob/6b1dc8db8b1b121dd24d4b8aaf00cc24ceea9733/src/cmd/acp.rs
[m-license]: https://github.com/tontinton/maki/blob/6b1dc8db8b1b121dd24d4b8aaf00cc24ceea9733/LICENSE
[h-release]: https://github.com/humanlayer/humanlayer/releases/tag/pro-0.20.0
[h-client]: https://github.com/humanlayer/humanlayer/blob/5486c0ce95b12cfc2597c7e0e3233c608446d1fd/claudecode-go/client.go
[h-client-mod]: https://github.com/humanlayer/humanlayer/blob/5486c0ce95b12cfc2597c7e0e3233c608446d1fd/claudecode-go/go.mod
[h-client-sum]: https://github.com/humanlayer/humanlayer/blob/5486c0ce95b12cfc2597c7e0e3233c608446d1fd/claudecode-go/go.sum
[h-approval]: https://github.com/humanlayer/humanlayer/blob/5486c0ce95b12cfc2597c7e0e3233c608446d1fd/hld/approval/manager.go
[h-mcp]: https://github.com/humanlayer/humanlayer/blob/5486c0ce95b12cfc2597c7e0e3233c608446d1fd/hld/mcp/server.go
[h-mod]: https://github.com/humanlayer/humanlayer/blob/5486c0ce95b12cfc2597c7e0e3233c608446d1fd/hld/go.mod
[h-sum]: https://github.com/humanlayer/humanlayer/blob/5486c0ce95b12cfc2597c7e0e3233c608446d1fd/hld/go.sum
[h-license]: https://github.com/humanlayer/humanlayer/blob/5486c0ce95b12cfc2597c7e0e3233c608446d1fd/LICENSE
[hl-npm]: https://registry.npmjs.org/@humanlayer%2Fcli/0.40.7
[hl-cli]: https://github.com/humanlayer/humanlayer/blob/8e1e3f159a78d7c81f6e1abc0dcc2e70d8828d48/apps/cli/package.json
[hl-pi]: https://github.com/humanlayer/humanlayer/blob/8e1e3f159a78d7c81f6e1abc0dcc2e70d8828d48/apps/riptide-pi-extension/README.md
[hl-tools]: https://github.com/humanlayer/humanlayer/blob/8e1e3f159a78d7c81f6e1abc0dcc2e70d8828d48/apps/riptide-pi-extension/src/tools.ts
[hl-pkg]: https://github.com/humanlayer/humanlayer/blob/8e1e3f159a78d7c81f6e1abc0dcc2e70d8828d48/apps/riptide-pi-extension/package.json
[hl-base]: https://github.com/humanlayer/humanlayer/blob/8e1e3f159a78d7c81f6e1abc0dcc2e70d8828d48/packages/session-sdk-base/package.json
[hl-api]: https://github.com/humanlayer/humanlayer/blob/8e1e3f159a78d7c81f6e1abc0dcc2e70d8828d48/contracts/riptide-api-contract/package.json
[hl-lock]: https://github.com/humanlayer/humanlayer/blob/8e1e3f159a78d7c81f6e1abc0dcc2e70d8828d48/bun.lock
[hl-license]: https://github.com/humanlayer/humanlayer/blob/8e1e3f159a78d7c81f6e1abc0dcc2e70d8828d48/LICENSE
[hl-notice]: https://github.com/humanlayer/humanlayer/blob/8e1e3f159a78d7c81f6e1abc0dcc2e70d8828d48/NOTICE
[hl-auth]: https://github.com/humanlayer/humanlayer/blob/8e1e3f159a78d7c81f6e1abc0dcc2e70d8828d48/apps/cli/src/commands/agents-auth.ts
[fold-npm]: https://registry.npmjs.org/@humanlayer%2Ffold-codex/0.1.32
[fold-pkg]: https://github.com/humanlayer/fold/blob/3110435925bc206f6d18d501d40580e9c459d6d7/packages/fold-codex/package.json
[fold-lock]: https://github.com/humanlayer/fold/blob/3110435925bc206f6d18d501d40580e9c459d6d7/bun.lock
[fold-license]: https://github.com/humanlayer/fold/blob/3110435925bc206f6d18d501d40580e9c459d6d7/LICENSE
