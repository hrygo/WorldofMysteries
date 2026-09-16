# Repository & CI Baseline v1.0

> **状态**：工程治理基线

## 1. Repository Layout

```text
repo/
├── contracts/
│   ├── schemas/
│   └── protocol/
├── engine/
│   ├── domain/
│   ├── application/
│   ├── infrastructure/
│   ├── ai/
│   └── tests/
├── macos-app/
│   ├── App/
│   ├── IPC/
│   └── Tests/
├── content-pack-tools/
├── fixtures/
│   └── golden_001/
├── scripts/
├── docs/
│   └── adr/
└── .ci/
```

## 2. Ownership Boundaries

- `domain/` 不 import AgentScope、SQLite driver、provider SDK。
- `application/` 组织 use case / transaction。
- `infrastructure/` 实现 SQLite、IPC、assets。
- `ai/` 实现 AgentScope Adapter / Model Router / Prompt Registry。
- `macos-app` 不 import Python / AgentScope 类型。
- `contracts` 是跨语言协议源。

## 3. Dependency Lock

必须锁定：
- Python version；
- AgentScope；
- model provider SDKs；
- SQLite extension build/version；
- embedding model；
- Swift package versions；
- build tooling。

CI 检查 lockfile 未漂移。

## 4. Branch / Review Gates

任何改变以下内容必须包含 ADR 或 Contract review：

- authoritative schema；
- protocol major/minor；
- worldline semantics；
- commit boundary；
- Knowledge authorization；
- Agent tool permissions；
- persistence durability；
- Canon Pack format。

## 5. CI Stages

```text
01 contract
02 static analysis
03 unit tests
04 database migration/recovery
05 golden mock
06 retrieval authorization
07 agent eval
08 Swift/Python protocol roundtrip
09 packaging smoke
10 artifact manifest
```

## 6. Contract CI

- JSON Schema metaschema；
- Golden fixtures；
- Pydantic validation；
- Swift Codable fixture roundtrip；
- no unknown enum drift；
- protocol examples。

## 7. Data CI

- migrations；
- FK；
- quick_check；
- atomic rollback；
- idempotency；
- outbox；
- delete/rebuild retrieval；
- worldline isolation。

## 8. AI CI

MockProvider 为 PR 必跑。

真实模型 Eval：
- 可按计划/受控凭据运行；
- 不作为每个小 PR 的 deterministic unit gate；
- 模型升级使用 shadow replay / eval baseline。

## 9. Packaging CI

至少 nightly/release：
- build macOS App；
- bundle Engine；
- launch handshake；
- engine kill/restart；
- codesign validation；
- dependency/SBOM artifact。

## 10. Artifacts

每个候选 Release 产出：
- App artifact；
- Engine dependency manifest；
- Schema bundle；
- migration bundle；
- Golden results；
- SBOM / third-party notices；
- SHA-256 manifest。

## 11. PASS

`Repository / CI readiness`：
- 新开发者可从 clean checkout 运行 deterministic test suite；
- Golden Mock 可一条命令执行；
- CI 能阻止 Contract/Schema/Knowledge/Transaction 回归；
- packaging smoke 自动化。
