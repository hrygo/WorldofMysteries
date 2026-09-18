# Executable Baseline v1.0

> **状态**：实施目标  
> **阶段目标**：完成第一条真实可执行纵向切片，并冻结 Engine Architecture v1.0。

## 1. 实施范围

### Local Engine
- macOS App 随包分发 Python 3.14.7 Local Engine；
- SwiftUI 与 Engine 分进程；
- typed UDS IPC；
- Engine-owned Domain DB；
- launch / shutdown / crash recovery。

### AgentScope
- pin 精确 2.x 版本；
- structured output；
- Character Reasoner；
- bounded Story Director；
- Narrative Compiler；
- trace / model metadata。

### Data
- canon.db；
- world.db；
- retrieval.db；
- transactional outbox；
- FTS5；
- VectorIndexProvider exact mode；
- Hybrid Retrieval；
- snapshots / integrity。

### Domain
- World；
- Character；
- Memory & Knowledge；
- Story；
- Context Compiler；
- Outcome Resolver；
- validators。

### Experience
- Golden 001 Story Player minimal flow；
- voice/text advice input；
- Story Book persistence；
- app restart continuity。

## 2. 实施顺序

2026-09-18 执行顺序补充：以 [Persistent World Alpha 计划](Persistent_World_Alpha_Plan_v1.0.md) 落实第一条真实闭环。下文 M0–M9 仍为技术能力章节编号，不等同于 `PROJECT_STATE.json` 导航里程碑编号；不删除任何 Gate。

```text
Contract 基线
  ├─ Local Engine / App IPC（真实进程）
  ├─ Data Kernel / Outbox（真实持久事务）
  └─ Golden 断言与故障点准备（立即开始）
              ↓
Domain / Context / Memory / Application + 固定模型输出
              ↓
第一轮真实 Commit → Golden 001 五轮
              ↓
Episode 原子结算 / 重启连续性 / 故障恢复
              ↓
真实 AgentScope 模型端到端接入 / 基础语音 / 历史回放
              ↓
目标 Mac 独立体验与全部既有 Gate → Engine Architecture v1.0
```

仅 Mock 模型输出；Orchestrator、Resolver、Validators、revision、幂等、SQLite transaction、记忆写回、Outbox、Finalization 与 Recovery 都必须是真实代码。AI 接口与版本固定可并行准备，真实 LLM 不阻断确定性 Golden Mock；知识授权边界从第一轮就存在。不得先交付一次性故事、再补持久世界。

## 3. M0 — Contract Freeze

完成：
- JSON Schema；
- Pydantic models；
- Swift IPC DTO；
- stable IDs；
- error taxonomy；
- version negotiation。

Gate：
- Golden fixtures 100% schema valid。

## 4. M1 — Local Engine

Gate：
- App 启动 Engine；
- handshake；
- App 退出 Engine 正常退出；
- Engine crash App 不崩；
- Engine 可重启恢复；
- sandbox/signing 可发布。

## 5. M2 — Data Kernel

Gate：
- Episode transaction rollback；
- WAL/FULL durability profile；
- outbox crash recovery；
- retrieval.db 删除重建；
- backup/restore；
- integrity checks。

## 6. M3 — Repositories

实现：
- WorldRepository
- CharacterRepository
- KnowledgeRepository
- MemoryRepository
- RelationshipRepository
- StoryRepository
- CanonRepository
- OutboxRepository

Gate：
- Domain Engine 不包含直接 SQL。

## 7. M4 — AgentScope AI Gateway

Gate：
- pinned runtime；
- structured outputs；
- Agent tools read/proposal only；
- Story Director bounded；
- model provider replaceable；
- trace complete。

## 8. M5 — Context / Memory / Knowledge

Gate：
- hidden truth leak = 0；
- wrong-character memory leak = 0；
- future Canon leak = 0；
- structured + lexical + vector hybrid retrieval；
- authorization before semantic search。

## 9. M6 — Golden 001

五轮完整运行并满足所有 G001–G012 assertions。

## 10. M7 — Finalization

Gate：
- Episode / Character / Memory / Knowledge / Relationship / WorldEvent 同一 world.db transaction；
- partial commit = 0；
- outbox independently retryable。

## 11. M8 — Voice

Gate：
- final transcript only enters transaction；
- PRE_COMMIT cancel；
- POST_COMMIT barge-in 不回滚；
- TTS failure falls back to text；
- Story Book replay is historical asset replay。

## 12. M9 — Failure Injection

注入：
- model timeout；
- invalid structured output；
- engine crash；
- SQLite write failure；
- projection failure；
- TTS failure；
- app restart；
- corrupted disposable retrieval index。

## 13. Definition of Done

用户能够：

```text
打开 App
→ 进入 Golden World
→ 进行五轮建议
→ 完成 Episode
→ 关闭 App
→ 重新打开
→ 世界保留历史
→ 人物记得经历
→ Story Book 可回放
→ 下一篇 Story 能读取前次结果
```

同时满足：
- Domain truth 无模型直写；
- no knowledge leak；
- no invalid capability；
- exact reproducible committed history；
- retrieval projection 可重建。
