# Context Compiler v1.0

> **状态**：安全与上下文边界基线  
> **核心职责**：决定一个 Consumer 在当前世界、时间、世界线和知识状态下“有资格看到什么”，并将授权内容压缩为可追溯 ContextPacket。

## 1. 唯一出口原则

任何 AI Worker 不直接读取 `world.db`、`canon.db`、`retrieval.db`。

```text
Domain Repositories / Retrieval
       ↓
Context Compiler
       ↓
Authorized ContextPacket
       ↓
AgentScope
```

## 2. 编译顺序

顺序固定为：

```text
1. Resolve consumer / WorldlineLineage / revision / world_time
2. Resolve authorization policy
3. Apply worldline-lineage / knowledge / spoiler / visibility / time hard filters
4. Structured retrieval
5. Graph retrieval
6. FTS retrieval
7. Vector retrieval on eligible corpus
8. Candidate fusion
9. Domain re-ranking
10. De-duplication / evidence binding
11. Token-budget allocation
12. ContextPacket
```

**语义相似度永远不能先于知识授权。**

## 3. Consumer 权限

### Story Genesis
可读取：
- relevant Canon；
- World Truth；
- 当前时期人物/地点；
- unresolved world threads。

### Story Director
可读取：
- Story Hard Commitments；
- StoryState；
- authorized World Truth；
- ActionIntent；
- pressure / secret structures。

### Character Reasoner
仅可读取：
- Character Core；
- Character Knowledge / Belief；
- Relevant Memory；
- Current Observation / Scene；
- Available Capability；
- PlayerAdvice。

不得读取未授权 Hidden Truth。

### Narrative Compiler
可读取：
- committed StateDelta；
- BeatPlan；
- speaker intent；
- narrative disclosure policy。

Narrative 不能通过 Context 获取未批准披露的隐藏事实。

### UI Observation
只读取用户可观察的信息，不读取 Hidden Truth。

## 3.1 Active StorySession Overlay

当 ContextRequest 带有 `story_session_id` 时，Context Compiler 使用：

```text
Authoritative Global Snapshot
        +
Committed Session Overlay
        =
Effective Session Context
```

Overlay 只包含已经通过 Turn Commit 的事实。未提交的 Character Reasoning、Resolver Candidate 或 Narrative 不进入 Context。

StorySession Finalized 后，长期 Domain Projection 已吸收 Overlay，Context Compiler 不再重复叠加。

## 4. Retrieval

检索分为：

```text
Eligibility
   ↓
Structured / Graph / Lexical / Semantic
   ↓
Fusion
   ↓
Domain Re-rank
```

Memory 排序信号：

- semantic relevance
- graph distance
- recency
- emotional importance
- relationship importance
- identity importance
- current goal relevance
- source confidence

## 5. Rank Fusion

FTS BM25 与 vector similarity 不直接线性相加。

v1.0 使用 rank-based fusion（默认 RRF），再应用 Domain Boost。

## 6. Context Packet

```yaml
context_packet:
  packet_id: ctx_x
  role: character_reasoner
  world_id: world_001
  worldline_id: wl_main
  world_revision: 103
  story_revision: 8
  compiler_version: "1.0"
  sections:
    role_contract: ...
    canon_constraints: ...
    world_observations: ...
    character_core: ...
    character_knowledge: ...
    beliefs: ...
    memories: ...
    relationships: ...
    current_scene: ...
    user_input: ...
  evidence_ids: [...]
  exclusions:
    hidden_fact_count: 12
  token_budget: 8000
```

## 7. Token Budget

优先级：

1. Hard rules / contracts。
2. Current state。
3. Knowledge / capability constraints。
4. Relevant memory / relationships。
5. Local world context。
6. Historical prose / background。

超预算时压缩低优先级摘要，不删除硬约束。

## 8. Provenance

Context 内重要事实带：

- source kind；
- stable source id；
- source revision；
- confidence；
- visibility class。

模型输出的 reason summary 可引用 evidence ids，不保存私有 chain-of-thought。

## 9. Determinism

相同：

```text
request
+ domain revision
+ retrieval index revision
+ compiler version
```

应产生语义等价 ContextPacket。

检索投影落后当前 world revision 时，Context Compiler 合并权威 structured state，不等待 embedding 更新。

## 10. Security Gates

Hard fail：

- future Canon leakage；
- hidden world truth to Character；
- spoiler violation；
- stale worldline data；
- ancestor event beyond fork boundary；
- wrong character memory；
- invalid revision；
- cross-world contamination。

## 11. AgentScope 边界

AgentScope 可进行 model-window compaction，但不得：

- 增加未经授权的事实；
- 回查完整数据库；
- 将 runtime memory 提升为 Domain Knowledge；
- 改变 ContextPacket 的 permission scope。
