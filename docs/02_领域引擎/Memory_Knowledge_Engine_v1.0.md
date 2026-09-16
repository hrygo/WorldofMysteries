# Memory & Knowledge Engine v1.0

> **状态**：领域引擎基线  
> **职责**：管理“角色知道什么、相信什么、记住什么、忘记什么，以及知识如何被获得、修正和传播”。

---

## 1. 定位

Memory & Knowledge Engine 是独立 Domain 子系统。它不属于 AgentScope Runtime Memory，也不等同于向量检索。

```text
World Truth
    │
    ├── Observation ───────────────┐
    │                              ▼
    │                       Knowledge Engine
    │                              │
    │                              ▼
    │                     Character Knowledge
    │
Episode / Interaction
    │
    ├── Memory Candidate ──────────┐
    │                              ▼
    │                        Memory Engine
    │                              │
    │                              ▼
    │                     Character Memory
    │
    └──────────────────────────────┴──→ Context Compiler
```

权威状态持久化在 `world.db`。向量、全文和跨域图索引均为可重建投影。

---

## 2. 核心不变量

1. `World Truth != Character Knowledge != Character Belief != Character Memory`。
2. 角色只能依据其 Knowledge、Belief、Memory、Observation 和当前感知作出决定。
3. AgentScope 的消息历史、压缩上下文和长期运行时 Memory 不是 Domain Memory。
4. Vector similarity 不具备知识授权能力。
5. Knowledge authorization 在语义检索之前执行。
6. 所有长期 Memory 都必须有来源。
7. 重大 Character Change 必须能追溯到 Event / Episode / Interaction evidence。
8. “遗忘”改变检索可用性，不删除历史来源。
9. Canon Character 的 Canon Knowledge 与用户世界新增 Knowledge 分层管理。
10. Memory Distiller 只产生 Candidate；Domain Engine 决定是否持久化。

---

## 3. Knowledge 模型

### 3.1 Knowledge

Knowledge 表示角色具有理由接受为事实的信息。

```yaml
character_knowledge:
  id: know_x
  character_id: char_a
  worldline_id: wl_main
  proposition_id: fact_x
  certainty: 0.72
  source:
    type: observation
    ref: observation_17
    reliability: 0.8
  acquired_world_time: ...
  status: probable
  revision: 42
```

### 3.2 Belief

Belief 允许错误。

```text
World Truth: A 杀死 B
Character Belief: C 杀死 B
```

Belief 与 Knowledge 分开持久化。角色推理使用其自身 Belief，不使用隐藏 Truth 自动纠偏。

### 3.3 Observation

Observation 是 World Truth 经 Visibility、Position、Sense、Spoiler 等规则转换后的可感知信息。

```text
World Event
  ↓
Observation Engine
  ↓
Character Observation
  ↓
Knowledge Acquisition
```

Observation 不自动等于 Knowledge。误导性观察、传闻、低可靠来源可产生低 certainty 的 Knowledge/Belief。

---

## 4. Knowledge Acquisition

合法来源：

- observation
- conversation
- document
- investigation
- ability
- organization
- canon_event
- inference
- memory_recall

写入流程：

```text
Observation / Statement / Evidence
        ↓
Knowledge Candidate
        ↓
Source & Permission Validation
        ↓
Consistency / Conflict Evaluation
        ↓
Commit
```

任何模型不得直接执行 `write_knowledge`。

---

## 5. Knowledge Conflict

同一 proposition 可存在：

- confirmed
- probable
- uncertain
- contradicted
- revoked

新证据不会简单覆盖旧记录，而是生成 Knowledge Change 并保留来源。

对矛盾来源：

```text
old belief
  +
new evidence
  ↓
belief revision candidate
  ↓
Character reasoning / rule evaluation
```

---

## 6. Secret 与 Knowledge

`Secret` 属于 Story/World 中的隐藏事实结构；`Knowledge` 表示某角色知道该秘密的什么部分。

Secret 状态：

```text
hidden → suspected → partial → revealed
```

Character Knowledge 不使用 Story 全局 Secret 状态直接授权。每个角色有独立 Knowledge 记录。

---

## 7. Memory 模型

Memory 表示角色对经历的长期心理记录，而不是事实数据库的复制。

正式类型：

- canon
- episode
- emotional
- relationship
- identity

Memory 至少包含：

```text
summary
source_ids
world_time
importance
emotional_weight
relationship_weight
identity_weight
retention
related_entities
```

---

## 8. Memory 生命周期

```text
Raw Episode / Interaction
        ↓
Important Moments
        ↓
Memory Candidates
        ↓
Consolidation
        ↓
Persistent Memory
        ↓
Decay / Merge / Reinforcement
```

### 保留等级

- permanent
- long
- normal
- decayable

“遗忘”通过降低召回权重、合并或标记 inactive 实现；不破坏原始 Episode/Event history。

---

## 9. Memory Consolidation

Memory Consolidation 发生在：

- Episode Finalization；
- 长会话完成；
- 明确的重大 Interaction；
- 数据维护窗口。

不在每个 Story Turn 执行长期蒸馏。

合并原则：

- 多条相近低价值 Memory 可压缩；
- 重大 Emotional / Identity Memory 保留独立来源；
- Relationship Memory 与 Relationship State 相互引用但不互相替代；
- consolidation 不能改写已发生的事实。

---

## 10. Relationship Memory

Relationship State 表示当前关系；Relationship Memory 表示“为什么变成这样”。

```text
Relationship:
  trust = low

Supporting Memories:
  ep_12: 对方隐瞒重要信息
  ep_19: 对方冒险救助
  ep_27: 再次撒谎
```

关系状态更新必须保留 evidence ids。

---

## 11. Identity Memory

Identity Memory 只用于改变“角色如何理解自己”的长期经历。

晋升条件高于普通 Episode Memory。单次低影响事件不得轻易形成 Identity Memory。

---

## 12. Memory Retrieval

检索不采用单一向量 RAG。

```text
Authorization / Worldline / Time
        ↓
Eligible Memory Set
        ↓
┌──────────────┬──────────────┬──────────────┐
│ Structured   │ Graph        │ FTS / Vector │
└──────────────┴──────────────┴──────────────┘
        ↓
Rank Fusion
        ↓
Domain Re-rank
        ↓
Token Budget Pack
```

Domain 排序信号：

- semantic relevance
- graph distance
- recency
- emotional weight
- relationship relevance
- goal relevance
- identity weight
- source confidence

---

## 13. Context Compiler 边界

Memory & Knowledge Engine 返回授权后的 Domain 对象或检索候选。

Context Compiler 负责：

- 当前 Consumer 的可见范围；
- 去重；
- 证据绑定；
- token allocation；
- ContextPacket 编译。

AgentScope 仅处理已经授权的 ContextPacket。

---

## 14. 数据所有权

权威表位于 `world.db`：

```text
character_knowledge
character_beliefs
character_memories
memory_links
knowledge_changes
```

检索投影位于 `retrieval.db`：

```text
retrieval_documents
memory_fts
knowledge_fts
embedding_store
vector indexes
cross-domain graph projection
```

删除 `retrieval.db` 不得导致任何人物“失忆”。

---

## 15. Character Engine 协作

Character Engine 只消费授权后的 Knowledge / Belief / Memory 并输出 `ActionIntent`：

```text
Authorized Epistemic Context
        ↓
Character Reasoner
        ↓
ActionIntent
```

人物行动产生的实际 Observation、Knowledge、Belief、Memory 与 Relationship 变化只有在 Outcome 已确定后才能形成：

```text
ActionIntent
    ↓
Outcome Resolver / World Observation
    ↓
StateDelta / Observation
    ↓
Memory & Knowledge Engine
    ├─ Knowledge Candidate
    ├─ Belief Revision Candidate
    └─ Memory Candidate
```

Character Reasoner 不因为“认为某事应该发生”而直接写入长期 Knowledge 或 Memory。

---

## 16. Episode Finalization 协作

Story Engine 只管理 Story 内部发现状态，并输出 `EpisodeDraft` 与 Story-side evidence。

Finalization 由 Session Orchestrator 聚合各领域候选：

```text
Committed StoryState / StateDelta
        │
        ├─ Memory Distiller → MemoryCandidate
        ├─ Observation / Evidence → Knowledge / Belief Candidate
        ├─ Relationship Domain → Relationship Delta
        └─ World Engine → WorldEvent Candidate
```

各 Domain Engine 独立验证自身候选；全部通过后，在同一 `world.db` transaction 中完成 Episode 与长期状态原子写回。Committed Episode 只引用最终提交的 Domain Event / Memory / Knowledge Change IDs，不保存未决 Candidate。

---

## 17. Canon Character

当前人物状态：

```text
Canonical Knowledge Snapshot
        +
User-world Knowledge Changes
        +
Persistent Memory
        +
Beliefs
        =
Effective Character Epistemic State
```

未来 Canon 知识不得通过 Lore 检索提前注入。

---

## 18. API 基线

```text
KnowledgeService
  snapshot(character, worldline, world_time)
  acquire(candidate)
  revise(candidate)
  authorizedFacts(request)

MemoryService
  recall(request)
  proposeFromEpisode(episode)
  consolidate(candidates)
  supportingMemories(relationship_or_belief)
```

所有 mutation API 最终转为 Domain Command，由 Session Orchestrator 控制 transaction。

---

## 19. Hard Gates

禁止提交：

- 无来源的重大 Knowledge；
- Character 无合法获取路径却得到 Hidden Truth；
- Knowledge 来自未来 Canon；
- Memory 与实际 Episode/Event 矛盾；
- Memory Distiller 发明不存在的经历；
- Relationship change 无 evidence；
- Identity Memory 无足够长期影响；
- Vector/FTS result 绕过授权过滤。

---

## 20. MVP

Golden 001 支持：

- Knowledge certainty；
- Belief；
- Episode Memory；
- Relationship Memory；
- authorized recall；
- consolidation；
- exact/vector hybrid retrieval；
- Knowledge Leak test；
- app restart persistence。

高级遗忘模型、人格心理模拟和自主知识传播不进入 MVP。
