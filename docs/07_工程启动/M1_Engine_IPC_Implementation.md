# M1 IPC foundation — implementation ledger

Task: `M1-IPC-FOUNDATION`. Refs #43, #44, #45. Base: `main@501d46fa3a6262b0ed501d96807377c3a13a50e4`.

## Approved boundary

The user approved strict contract unification and a dedicated parent-child credential pipe, conditional on no additional end-user configuration, account, network dependency, cost or permission steps. This is not approval of automatic merge or of new gameplay/engine decisions. Preserve committed world facts. The scope of this coordinated prerequisite is recorded in its new capsule; no existing capsule or protected gate is modified.

## Increment 1 — contract

- Canonical schema in `contracts/protocol/`; documentation path is a reference only.
- Request/response/event shapes, structured errors, identifiers and nonnegative stream sequence/revision are enforced in Schema, Python and Swift.
- Error and success payloads are exclusive; absent optional fields are omitted instead of sent as null.
- Shared positive/negative fixture corpus drives Python and Swift tests. Preview constructors remain source-compatible, but malformed values cannot be encoded or decoded on the wire.
- Handshake payload declares the private, per-launch credential; no credential value is logged.

## Evidence at this increment

- 112 focused Python/contract tests passed on Python 3.13.5 in the Linux workspace (not the locked Python 3.14.7 environment).
- 92 corpus decisions passed using the actual production Swift envelope compiled with Swift 6.2.1; accepted Swift output was revalidated against Schema and Pydantic.
- Architecture static checks and capsule schema passed.
- This does not claim full SwiftUI/Xcode tests, target Mac performance, packaging, real service implementation, Golden 001 or database persistence.

## Increment 2 — real system transport

- Added a real independent UDS server, private bootstrap pipe and per-connection authentication.
- System health reports transport readiness separately from unavailable world/model/voice capability; unknown methods fail closed.
- Bounded framing, strict JSON, fragmented/coalesced input, correlated FIFO replies and concurrent clients.
- Private runtime/socket permissions, exclusive startup lease, confirmed stale-socket recovery and inode-checked cleanup.
- Normal shutdown, signal shutdown with active/partial clients, crash/restart and old-token rejection have actual subprocess tests.
- Aligned integral JSON numbers and handshake constraints across the contract models. The shared corpus now has 94 cases; numeric wire spellings are tested without pre-normalization.
- Initial macOS CI found an empty-payload compatibility regression in the existing Artifact adapter test. Empty objects now remain absent typed business results; malformed nonempty payloads still fail. The existing test is unchanged and a focused regression test was added.

### Local evidence

189 focused Python/contract/transport assertions passed on Python 3.13.5/Linux, including real independent-process tests. The 94-case production Swift codec/reverse roundtrip and the empty-payload regression probe passed with Swift 6.2.1/Linux. These are not the pinned full runtime or target App acceptance. The initial commit's Capsule Gate and Python CI passed; its Swift test failure motivated the compatibility fix. New-head CI must be read separately.

### Remaining product integration

App lifecycle integration, signed bundled Python, automatic first-run/reconnect on the target Mac, real story handlers and persistence remain subsequent tasks. No new user operations are added by the internal design, but end-user-invisible startup/performance has not been accepted. Keep #43–#45 open. No merge is authorized.
