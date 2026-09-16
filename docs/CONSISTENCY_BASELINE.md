# Consistency Baseline v1.0

> **状态**：跨资产一致性基线  
> **适用范围**：本交付包中的全部规范、Schema、Golden Fixture、工程 Gate 与 UI 运行态。

## 1. 术语

统一使用：

```text
PlayerAdvice
Character Reasoner
ActionIntent
StateDelta
BeatPlan
ClosurePlan
NarrativeBlock
PerformancePlan
AudioAssetRef
```

“建议方向”是 UI affordance，不是合法 Action 白名单。

## 2. 事实边界

```text
CanonFact
≠ World Truth
≠ WorldObservation
≠ CharacterKnowledge
≠ CharacterBelief
≠ CharacterMemory
≠ Narrative
```

任何层之间的转换都有显式 Engine / Validator。

## 3. AI 边界

```text
AgentScope / Model
→ Proposal
→ Domain Validation
→ Commit
```

AgentScope 不直接持有：
- World Truth；
- Character Memory Truth；
- Knowledge / Belief；
- Relationship Truth；
- Worldline；
- Domain Transaction。

## 4. Story Turn 边界

```text
FinalTranscript / Text
→ PlayerAdvice
→ Character Reasoner
→ ActionIntent
→ Outcome Resolver
→ StateDelta
→ Validators
→ COMMIT Session Fact
→ Story Director
→ BeatPlan
→ NarrativeBlock
→ Performance / Audio
```

Narrative / Audio 重试不重新决定 Outcome。

## 5. Session 与长期世界

每个 Turn 的 Commit 写入 durable StorySession Overlay。

```text
Global State at base revision
+
Committed Session Overlay
=
Effective Story State
```

Episode Finalization 才把 Overlay 晋升为长期 Global Domain State。

已有 committed Turn 的 Session：
- 可以 suspend；
- 可以 resume；
- 可以 Closure；
- 不允许静默 discard。

## 6. Memory / Knowledge

Character Reasoner 不直接修改长期 Memory / Knowledge。

```text
ActionIntent
→ Outcome
→ Observation / StateDelta
→ Memory & Knowledge Engine
→ Candidate
→ Validator
→ Commit
```

长期 Memory Distillation 在 Episode Finalization 执行，不在每个 Turn 执行。

## 7. Worldline

Worldline 分叉使用：

```text
Materialized Current State
+
Lineage History
```

Child 继承 fork boundary 之前的有效历史，但不复制成第二份 Episode/Memory Truth；Parent fork 后事件不进入 Child。

## 8. 数据

```text
canon.db     = immutable Canon truth
world.db     = authoritative mutable Domain state
retrieval.db = rebuildable projection
runtime.db   = diagnostics
```

`retrieval.db` 不参与 Domain 原子事务。

Graph：
- specialized Domain relation table = Truth；
- unified cross-domain graph = Projection。

Vector / FTS：
- retrieval signal；
- 不具备知识授权能力。

## 9. UI / Voice

UI 运行态映射 Engine 状态。

PRE_COMMIT：
- 可取消 pending Turn。

POST_COMMIT：
- 可停止 Narrative/Audio；
- 不回滚事实。

麦克风 / ASR device lifecycle 属于 SwiftUI / Media Runtime；Local Engine 从 FinalTranscript 开始参与 Story Turn。

## 10. Canon 内容

Golden 001 是 TestFixture，不是 Canon。

硬 Canon 约束只来自：
- verified CanonFact；
- verified CanonRule；
- time/profile-correct Canon Snapshot。

Interpretation、Creative Lore、Generated World Fact、TestFixture 不得伪装为 Canon。

## 11. 正式交付语义

本包中的规范直接描述 v1.0 当前有效基线。工程实现不得从已被排除的旧版本、旧 UI 图或阶段性讨论稿重新引入不同语义。
