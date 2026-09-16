# 工程实施准备与技术 Spike 规格 v1.0

> **状态**：工程启动基线  
> **目标**：在进入大规模功能开发前，完成《诡秘世界》第一条可执行纵向切片的技术可行性验证、跨语言协议冻结、数据可靠性验证和工程门禁建立。

---

# 1. 工程启动原则

工程团队以现有 Design Baseline v1.0 为唯一产品与系统设计输入。

实施前不再扩张新的领域引擎；工程准备阶段只处理以下问题：

1. App 与 Local Engine 能否作为一个可签名、可分发的 macOS 产品稳定运行。
2. `world.db` 是否能够作为长期 Truth Kernel 承担事务、恢复和迁移。
3. AgentScope 是否能够在既定 Domain 边界内稳定执行结构化模型调用和 bounded agent。
4. Swift / Python / JSON Schema 是否能够形成单一、稳定的跨语言 Contract。
5. Golden Scenario 001 是否能够在 Mock Runtime 下完整、确定地运行。
6. 隐私、日志、密钥、备份、内容来源与发布边界是否具有明确规则。
7. CI 是否能够阻止架构不变量、Schema、Golden、恢复性和知识边界的回归。

工程准备阶段完成后，进入功能实现；工程准备阶段不承担完整内容生产、22 条途径数据录入或最终视觉精修。

---

# 2. Go / No-Go 总门禁

工程主线开发仅在以下 Gate 全部通过后进入并行开发状态：

```text
GATE-PACKAGE
  SwiftUI App 能启动随包分发的 Local Engine
          ↓
GATE-PROTOCOL
  Swift ↔ Python typed protocol 可双向通信
          ↓
GATE-DATA
  world.db 在故障注入后保持正确且可恢复
          ↓
GATE-AI
  AgentScope 能稳定输出受 Schema 约束的 Domain Proposal
          ↓
GATE-GOLDEN-MOCK
  Golden 001 在 Mock Model 下 5 Turn 完整通过
          ↓
GO
```

以下 Gate 在进入公开分发前必须通过：

```text
GATE-SECURITY
GATE-CONTENT
GATE-PACKAGING-RELEASE
GATE-VOICE
GATE-E2E-REAL-MODEL
```

---

# 3. P0 工作包

## WP-01 — Local Engine Packaging Spike

### 目标

验证：

```text
Signed SwiftUI App
   ↓
Bundled Local Engine
   ↓
Bundled Python Runtime
   ↓
Pinned AgentScope
   ↓
UDS IPC
   ↓
Structured response
```

### 必须覆盖

- Apple Silicon arm64；
- Debug 与 Release build；
- App Sandbox；
- Hardened Runtime；
- Code Signing；
- Notarization 可行路径；
- App 内 bundled Python Runtime；
- Python package import；
- AgentScope import；
- child/helper process lifecycle；
- Engine stdout/stderr 不污染产品 UI；
- crash detection；
- restart；
- App exit 时 graceful shutdown；
- Engine version handshake；
- App / Engine compatibility error。

### 允许实现形式

产品协议不绑定具体打包工具。Spike 允许对 Python runtime bundling 方案进行实现级比较，但最终产物必须满足：

```text
用户无需预装 Python
用户无需手工启动 Engine
用户无需开放 TCP 端口
用户无需安装 AgentScope
```

### Gate

`GATE-PACKAGE = PASS` 必须提供：

- 签名后的测试 App；
- Release 配置；
- Engine 可启动证据；
- crash/restart 证据；
- architecture / dependency manifest；
- cold-start 时间数据。

---

## WP-02 — Local IPC Protocol Freeze

### 协议

v1.0 使用：

```text
Unix Domain Socket
+
Length-prefixed UTF-8 JSON messages
+
JSON Schema controlled payload
```

HTTP/TCP 不作为 MVP App ↔ Engine 内部协议。

### 协议职责

必须支持：

- handshake；
- request / response；
- server event stream；
- request cancellation；
- idempotency key；
- trace id；
- protocol version；
- method version；
- structured error；
- graceful shutdown；
- heartbeat / health。

### Gate

`GATE-PROTOCOL = PASS`：

- Swift 与 Python 均从同一 Schema contract 生成或验证 DTO；
- unknown field / invalid payload 被拒绝；
- protocol version mismatch 有确定错误；
- request cancellation 可验证；
- connection loss 后可重新连接；
- reconnect 不重复 Domain Commit。

详细规范见 `IPC_Protocol_v1.0.md`。

---

## WP-03 — Data Kernel Spike

### 权威内核

实现：

```text
canon.db   read-only
world.db   authoritative
retrieval.db rebuildable
runtime.db optional diagnostics
```

`world.db`：

```text
STRICT
foreign_keys=ON
WAL
synchronous=FULL
single Domain Writer
revision
idempotency
transactional outbox
```

### 最小表族

- worlds
- worldlines
- entity registry
- domain events
- character states
- relationships
- character knowledge
- character beliefs
- character memories
- story sessions
- story turns
- episodes
- projection outbox
- schema migrations

### Retrieval

实现：

- Alias exact / prefix；
- FTS5 trigram；
- ExactVectorProvider；
- Cross-domain Graph Projection；
- RRF-based Hybrid Retrieval；
- authorization-before-semantic retrieval。

### 故障注入

必须覆盖：

1. Domain transaction 中途退出。
2. Domain commit 后、Outbox 投影前退出。
3. retrieval projection 中途退出。
4. 删除 `retrieval.db`。
5. migration 中途失败。
6. WAL 存在时非正常退出。
7. duplicate idempotency command。
8. expected revision conflict。

### Gate

`GATE-DATA = PASS`：

- partial Episode Finalization = 0；
- `retrieval.db` 可删除并完整重建；
- pending Outbox 可恢复；
- duplicate command 不重复 Commit；
- parent / child worldline 不互相污染；
- integrity / FK checks 通过；
- Golden 数据规模下延迟可观测。

详细规范见 `Data_Kernel_Spike_v1.0.md`。

---

## WP-04 — AgentScope Integration Spike

### v1.0 Worker 形态

```text
Advice Interpreter    → structured model call
Character Reasoner    → structured model call
Outcome Resolver      → deterministic Domain code
Story Director        → bounded Agent
Narrative Compiler    → structured model call
Memory Distiller      → structured model call
```

### Runtime Policy

必须固定：

- Python version；
- AgentScope exact version；
- primary provider adapter；
- fallback provider adapter；
- task model policies；
- max output；
- timeout；
- retry；
- bounded agent max steps；
- bounded agent max tool calls；
- trace metadata；
- structured output validation。

### Story Director

只允许：

- read story state；
- read open threads；
- read pressure；
- read authorized context；
- read ActionIntent；
- propose BeatPlan。

不允许任何 Domain write。

### Gate

`GATE-AI = PASS`：

- structured output 经过 Pydantic / JSON Schema；
- invalid output 只重试当前 Stage；
- Agent 无直接 Domain write tool；
- Story Director 在 bounded limit 内结束；
- provider 替换不改变 Domain Contract；
- Context Compiler 是知识入口；
- AI runtime failure 不破坏已提交 Domain state。

详细规范见 `AgentScope_Spike_v1.0.md`。

---

## WP-05 — Golden 001 Mock E2E

### 目标

Golden 001 在无真实 LLM 随机性的条件下完整运行。

链路：

```text
Open World
→ Start StorySession
→ Turn 1
→ Turn 2
→ Turn 3
→ Turn 4
→ Turn 5
→ Closure
→ Episode Finalization
→ App/Engine Restart
→ State Reload
```

### 固定模型产物

Mock 层必须提供：

- PlayerAdvice；
- ActionIntent；
- BeatPlan；
- NarrativeBlock；
- MemoryCandidate。

Outcome Resolver 不使用 Mock Model；使用真实 deterministic Domain code。

### 每轮断言

必须精确断言：

- story revision；
- discovered clues；
- secret states；
- pressure；
- character state；
- knowledge state；
- relationship state；
- pending outbox；
- transaction status。

### Gate

`GATE-GOLDEN-MOCK = PASS`：

- G001–G012 全部通过；
- Expected State 全部一致；
- restart 后等价；
- Narrative/TTS mock retry 不改事实；
- fixed seed 下 deterministic。

详细规范见 `Golden_001_Executable_Test_Spec_v1.0.md`。

---

## WP-06 — Contract Freeze

### 单一协议源

跨语言 Contract 使用：

```text
JSON Schema Draft 2020-12
```

Python：

```text
Pydantic runtime model
```

Swift：

```text
Codable DTO
```

必须建立自动一致性检查，禁止手工维护两套无验证类型。

### Freeze 范围

- Domain IDs；
- Error taxonomy；
- IPC Envelope；
- Story contracts；
- Character / Knowledge / Memory contracts；
- Context contracts；
- version negotiation；
- enum semantics；
- candidate / committed object distinction。

### Gate

所有 Golden Fixture 通过：

```text
JSON Schema
Pydantic
Swift decode/encode roundtrip
```

---

# 4. P1 工作包

## WP-07 — Security & Privacy Baseline

必须冻结：

- API key → Keychain；
- raw microphone → 默认 ephemeral；
- transcript → Story 输入，按用户世界策略持久化；
- Hidden Truth → 禁止普通 telemetry；
- Prompt / Context → release log 默认不完整落盘；
- Local DB → user-scoped Application Support；
- Domain DB 不默认上传；
- cloud model 只接收 Authorized ContextPacket；
- backup / export；
- world deletion；
- diagnostic bundle redaction；
- crash log redaction；
- filesystem permissions。

详细规范见 `Security_Privacy_Baseline_v1.0.md`。

---

## WP-08 — Repository / CI / Delivery Baseline

必须建立：

```text
contracts
engine
macos-app
tests
fixtures
content-pack-tools
```

以及：

- dependency lock；
- Python type checking；
- Swift build/test；
- JSON Schema validation；
- migration tests；
- Golden Mock tests；
- failure injection tests；
- Agent eval runner；
- license / dependency manifest；
- signed packaging job；
- artifact retention。

详细规范见 `Repository_CI_Baseline_v1.0.md`。

---

## WP-09 — Content Provenance & Release Gate

正式分发内容必须具有：

- source type；
- source locator；
- authority；
- evidence；
- content namespace；
- copyright / license status metadata；
- inclusion policy。

产品 Content Pack 不将“可检索到”视为“可再分发”。

发布 Gate 要求：

- Canon Pack 来源清单完整；
- 原文长文本与衍生素材的分发边界明确；
- UI / 卡牌 /音频素材 provenance 明确；
- 第三方许可证清单完整。

详细规范见 `Content_Provenance_Release_Gate_v1.0.md`。

---

## WP-10 — Interaction State Freeze

在 Fate Intervention 与 Story Player 实施前固定 UI runtime state：

```text
idle
listening
transcribing
interpreting
deciding
resolved_pre_commit
committed
directing
narrating
speaking
interrupted
recovering
closure
error
```

UI 必须映射 Domain/Runtime 状态，而不是发明第二套流程。

PRE_COMMIT 可取消；POST_COMMIT 不回滚。

---

# 5. 性能与可靠性基线

性能指标用于 Spike 验证，不作为虚假的最终 SLA。

至少采集：

```text
App → Engine cold start
IPC request p50 / p95
world snapshot query
1-hop / 3-hop graph query
FTS query
exact vector query
hybrid retrieval
Story Turn commit
Episode finalization
projection delay
retrieval rebuild time
```

可靠性：

```text
duplicate commit rate = 0
partial finalization = 0
knowledge authorization leak = 0
worldline contamination = 0
```

---

# 6. 工程实施顺序

```text
M0  Contract / Protocol Freeze
       ↓
M1  Local Engine Packaging + IPC
       ↓
M2  Data Kernel
       ↓
M3  Repository Layer
       ↓
M4  AgentScope Runtime
       ↓
M5  Context / Memory / Knowledge
       ↓
M6  Golden 001 Mock E2E
       ↓
---------------- GO ----------------
       ↓
M7  Real Model Golden 001
       ↓
M8  Voice / Story Player
       ↓
M9  Episode / Story Book
       ↓
M10 Failure Injection / Release Packaging
```

M0–M6 为工程并行开发前的核心可行性门禁。

---

# 7. No-Go 条件

出现以下任一情况，不进入大规模功能开发：

1. Python/AgentScope 无法稳定随签名 App 分发。
2. Engine crash 会导致 App crash 或世界不可恢复。
3. Swift/Python Contract 无法自动一致性验证。
4. `world.db` 在故障注入下出现 partial finalization。
5. AgentScope Agent 拥有绕过 Domain Command 的写权限。
6. Hidden Truth 能通过 Retrieval/Context 泄漏给无权限角色。
7. Golden 001 Mock 无法 deterministic replay。
8. App restart 后无法恢复最近 durable stage。
9. retrieval index 成为 Domain correctness 的硬依赖。
10. 项目 dependency / content provenance 无法追溯。

---

# 8. Go 条件

工程主线进入并行开发必须同时满足：

```text
GATE-PACKAGE       PASS
GATE-PROTOCOL      PASS
GATE-DATA          PASS
GATE-AI            PASS
GATE-GOLDEN-MOCK   PASS
```

并形成：

- 可重复构建的测试 App；
- 可重复构建的 Local Engine；
- pinned dependency lock；
- machine-readable Gate evidence；
- Golden 001 CI；
- Data recovery CI；
- Schema CI；
- baseline artifact manifest。

---

# 9. 工程实施后的首个可演示目标

```text
启动 macOS App
→ Local Engine 自动就绪
→ 打开 Golden World
→ 进入《不存在的预约》
→ 完成五轮用户 Advice
→ 每轮严格 Commit
→ 完成 Closure
→ Episode 原子写回
→ 关闭 App
→ 再次启动
→ Character 保留 Memory/Knowledge
→ World 保留 Event
→ Story Book 读取历史 Narrative
→ 下一次 Context 可读取前次结果
```

这条链路通过后，Engine Architecture v1.0 进入工程冻结状态。
