# Data Architecture v1.0

> **状态**：数据架构基线  
> **ADR**：ADR-002  
> **核心模式**：SQLite-centered Local Multi-model Persistence & Retrieval Architecture

## 1. 架构目标

数据层同时支持：

- 强事务关系数据；
- Event Store 与 revision；
- 世界线与叙事时间；
- Character Memory / Knowledge / Belief；
- 复杂关系与图检索；
- 全文检索；
- 向量语义检索；
- Story / Episode 长期保存；
- 音频和图片资产；
- crash recovery；
- schema / content-pack migration。

架构优先级：

```text
Truth correctness
→ recoverability
→ authorization
→ retrieval quality
→ performance
```

---

## 2. 物理布局

```text
Application Support/
└── MysteriousWorld/
    ├── Canon/
    │   └── canon.db
    │
    ├── Worlds/
    │   └── <world-id>/
    │       ├── world.db
    │       ├── retrieval.db
    │       ├── assets/
    │       │   ├── audio/
    │       │   └── images/
    │       ├── snapshots/
    │       └── exports/
    │
    └── Runtime/
        ├── runtime.db
        ├── engine.sock
        └── logs/
```

### canon.db
不可变 Canon Content Pack。Runtime 只读。

### world.db
用户世界唯一权威可变持久层。

### retrieval.db
可重建检索投影。删除后可从 `canon.db + world.db` 重建。

### runtime.db
AI trace、性能和诊断，不属于世界事实。

---

## 3. Truth Ownership

### 权威 Domain 数据

`world.db`：

- world / worldline；
- domain events；
- current state；
- character state；
- relationship；
- knowledge / belief；
- memory；
- location / organization / mystery；
- story session / turn；
- episode；
- revision / idempotency；
- projection outbox。

### 派生数据

`retrieval.db` / memory：

- FTS；
- embeddings；
- vector index；
- retrieval documents；
- cross-domain graph projection；
- ranking features；
- centrality / path cache。

**派生数据不能成为 Domain authorization 或事实判定来源。**

---

## 4. 图数据模型

### 4.1 Specialized Domain Relation Tables 是 Truth

具有明确领域语义的关系由各 Domain 表权威保存，例如：

```text
relationships
character_knowledge
character_beliefs
memory_links
organization_memberships
event_causality
story_secret_clues
canon_dependencies (canon.db)
```

这些表拥有：

- constraints；
- evidence；
- valid time；
- revision；
- Domain-specific properties。

### 4.2 Unified Cross-domain Graph 是 Projection

为了统一图遍历，将 Specialized Tables 投影为：

```text
Node
Typed Edge
```

例如：

```text
Character ─TRUSTS→ Character
Character ─KNOWS→ Fact
Character ─MEMBER_OF→ Organization
Memory ─ABOUT→ Character
Event ─CAUSED_BY→ Event
Secret ─REVEALED_BY→ Clue
```

该统一 Graph 存在于 `retrieval.db` 或内存，可删除重建。

统一 Graph 不维护任何与 Specialized Domain Table 并列的权威关系副本；所有 Edge 必须可从 Domain Table 和 Canon Table 重建。

Graph Projection 的每条边至少携带可过滤元数据：

```text
source_domain_ref
worldline_id
valid_from / valid_to
visibility_scope
knowledge_class
source_revision
```

Graph traversal 必须使用 Context Compiler 已计算的授权 scope；隐藏边不得先参与无约束遍历再在结果阶段过滤。

### 4.3 图查询三级

**Level 1：Domain JOIN**

1-hop、确定性业务查询直接 SQL。

**Level 2：Cross-domain traversal**

对 Unified Graph Projection 使用 Recursive CTE，主要覆盖 1–3 hop。

**Level 3：Graph algorithms**

提取相关子图到内存，执行：

- shortest path；
- reachability；
- centrality；
- community；
- influence analysis。

算法结果属于 Cache/Projection。

---

## 5. Event Store 与 Current Projection

世界长期状态采用：

```text
Domain Event Log
       +
Current Domain Projections
```

Event 保存“为什么变成这样”；Projection 保存“现在是什么”。

事件 Header 固定独立列：

```text
worldline
revision
world_time
aggregate
event_type
cause
episode
turn
```

稀疏差异放 payload。

不把可查询的关键字段全部塞 JSON。

---

## 6. 时间模型

至少同时存在：

- `world_time`：叙事世界时间；
- `revision`：事实提交顺序；
- `commit_time`：现实数据库提交时间；
- `worldline_id`：所属历史分支。

历史有效关系支持：

```text
valid_from_world_time
valid_to_world_time
created_revision
retired_revision
```

现实时间不能替代 world time。

---

## 7. Worldline

MVP 采用 **Materialized Current State + Lineage History**。

分叉：

```text
Parent current authoritative state
        ↓
Fork transaction
        ↓
materialize child mutable current projections
        ↓
record:
  parent_worldline_id
  fork_event_id
  fork_world_revision
  fork_world_time
```

分叉后的规则：

1. Character State、Relationship Current State、Knowledge/Belief Current Projection、Location/Organization Current State 等可变“当前状态”在 Child 中完整物化，父子随后独立演进。
2. 已发生的 Domain Event、Episode 和长期 Memory 不复制成第二份历史事实；它们保留原始 `origin_worldline_id` 与 revision/time provenance。
3. Child 的 Effective History 由自身历史 + 祖先 Worldline 在对应 fork boundary 之前的历史组成。
4. Context Compiler / Story Book / History Query 使用 `WorldlineLineage` 计算可见祖先片段，禁止把 Parent 在 fork 之后发生的事件泄漏给 Child。
5. Child 新产生的 Event / Episode / Memory 只属于 Child。
6. Retrieval Projection 可以为性能物化 lineage-aware candidate scope，但该 Projection 可删除重建，不成为历史事实源。

因此在线当前状态查询不需要逐层继承计算，而历史仍保持单一 provenance，不产生重复 Episode/Memory Truth。

本地个人世界的分支数量有限；只有在 lineage query 或 materialization 成为可测瓶颈后才引入更复杂的 Copy-on-write / branch index。

## 8. IDs

跨协议使用 stable string ID：

```text
character.audrey
world.char.<uuid>
episode.<uuid>
```

数据库内部可使用 `INTEGER PRIMARY KEY` 作为 join / rowid，并通过 Registry 映射 stable ID。

显示名称不作为主引用。

---

## 9. JSON 策略

采用：

# Hot Columns + Sparse JSON

独立列：
- 高频查询；
- FK；
- revision；
- worldline；
- time；
- authorization；
- status。

JSON：
- 稀疏 payload；
- provider-specific metadata；
-低频可扩展属性。

权威层 v1.0 优先 TEXT JSON，保持可诊断性。JSONB 只在 benchmark 证明收益后用于派生/热点结构。

---

## 10. SQLite 基线配置

Runtime SQLite 基线固定为 `3.53.4`；不依赖 macOS 系统 SQLite 版本。SQLite 与 Python runtime 一同纳入 Engine 构建与依赖清单。

`world.db`：

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = FULL;
PRAGMA trusted_schema = OFF;
```

核心表使用 `STRICT`。

Writer 模式：

```text
single Domain Writer connection/queue
+
small read pool
```

所有连接显式开启 foreign keys。

`synchronous=FULL` 是权威世界 durability 基线；调整必须经过 power/crash injection 验证。

---

## 11. StorySession 唯一活跃约束

MVP 同一 `worldline_id` 最多存在一个未终结 StorySession。

数据库使用 Partial Unique Index 形成最终防线：

```sql
CREATE UNIQUE INDEX ux_story_sessions_open_worldline
ON story_sessions(worldline_id)
WHERE status IN (
  'active',
  'suspended',
  'closing',
  'recovery_required'
);
```

Application 层在创建新 Story 前先执行恢复/Closure 检查；数据库索引防止竞态下出现第二个未终结 Session。

只有尚无 committed Turn 的 Session 才允许进入 `cancelled`；已有 committed Turn 的 Session 必须 suspend、resume、closure 或进入 recovery。

## 12. Domain Transaction

Story Turn：

```text
BEGIN IMMEDIATE
  verify expected revisions
  persist StateDelta / session state
  append events
  increment revisions
  append projection_outbox
COMMIT
```

Episode Finalization：

```text
BEGIN IMMEDIATE
  episode
  character state
  knowledge / belief
  memory
  relationship
  world events
  worldline metadata
  session closure
  outbox
COMMIT
```

失败全部 rollback。

---

## 13. Transactional Outbox

`retrieval.db` 不加入 Domain transaction。

```text
world.db commit
   ├─ domain mutations
   └─ projection_outbox
          ↓
Projection Worker
          ↓
retrieval.db
```

原因：多个 SQLite 数据库文件在 WAL 模式下不作为一个 crash-atomic unit。

Outbox 处理必须幂等。

`retrieval.db` 保存 `last_indexed_revision`。

当前 Turn 需要刚提交事实时，Context Compiler 直接合并 `world.db` 权威状态，不等待 embedding。

---

## 14. Full-text Search

### Entity / aliases

人名、地名、称号、短词：

```text
B-tree alias exact/prefix
```

### 中文自由文本

FTS5 `trigram` 作为 v1.0 baseline，覆盖 substring。

少于 3 Unicode 字符的查询由 Alias / structured search 处理。

### 英文/混合语料

可使用 `unicode61` 索引。

FTS 属于 `retrieval.db`，可完整重建。

---

## 15. Vector Architecture

定义：

```text
VectorIndexProvider
```

实现：

- ExactVectorProvider；
- SQLiteVec1Provider；
- Future provider。

### v1.0

**Exact first**。

少量向量直接 exact cosine / L2。

### Vec1

Vec1 是 Apple Silicon 本地 ANN 候选，但不成为 Domain dependency。启用 ANN 前必须测：

- recall@k；
- p50/p95；
- index build；
- memory；
- crash/rebuild。

向量索引始终可删除重建。

---

## 16. Retrieval Document

统一派生文档记录：

```text
document_id
source_kind
source_stable_id
worldline_id
character_id
visibility_scope
world_time
text
content_hash
source_revision
```

Embedding 使用：

```text
document_id
embedding_model_id
model_revision
dimension
content_hash
```

`content_hash` 未变不重新 embedding。

---

## 17. Hybrid Retrieval

固定顺序：

```text
Authorization / knowledge / spoiler / worldline / time
          ↓
Eligible corpus
          ↓
┌────────────┬────────────┬────────────┬────────────┐
│ Structured │ Graph      │ FTS        │ Vector     │
└────────────┴────────────┴────────────┴────────────┘
          ↓
Rank Fusion (RRF baseline)
          ↓
Domain Re-ranking
          ↓
Context Compiler
```

禁止先进行全库 vector search 再靠后置过滤补救权限。

---

## 18. Memory Retrieval

Memory 的权威内容在 `world.db`。

检索信号：

- entity relationship；
- shared episode；
- semantic relevance；
- lexical relevance；
- recency；
- emotional weight；
- relationship weight；
- identity weight；
- current goal relevance。

Vector 只是一个 signal。

---

## 19. Projection Worker

处理：

```text
Outbox
  ↓
read authoritative object
  ↓
build retrieval document
  ↓
update FTS
  ↓
update embedding if hash changed
  ↓
update vector projection
  ↓
update graph projection
  ↓
checkpoint revision
  ↓
mark processed
```

失败可无限安全重试。

---

## 20. Startup Recovery

```text
Open world.db
  ↓
schema version / migrations
  ↓
quick_check / required checks
  ↓
read world revision
  ↓
recover unfinished transactions/stages
  ↓
open retrieval.db
  ↓
resume pending outbox / rebuild if needed
  ↓
ready
```

检索投影恢复不阻塞基本 World UI 读取。

---

## 21. Assets

Audio、Image 不作为 BLOB 存入主数据库。

DB 只存：

- asset stable id；
- relative path；
- hash；
- mime/codec；
- size/duration；
- source revision；
- narrative block / character binding。

二进制存 `assets/`。

---

## 22. Backup

权威备份使用 SQLite Online Backup API 或等价安全 snapshot 机制，不对活跃数据库执行裸 `cp`。

关键备份包括：

- `world.db`；
- required asset manifest / assets；
- canon pack version；
- schema version。

`retrieval.db` 默认不属于关键备份。

快照时机：

- Episode Finalization；
- Major Divergence；
- migration 前；
- content pack switch 前；
- user manual backup。

---

## 23. Integrity

常规：

```text
PRAGMA quick_check
PRAGMA foreign_key_check
```

诊断：

```text
PRAGMA integrity_check
PRAGMA foreign_key_check
```

`integrity_check` 不替代 FK check。

---

## 24. Migration

### world.db

```text
backup
→ ordered migration
→ integrity checks
→ open world
```

### canon.db

安装新 Content Pack，不原地修改旧 Pack；通过 compatibility check 切换。

### retrieval.db

tokenizer、embedding、graph projection schema 大变化时优先 rebuild。

---

## 25. Security / Privacy

- Domain DB 默认本地；
- App 不直连 DB；
- model call 只发送 Context Compiler 授权最小上下文；
- raw user microphone 默认 ephemeral；
- DB 文件由 macOS user isolation / FileVault 提供系统级保护；
- 单应用透明加密成为明确需求时再引入 SQLCipher/加密容器；
- SQLite `trusted_schema=OFF`。

---

## 26. Diagnostics

持续暴露：

```text
world_revision
retrieval_revision
pending_outbox
db / wal size
entity count
relationship count
memory count
retrieval document count
embedding count
vector model revision
query p50 / p95 by channel
rebuild time
```

---

## 27. Data Golden Tests

### D001 Atomic Finalization
异常注入后 0 个 partial domain mutation。

### D002 Crash After Commit
Domain 已 commit、检索未投影；重启后 Outbox 完成。

### D003 Delete Retrieval DB
世界正常打开，检索库完整重建。

### D004 Vector Fallback
禁用 Vec1 后 exact provider 正常。

### D005 Knowledge Isolation
隐藏秘密即使语义最相似也不得进入 Character Context。

### D006 Worldline Fork
Child 初始状态等价；后续修改不污染 Parent。

### D007 Event / Projection Recovery
恢复后的 current state 与基线一致。

### D008 Migration Recovery
migration 失败仍可恢复原快照。

---

## 28. 升级触发器

以下条件触发新 ADR，而不是预先引入重型服务：

### Graph
跨域图查询已成为 p95 核心瓶颈，且大量实时查询需要 >3–5 hop 任意 pattern / 复杂算法。

### Vector
进入数十万到百万量级并且本地 provider 无法满足 recall/latency。

### Concurrency
需要多设备或多个 remote writer 并发修改同一世界。

### Cloud
产品进入长期 Remote Engine / multi-user server 模式。

届时 PostgreSQL/pgvector 和独立图投影服务重新评估。

---

## 29. 最终不变量

1. `world.db` 是用户世界唯一权威可变持久层。
2. Specialized Domain Tables 是领域关系 Truth。
3. Unified Graph 是 Projection。
4. Vector 是 Projection。
5. FTS 是 Projection。
6. `retrieval.db` 可删除重建。
7. Domain commit 不依赖检索服务成功。
8. Permission 先于 semantic retrieval。
9. Agent memory 不等于 Domain Memory。
10. 所有事实 mutation 经过 Domain Command + Validator + transaction。
