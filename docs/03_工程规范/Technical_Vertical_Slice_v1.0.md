# Technical Vertical Slice v1.0

> **状态**：可执行纵向切片基线  
> **目标**：让 Golden Scenario 001 在真实 Local Engine + AgentScope + SQLite 架构中完整运行，并据此冻结 Engine Architecture v1.0。

## 1. 最终演示链路

```text
Launch SwiftUI App
  ↓
Start bundled Local Engine
  ↓
IPC handshake
  ↓
Open canon.db / world.db
  ↓
Recover pending transactions / projections
  ↓
Start Golden 001
  ↓
5 voice/text advice turns
  ↓
Advice → Character → Resolver → Validate → Commit
  ↓
Director → Narrative → Audio
  ↓
Closure
  ↓
Atomic Episode Finalization
  ↓
App exit
  ↓
App reopen
  ↓
World / Character / Story Book remain correct
```

## 2. Spike A — Local Engine

验证：

- bundled Python 3.14.7；
- AgentScope exact pinned version；
- Apple Silicon；
- process lifecycle；
- Unix Domain Socket；
- structured streaming events；
- App Sandbox / signing；
- engine crash/restart。

## 3. Spike B — Data Kernel

验证：

- `world.db` STRICT/FK/WAL/FULL；
- single Domain Writer；
- event/revision；
- transactional outbox；
- `retrieval.db` delete/rebuild；
- FTS trigram；
- VectorIndexProvider exact mode；
- hybrid retrieval；
- crash after domain commit。

## 4. Spike C — AI Runtime

实现：

- Advice Interpreter；
- Character Reasoner；
- Bounded Story Director；
- Narrative Compiler；
- Memory Distiller；
- schema/Pydantic；
- prompt/model/version trace。

## 5. Spike D — Domain Loop

实现：

- World snapshot；
- Character state；
- Memory/Knowledge；
- StorySession；
- Outcome Resolver；
- validators；
- Episode Finalization。

## 6. Golden Dataset

基础测试规模之外，数据层使用 synthetic benchmark：

```text
entities        10k
relationships   100k
memories        20k
retrieval docs  20k
vectors         20k
```

测量：

- lookup
- 1–3 hop retrieval
- FTS
- vector top-k
- hybrid retrieval
- Episode commit
- outbox projection
- startup/rebuild

## 7. Done Definition

必须满足：

- UI 与 Engine 进程隔离；
- AgentScope 不持有 Domain write capability；
- Golden 001 五轮全部完成；
- 所有 fixtures 通过 schema；
- Hidden Truth leak = 0；
- Episode Finalization 原子；
- `retrieval.db` 可删除重建；
- App restart 后状态一致；
- Narrative/TTS retry 不改变事实；
- engine crash 后从最近 durable stage 恢复；
- latency / failure / retrieval metrics 可观测。

## 8. 非目标

本阶段不实现：

- 22 条途径完整 Lore；
- 全量 Canon 知识图谱；
- 后台持续 NPC 社会模拟；
- Cloud multi-user；
- Multi-device concurrent write；
- RealtimeAgent 作为正确性关键路径；
- 大规模 ANN。
