# 《诡秘世界》工程交付基线 v1.0

> **状态**：工程交付基线  
> **日期**：2026-09-16  
> **首发形态**：macOS 26+ / Apple Silicon arm64，单真实用户、本地持久世界  
> **工程形态**：SwiftUI App + 同机独立 Local Engine Service  
> **AI Runtime**：AgentScope 2.0.8（lockfile 精确固定）  
> **数据内核**：SQLite-centered Local Multi-model Architecture  

---


## 0. Engineering GO

工程主线进入大规模并行开发前，以下 P0 Gate 必须全部通过：

```text
GATE-PACKAGE
GATE-PROTOCOL
GATE-DATA
GATE-AI
GATE-GOLDEN-MOCK
```

执行规范位于 `07_工程启动/`。

当前包定义 **如何验证和达到 GO**；未执行的技术 Gate 不因文档存在而被视为已通过。

## 1. 一句话定义

《诡秘世界》是一套以 Canon 为历史底座、以持续世界状态为现实、以人物长期身份与记忆为主体、以语音驱动互动叙事为主要体验的单人持久世界应用。

世界不会因一篇故事结束而重置；人物不会因一次模型调用重新生成；模型不能直接修改世界事实。

---

## 2. 规范架构

```text
                         Lore / Canon
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│                    Domain Truth                         │
│  World Engine · Character Engine · Memory & Knowledge  │
│  Story Engine · Outcome Resolver · Validators           │
└───────────────────────────┬─────────────────────────────┘
                            │
                   Session Orchestrator
                            │
                  ┌─────────┴─────────┐
                  ▼                   ▼
           Context Compiler      Deterministic Core
                  │                   │
         Authorized Context           │
                  ▼                   │
        Mysterious AI Gateway         │
                  │                   │
             AgentScope 2.0.8           │
        ┌─────────┼─────────┐         │
        ▼         ▼         ▼         │
   Model Call  Bounded Agent Tools    │
        └─────────┬─────────┘         │
                  ▼                   │
             Typed Proposal ──────────┘
                  │
          Resolver / Validators
                  │
                COMMIT
                  │
                  ▼
         Narrative / Performance
                  │
                  ▼
           Audio / Voice Engine
                  │
                  ▼
                User
```

`COMMIT` 是事实与表达的硬边界。Narrative、TTS、UI 重试不得改变已提交命运。

---

## 3. 部署基线

```text
┌───────────────────────────────────────────┐
│                    Mac                    │
│                                           │
│  SwiftUI App                              │
│      │                                    │
│      │ local typed IPC                    │
│      ▼                                    │
│  Embedded Local Engine Service            │
│      ├─ Python 3.14.7（CPython standard GIL build） runtime               │
│      ├─ Domain Engines                     │
│      ├─ AgentScope                         │
│      ├─ SQLite                             │
│      └─ Model / Speech adapters            │
│                                           │
└───────────────────────────────────────────┘
                 │
                 └──── optional network ───→ Cloud Models
```

Engine 随 App 分发、与 App 位于同一台设备、独立进程运行、由 App 管理生命周期。Domain Database 只由 Engine 读写。

---

## 4. 数据基线

```text
canon.db       = immutable Canon truth
world.db       = authoritative mutable world
retrieval.db   = rebuildable search projection
runtime.db     = non-domain runtime trace / diagnostics
assets/        = audio / image / export binary assets
```

`world.db` 使用强事务；`retrieval.db` 通过 Transactional Outbox 异步投影，不参与 Domain 原子事务。

检索采用：

```text
Authorization
→ Structured / Graph / FTS / Vector candidate generation
→ Rank fusion
→ Domain rerank
→ Token-budget packing
```

隐藏事实和角色无权获知的知识在语义排序之前被排除。

---

## 5. AI Runtime 基线

| 工作单元 | 实现 |
|---|---|
| Advice Interpreter | AgentScope structured model call |
| Character Reasoner | AgentScope structured model call |
| Outcome Resolver | Deterministic Domain Code |
| Story Director | Bounded AgentScope Agent |
| Narrative Compiler | AgentScope structured model call |
| Memory Distiller | AgentScope structured model call |
| Canon / Capability Validation | Domain rules first |
| World Pulse Planner | 不进入 MVP 持续运行路径 |

AgentScope 管理 AI execution，不管理 world truth。

AgentScope Runtime Memory 不作为 Character Memory、Knowledge、Relationship 或 World Event 的事实源。

---

## 6. 规范文档

### 产品

- `00_产品/诡秘世界_PRD_产品基线_v1.0.md`
- `00_产品/产品体验与交互基线_v1.0.md`

### 总体架构与 ADR

- `01_总体架构/总体架构基线_v1.0.md`
- `01_总体架构/ADR-001_本地引擎部署拓扑.md`
- `01_总体架构/ADR-002_数据架构.md`
- `01_总体架构/ADR-003_AgentScope_AI_Runtime.md`
- `01_总体架构/架构专家评估与系统优化报告_v1.0.md`

### Domain Engines

- `02_领域引擎/World_Engine_v1.0.md`
- `02_领域引擎/Character_Engine_v1.0.md`
- `02_领域引擎/Story_Engine_v1.0.md`
- `02_领域引擎/Lore_Engine_v1.0.md`
- `02_领域引擎/Memory_Knowledge_Engine_v1.0.md`
- `02_领域引擎/Audio_Voice_Engine_v1.0.md`

### Engineering

- `03_工程规范/AgentScope_Integration_v1.0.md`
- `03_工程规范/Context_Compiler_v1.0.md`
- `03_工程规范/Runtime_Orchestration_v1.0.md`
- `03_工程规范/Engine_API_Contracts_v1.0.md`
- `03_工程规范/Data_Architecture_v1.0.md`
- `03_工程规范/macOS_App_Platform_Baseline_v1.0.md`
- `03_工程规范/Swift6_Xcode27_Best_Practices_v1.0.md`
- `03_工程规范/Schema_Contracts_v1.0.md`
- `03_工程规范/Engine_Quality_Gates_v1.0.md`
- `03_工程规范/Technical_Vertical_Slice_v1.0.md`
- `03_工程规范/人机协同研发工作框架_v1.0.md`

### Executable Contracts

- `03_工程规范/schemas/*.schema.json`
- `04_Golden_Scenarios/golden_001/*`

### UI

- `05_UI/UI_交互基线_v1.0.md`
- `05_UI/Interaction_Runtime_State_v1.0.md`
- `05_UI/assets/01_世界首页_概念参考.png`
- `05_UI/assets/02_人物档案_概念参考.png`
- `05_UI/assets/05_卡牌详情_概念参考.png`
- `05_UI/assets/06_卡牌馆_概念参考.png`

命运介入页与 Story Player 当前没有被批准的视觉稿；两者以交互规范为准，不以旧图作为实现基线。

---


### Engineering Launch

- `07_工程启动/README.md`
- `07_工程启动/工程实施准备与技术Spike规格_v1.0.md`
- `07_工程启动/Local_Engine_Packaging_Spike_v1.0.md`
- `07_工程启动/IPC_Protocol_v1.0.md`
- `07_工程启动/Data_Kernel_Spike_v1.0.md`
- `07_工程启动/AgentScope_Spike_v1.0.md`
- `07_工程启动/Security_Privacy_Baseline_v1.0.md`
- `07_工程启动/Repository_CI_Baseline_v1.0.md`
- `07_工程启动/Content_Provenance_Release_Gate_v1.0.md`
- `07_工程启动/Canon_Content_Accuracy_Baseline_v1.0.md`
- `07_工程启动/CONTENT_CLASSIFICATION.json`
- `07_工程启动/golden_001_runtime/`
- `07_工程启动/Go_NoGo_Gates_v1.0.yaml`
- `07_工程启动/Engineering_Tasks_v1.0.yaml`
- `07_工程启动/TRACEABILITY.md`
- `07_工程启动/protocol/`

### Baseline Metadata

- `BASELINE.json`
- `BASELINE_VALIDATION.json`
- `FINAL_VALIDATION.json`
- `CONSISTENCY_BASELINE.md`
- `ASSET_INDEX.md`
- `MANIFEST.sha256`

## 7. 规范优先级

不同关注点使用对应规范：

1. 产品行为：PRD。
2. UX 行为：体验与 UI 交互基线。
3. Domain 语义：各 Engine 规格。
4. 架构选择：ADR。
5. 数据、运行时和调用边界：工程规范。
6. 结构化对象：JSON Schema。
7. 回归行为：Golden Scenario Assertions。

本基线目录只包含当前规范资产；未列入资产索引的文件不具有规范效力。

---

## 8. 不变量

1. 世界先于故事。
2. 角色先于剧情。
3. Canon 定义已经发生的历史，不锁死未发生的未来。
4. Advice 不等于 Command。
5. Models / Agents 只产生 Proposal；Domain Engine 才能 Commit。
6. Character Reasoner 永远不接收超出角色知识边界的事实。
7. Context Compiler 决定“有资格看到什么”；AgentScope 只负责“如何执行模型上下文”。
8. Domain Memory 与 Agent Runtime Memory 完全分离。
9. Narrative 与 Audio 位于 Commit 之后。
10. User World 永不反向修改 Canon。
11. `world.db` 是用户世界权威持久层；检索索引必须可重建。
12. App 不直接读写 Domain Database。
13. 默认不运行后台 MMO 式全量 NPC 自主模拟。
14. 世界时间由叙事事件推进，不直接绑定现实时间。
15. 任何重大 Worldline 分叉必须显式登记。

---

## 9. 当前实施门槛

设计基线进入可执行纵向切片时必须通过：

- Embedded Local Engine 启动、退出、崩溃恢复；
- AgentScope exact-version pin 与 structured output；
- `world.db` 强事务与 Outbox；
- `retrieval.db` 删除后完整重建；
- Golden Scenario 001 五轮 E2E；
- Knowledge Leak / Capability / Canon / Revision hard gate；
- App 重启后 World、Character、Story Book 状态保持一致；
- Narrative/TTS retry 不改变 StoryState。

通过上述门槛后，系统进入可扩展内容生产阶段。
