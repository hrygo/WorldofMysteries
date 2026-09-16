# 《诡秘世界》World Engine v1.0

> **状态**：Domain Engine 规范基线  
> **权威持久层**：`world.db`  
> **实现约束**：遵循 ADR-002


## 1. 定位

World Engine 是《诡秘世界》的“现实层”。它回答：

1. 现在是什么世界时间？
2. 什么事情已经真实发生？
3. 当前世界状态是什么？
4. 新事件怎样成为历史？

它不负责写故事，也不决定人物说什么。

```text
Lore / Canon
     ↓
World Engine
     ↓
Character Engine
     ↓
Story Engine
     ↓
Narrative / Audio
```

## 2. 核心原则

### 2.1 Event Sourcing

```text
Canon Baseline
      +
World Event Log
      =
Current World State
```

世界不能只存一个巨大 `world_state.json`。重要变化以 append-only WorldEvent 保存，Projection 用于高效读取当前状态。

### 2.2 五层事实必须区分

| 层 | 含义 |
|---|---|
| Canon Fact | 原著已经确定的事实 |
| World Fact | 当前个人世界已经成立的事实 |
| Story Fact | 当前 Story Session 中暂时成立的事实 |
| Character Knowledge | 某个人知道/相信什么 |
| Narrative Text | 用户最终看到或听到的文学表达 |

### 2.3 Canon 只读

运行时不能改写 Canon。发生偏离时，以 Worldline Override / Generated Event 表达。

```text
Effective World Truth
=
Canon Baseline
+ Worldline Overrides
+ Generated Events
```

## 3. Worldline

```yaml
worldline:
  id: wl_main
  parent_worldline_id: null
  fork_event_id: null
  canon_anchor: canon.timeline.xxx
  status: active
```

Major Divergence 后：

```text
Canon / Main
─────────────●──────────────→
             \
              └──────────────→ Worldline 002
```

并非每次介入都创建 Worldline。只有改变重大人物生死、关键历史节点、组织命运、高位力量关系，或使后续重大 Canon 无法成立时，才触发 `DivergenceEvaluator`。

## 4. WorldEvent

WorldEvent 是世界变化的原子。

```json
{
  "id": "evt_xxx",
  "world_id": "world_001",
  "worldline_id": "wl_main",
  "world_time": "...",
  "event_type": "location_destroyed",
  "actors": ["character.xxx"],
  "targets": ["location.red_chimney"],
  "cause": {
    "episode_id": "ep_0072",
    "story_action_id": "act_038"
  },
  "payload": {},
  "visibility": {},
  "persistence": "world",
  "importance": "local",
  "canon_relation": "compatible",
  "provenance": {},
  "revision": 1288
}
```

事件类型由 Domain Registry 管理，模型不能任意发明类型。

`world.db` 保存统一 `DomainEvent` Header，但事件语义归对应 Domain Engine 所有：

```text
CharacterEvent      → Character Engine
RelationshipEvent   → Character / Relationship Domain
KnowledgeChange     → Memory & Knowledge Engine
StoryEvent          → Story Engine
WorldEvent          → World Engine
```

World Engine 的 `WorldEvent` 只表示具有世界状态意义的变化。

### Location

- discovered
- damaged
- destroyed
- occupied
- abandoned
- state_changed

### Organization

- member_joined
- member_left
- leader_changed
- exposed
- influence_changed

### Persistent Mystery

- created
- clue_surfaced
- partially_revealed
- resolved

### World

- major_incident
- public_knowledge_changed
- timeline_diverged

人物移动、受伤、死亡等由 CharacterEvent 表达；当其产生世界可观察后果时，World Engine 通过 Domain Event/Projection 生成对应 Observation。人物获得知识、目标变化和关系变化不转换为 WorldEvent。

## 5. Projection 与 Domain Ownership

`world.db` 同时保存 Domain Event Log 与各领域 Current Projection，但 Projection 由对应 Domain 语义负责：

```text
Domain Event Log
   │
   ├── Character / Relationship Projection  ← Character Domain
   ├── Knowledge / Belief / Memory           ← Memory & Knowledge
   ├── Story Session Projection              ← Story Engine
   ├── Location / Organization / Mystery     ← World Engine
   └── World Summary / Observation           ← World Engine
```

World Home 读取 World Summary / Observation；人物页通过 Character Application View 组合 Character、Relationship、Knowledge、Memory；地点页读取 World Engine 的 Location Projection。

World Engine 不成为其他 Domain Projection 的第二写入者。

持久层使用 SQLite：

```text
Append-only Event Store
+
Mutable Projection Tables
```

核心表：

```text
world_events
characters
character_states
relationships
locations
location_states
organizations
mysteries
worldlines
episodes
snapshots
```

## 6. Revision 与事务边界

每个世界变化具有 `world_revision`。

Story Session 开始：

```yaml
story_session:
  worldline_id: wl_main
  base_world_revision: 328
  world_time: ...
  context_snapshot: ...
```

故事结束写回必须基于 expected revision；若世界已变化，需 Reconcile，禁止盲写。

Story Session 是事务边界：开始时获得 World Snapshot，结束时提交 Proposed Events。

## 7. Story State 与 World State

Story 中大量状态不值得长期保存。

四级 Persistence：

```text
Ephemeral  → 当前 Scene
Episode    → 当前故事
Character  → 跨故事影响角色
World      → 跨故事影响世界
```

Persistence Filter 只把未来仍有意义的变化提交至长期状态。

## 8. 世界时间

```text
现实时间 ≠ 世界时间
```

世界时间由 Episode、Time Skip、World Event 推进。

Time Skip 不能只给日期加数值；应执行 Significant Event Compression：

```text
Advance Time
    ↓
检查 unresolved events
    ↓
检查 ongoing goals
    ↓
生成必要 background consequences
    ↓
Commit meaningful events
```

## 9. World Pulse

“世界仍在发生”不等于后台无限 Agent 模拟。

World Pulse 在以下节点运行：

- Episode 完成
- 用户打开应用
- 用户主动推进世界时间

每次只生成 0–3 个 meaningful event，检查：

- 成熟事件
- 角色 ongoing goals
- unresolved mystery 后果
- 关系反馈

## 10. Visibility 与 Observation Engine

```text
World Truth
     ↓
Visibility / Knowledge
     ↓
Observation Engine
     ↓
User / Character Observation
```

世界发生不等于所有人知道。

首页读取的是 `World Observation Feed`，不是 `World Truth Feed`。

示例：

```yaml
observation:
  event_id: evt_338
  observer: user
  title: 东区的异常死亡
  description: 一具身份不明的尸体在清晨被发现。
  certainty: rumor
  hidden_truth: not_exposed
```

## 11. Context Compiler

任何模型/Agent 禁止直接访问整个世界数据库。

```text
Authorization / Visibility
        ↓
Structured Query
+ Graph Retrieval
+ FTS Retrieval
+ Vector Retrieval
        ↓
Domain Re-ranking
```

按角色编译上下文：

| 调用方 | 可见内容 |
|---|---|
| Story Director | 世界真实状态、Commitments |
| Character Reasoner | 角色可知状态、相关记忆 |
| Advice Interpreter / Suggestion Planner | 当前局势、可执行策略 |
| Canon Guard | Canon、能力边界 |
| Narrator | 可公开叙述信息 |
| UI Observation | 用户当前可知道的信息 |

## 12. World Engine 核心对象

```text
World
Worldline
WorldEvent
WorldFact
Location
Organization
Mystery
Observation
```

`CanonFact` 由 Lore Engine 持有，World Engine 通过 Canon snapshot/reference 消费；Character 由 Character Engine 管理，World Engine 仅引用 Character ID。

## 13. 架构

```text
                Lore / Canon
                     │
                     ▼
               Canon Store
                     │
                     ▼
User Action ──→ World Engine ←── Story Result
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
   Event Store   Projection   Worldline
        │            │
        └──────┬─────┘
               ▼
        World Truth State
               │
        ┌──────┴──────┐
        ▼             ▼
 Knowledge       Observation
 Engine            Engine
        │             │
        └──────┬──────┘
               ▼
        Context Compiler
               │
   ┌───────────┼───────────┐
   ▼           ▼           ▼
Character   Story       UI / Audio
 Engine     Engine
```

## 14. 哲学边界

我们不是做“AI 模拟世界”，而是：

```text
Persistent World State
+
Meaningful Events
+
Generative Narrative
```

只模拟用户可能感知到、并且以后有意义的事情。

---

## 15. 与 Memory / Knowledge Engine 的边界

World Engine 持有世界真实状态与 Observation 生成规则，不直接把 World Truth 写入人物 Knowledge。

```text
World Event
   ↓
Visibility / Observation
   ↓
Memory & Knowledge Engine
   ↓
Character Knowledge / Belief
```

人物知识、信念和长期记忆的持久化归 Memory & Knowledge Engine；数据仍位于同一 `world.db` 权威事务内。

## 16. 与统一 Graph 的边界

World Engine 持有地点、组织、事件因果等领域关系事实。跨域统一 Graph 不作为第二事实源，由 Retrieval Projection 从 Domain Tables 生成。
