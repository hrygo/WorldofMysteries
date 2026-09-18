# M1 App–Engine session implementation

## Scope and baseline

- Tracks #45 under #43; consumes the real system transport merged by #50.
- Base: `main@f7fa79c718cc80f15a261d1f195d731a3a3f2987`.
- Branch: `feat/app-engine-session`; capsule: [M1-APP-ENGINE-SESSION](../../.agents/capsules/M1-APP-ENGINE-SESSION.json).
- Contribution sources: [AGENTS](../../AGENTS.md), [CONTRIBUTING](../../CONTRIBUTING.md), [PR template](../../.github/PULL_REQUEST_TEMPLATE.md), [CODEOWNERS](../../.github/CODEOWNERS), existing macOS/collaboration Skills and [IPC protocol](IPC_Protocol_v1.0.md).
- The user approved internal IPC/bootstrap work only without new end-user configuration, permissions, fees, network dependencies or save migration. This implementation does not certify installed-app acceptance.

## Increment 1: actual transport and owned child lifecycle

The production Swift client now opens a real nonblocking UDS. One private dispatch queue and `Synchronization.Mutex` own descriptor state, bounded reads/writes, request correlation and continuations. There is no `@unchecked Sendable`, blocking socket read on the UI actor, echo implementation or automatic mutation replay. Per-request cancellation/timeout terminates that connection rather than guessing whether a mutation committed. Calls require authenticated, advertised capabilities.

The 4-byte big-endian framing matches the existing contract: 1 MiB per body, 64 JSON levels, UTF-8 validation, duplicate-key rejection (including escaped-equivalent keys), finite JSON numbers and bounded partial-frame time. Requests have both request/trace correlation; pending requests and output buffering are bounded. Events have bounded buffering and monotonically increasing per-stream sequence. Connection-failure observation uses a separate stream, so lifecycle monitoring cannot consume narrative events. This is not durable event replay.

`EngineProcessManager` owns the executable, launch token and a fresh private Runtime directory. Concurrent starts coalesce; stop/start ordering prevents stale cleanup from killing a newer session. Bootstrap credentials pass through a small pipe filled before launch and closed afterwards. They do not enter argv, ordinary logs or files. Python is invoked without a shell and without user-site/environment Python injection. A normal stop requests SIGTERM, then escalates after two seconds if necessary, and waits for Foundation to reap the owned child off the UI actor. Resource removal is nonrecursive and checks directory identity and the socket lock.

Only ephemeral socket paths may fall back from Application Support to the app's temporary directory when the Darwin `sun_path` limit would otherwise prevent startup. Each launch still gets a private 0700 subdirectory. No database or user document is relocated. An explicitly injected overlong test/development path fails rather than being silently rewritten.

The Python system server accepts an optional parent PID supplied by the App. It validates the actual parent before binding and checks parent identity while running. App force-quit or crash therefore stops the child instead of leaving an orphan daemon. Normal App termination uses an `NSApplicationDelegate` termination barrier to await cleanup before replying to macOS.

## Honest App integration

`AppState` runs launch → connection → authenticated handshake → typed health. Transport availability is independent of world/model/voice availability. The current system-only Engine remains `transportReady`, not world-ready. All current world surfaces remain explicitly labelled as demo data; an IPC connection does not turn `DemoWorldSnapshot` into world facts.

An unexpected connection loss immediately clears capability/world context and permits at most two transport restarts in that session. A repeated crash exhausts the budget; shutdown cancels recovery. Reconnection never resends Advice or other world mutations. The editable Advice draft has no submission or voice callback until an actual business integration exists, so it is not discarded and no fake deciding/listening state is produced.

Production discovery only accepts the App resource layout `LocalEngine/bin/python3` plus `LocalEngine/engine`. An explicit executable/module-directory injection is available for development and tests, not as an end-user requirement. There is no PATH search, automatic download or fallback to a user's Python. A missing bundle reports a typed unavailable state.

## Validation ledger

Local execution uses Python 3.13.5 and Swift 6.2.1 on Linux; this is compatibility evidence, not the pinned macOS gate.

- 16 real cross-process cases passed: production Swift transport/process manager and AppState against a separately launched Python server; authenticated health, concurrent starts/requests, wrong-token rejection, child crash/new credentials, cancelled startup, stop during startup, automatic reconnect, bounded crash-loop recovery, parent force-quit and hostile/fragmented peer responses.
- 174 existing/new framing, server and schema cases passed, including three invalid-parent cases.
- Swift compilation uses strict Swift 6 concurrency. The Linux distributed Observation dynamic library has an unresolved runtime symbol; Linux integration tests use the toolchain's actual static standard libraries. macOS uses its native dynamic libraries. No Observation, AppState, process or transport substitute is used.
- The integration driver includes the exact production `ArtifactContext` declaration from its source file to avoid unrelated SwiftUI imports in the portable executable; it does not replace that data type with an invented stub.
- Additional Swift Testing suites cover frame/parser and typed availability failures. Their target macOS execution and the full Xcode App target must be verified in CI before acceptance.
- Architecture fitness, protected-profile registry, required-check contract and whitespace guards passed locally. Native GitHub DNS and `rtk` are unavailable; verified Git bundles supplied source/history, and connector Git objects publish changes.

Any subsequent CI results and verifier-generated Work Receipt are attached to the actual tested commit, not inferred from these local results. No protected gate, registry, protocol schema, lockfile or build configuration is changed in this slice.

## Remaining work

This slice does **not** contain a packaged Python distribution, signed/notarized installed-app verification, business handlers, database mutations, durable idempotency, cancellation across Commit, event replay, Golden five-turn persistence, or world-history recovery. The resource lookup is implemented, but the required runtime bytes and release pipeline are not yet delivered. Therefore the default current App may truthfully report the missing bundled runtime; users are not instructed to install Python as a workaround.

The next packaging/integration increment must supply and verify the pinned arm64 runtime, measure installed-app startup/recovery, and preserve the user's zero-configuration condition. #43/#44/#45 remain open until their full acceptance scope is actually verified. No merge or release is authorized by this document.

## Increment 2: target-macOS regression closure

The initial candidate `7aa75a6` passed 282 of 283 Python cases on macOS; its valid fragmented-response fixture exceeded an artificial 300 ms test deadline while deliberately sleeping after each three-byte chunk. Fragment reassembly now uses the unchanged production five-second request budget. The separate timeout case retains 300 ms and must specifically return `timedOut`; wrong request/trace and malformed frame tests likewise assert their exact errors after a successful handshake. No production timeout or safety limit was relaxed.

The initial Swift suite also exposed a legacy Artifact test that expected a nonexistent socket to connect successfully. That assumption is incompatible with real transport. The replacement verifies unauthenticated resolver rejection and uses the actual, now module-internal `ArtifactIPCCodec` to preserve missing-payload rejection, reject malformed nonempty payloads, and propagate engine denial. No successful connection is simulated. This bounded testability/coverage increment has its own [regression capsule](../../.agents/capsules/M1-APP-ENGINE-REGRESSION.json); the original session capsule is unchanged. Target CI must revalidate the new head before claiming closure.
