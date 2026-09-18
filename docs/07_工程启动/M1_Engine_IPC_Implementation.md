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

## Remaining increment

Implement and test the real UDS process, private bootstrap pipe, authenticated system methods, bounded framing, connection handling and safe socket lifecycle. App lifecycle integration, signed bundled Python, real story handlers and persistence remain subsequent tasks. Keep #43–#45 open.
