# Data Kernel Spike v1.0

> **状态**：P0 技术验证规格  
> **目标**：验证 SQLite-centered Truth Kernel 在事务、故障恢复、检索投影和 Golden 数据规模下成立。

## 1. 最小物理布局

```text
canon.db
world.db
retrieval.db
runtime.db
assets/
```

`world.db` 是唯一可变权威事实源。

## 2. Connection Profile

SQLite runtime baseline = `3.53.4`；Spike 使用与 Release Engine 相同的 SQLite build profile。

`world.db`：

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA synchronous=FULL;
PRAGMA trusted_schema=OFF;
```

核心业务表使用 `STRICT`。

写入：

```text
single Domain Writer
```

读取：

```text
small read pool
```

## 3. 最小 Schema

至少实现：

```text
worlds
worldlines
entities
domain_events
character_states
relationships
character_knowledge
character_beliefs
character_memories
story_sessions
story_turns
story_character_overlays
story_knowledge_overlays
story_belief_overlays
story_relationship_overlays
story_world_event_candidates
episodes
projection_outbox
idempotency_records
schema_migrations
```

## 4. Projection

`retrieval.db`：

```text
retrieval_documents
FTS5 indexes
exact embeddings
cross-domain graph projection
projection_checkpoint
```

不允许任何业务规则要求 `retrieval.db` 必须同步成功才能 Domain Commit。

## 5. StorySession Constraint

实现：

```sql
CREATE UNIQUE INDEX ux_story_sessions_open_worldline
ON story_sessions(worldline_id)
WHERE status IN ('active','suspended','closing','recovery_required');
```

测试：

- 同一 Worldline 第二个 open Session 创建失败；
- `finalized` Session 不阻止新 Story；
- 0 committed Turn 的 `cancelled` Session 不阻止新 Story；
- suspended Session 必须 resume 或 closure，不能被新 Story 静默覆盖。

## 6. Transaction Tests

### D001 Atomic Turn
Turn commit 中注入写入错误。

预期：
- StateDelta 不部分落盘；
- revision 不递增；
- outbox 不产生孤儿记录。

### D002 Atomic Finalization
在 Memory / Relationship / WorldEvent / Episode 任一点注入失败。

预期：
- 全部 rollback；
- StorySession 仍处于可重试 finalization 状态。

### D003 Idempotency
相同 idempotency key 执行两次。

预期：
- 只存在一次 Domain effect；
- 第二次返回已存在结果。

### D004 Revision Conflict
expected revision 落后。

预期：
- `revision_conflict`；
- 不盲写。

## 7. Crash Tests

### D005 Crash After Domain Commit
`world.db` commit 后，在 Outbox projection 前 kill process。

重启：
- Domain state 已存在；
- pending outbox 被处理；
- retrieval revision 最终追平。

### D006 Crash During Projection
FTS 更新后、vector 更新前 kill。

重启：
- 同一 outbox 可幂等重跑；
- 无重复 retrieval document。

### D007 Delete retrieval.db
删除整个检索库。

预期：
- World 可正常打开；
- structured UI 可使用；
- retrieval background rebuild；
- rebuild 完成后语义检索恢复。

## 8. Worldline Test

建立 Child Worldline：

```text
parent revision = R
fork
child current projection == parent effective current state at R
```

随后：

- Parent 继续产生 Event P-after；
- Child 产生 Event C-after；
- Child 修改 relationship / knowledge。

断言：

- Parent Current State 不受 Child 修改影响；
- Child Current State 不受 Parent 后续修改影响；
- Child Effective History 包含 Parent 在 fork boundary 之前的 Event/Episode/Memory；
- Child 不可读取 Parent 的 P-after；
- Parent 不可读取 Child 的 C-after；
- 历史 Episode / Memory 不因为 Fork 产生重复权威记录；
- Context Compiler 使用 WorldlineLineage 正确授权召回。


## 9. Retrieval Test Corpus

Synthetic：

```text
entities        10,000
domain relations 100,000
memories        20,000
retrieval docs  20,000
vectors         20,000
```

测试：

- entity lookup；
- 1-hop；
- 3-hop；
- FTS trigram；
- exact cosine top-k；
- hybrid RRF；
- authorization filter；
- rebuild。

## 10. Knowledge Isolation

构造：

```text
public memory semantic similarity = 0.72
hidden secret similarity = 0.99
```

Character 无 hidden secret authorization。

预期：
- hidden secret 永远不进入 eligible corpus；
- top-k 只来自合法集合。

## 11. Backup / Restore

验证：

- SQLite safe backup；
- restore 后 revision 一致；
- assets manifest 可解析；
- retrieval.db 缺失不影响恢复；
- backup 记录 schema version 与 Canon Pack version。

## 12. Migration

模拟：

```text
schema v1 → v2
```

中途注入 failure。

预期：
- 原 snapshot 可恢复；
- migration 不留下半结构状态；
- migration 完成后 integrity / FK checks 通过。

## 13. Metrics

记录：

```text
DB open
snapshot query
turn commit
episode finalization
1-hop
3-hop
FTS
vector
hybrid
outbox projection lag
rebuild duration
DB / WAL size
```

## 14. PASS

`GATE-DATA = PASS`：

- D001–D007 全部通过；
- partial finalization = 0；
- duplicate Domain effect = 0；
- knowledge authorization leak = 0；
- worldline contamination = 0；
- retrieval.db 可重建；
- backup / restore 可验证；
- 全部性能指标已有基线数据。
