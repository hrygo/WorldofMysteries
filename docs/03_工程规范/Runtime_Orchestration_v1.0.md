# Runtime Orchestration v1.0

> **状态**：事务与恢复基线  
> **控制平面**：Session Orchestrator。

## 1. 原则

一次 Story Turn 是可恢复事务流程，不是一次聊天补全。

```text
INPUT
  ↓
INTERPRET
  ↓
DECIDE
  ↓
RESOLVE
  ↓
VALIDATE
  ↓
COMMIT
  ↓
DIRECT
  ↓
NARRATE
  ↓
RENDER AUDIO
  ↓
DELIVER
```

`COMMIT` 之前决定事实；`COMMIT` 之后只决定表达。

## 2. Turn 状态机

```text
WAITING_INPUT
RECEIVED
INTERPRETED
DECIDED
RESOLVED
VALIDATED
COMMITTED
BEAT_READY
NARRATIVE_READY
AUDIO_READY
DELIVERED
```

错误状态：

- FAILED_RETRYABLE
- FAILED_FATAL
- CANCELLED
- RECONCILE_REQUIRED

## 3. TurnTransaction

至少记录：

```text
turn_id
session_id
idempotency_key
status
base_world_revision
base_character_revision
base_story_revision
player_advice_id
action_intent_id
state_delta_id
committed_story_revision
narrative_block_id
```

## 4. Single Domain Writer

`world.db` 使用单 Domain Writer Queue。

所有 mutation：

```text
Domain Command
  ↓
Writer Queue
  ↓
BEGIN IMMEDIATE
  ↓
validate expected revisions
  ↓
mutate state / append events
  ↓
append projection_outbox
  ↓
COMMIT
```

## 5. Story Turn Commit

Story Turn 的 `COMMIT` 是 **durable Session Fact Commit**，不是 Episode 的全局长期写回。

StorySession 维护持久化 Overlay：

```text
StoryState
Session Character State
Session Knowledge / Belief
Session Relationship State
Pending WorldEvent Candidates
Turn Transactions
```

每个 Turn 在一个 `world.db` transaction 中至少原子保存：

- committed StoryState；
- StateDelta；
- Session Character / Knowledge / Belief / Relationship Overlay；
- Pending WorldEvent Candidates；
- Turn status；
- story revision；
- 必要 Outbox metadata。

Narrative/TTS 不参与事实 transaction。

Story Player 后续 Turn 与 Context Compiler 均读取：

```text
Effective Session State
=
Global Domain State at session base revision
+
Committed Session Overlay
```

因此 App crash 或 Story suspend 不会丢失已经发生的命运；但全局 Character/World Current Projection 只在 Episode Finalization 时一次性晋升更新。

## 6. Episode Finalization

Episode Finalization 将已提交 Session Overlay 晋升为长期 Domain State。开始提交前重新校验 Session base revisions 与当前 Worldline；任何不可自动协调的冲突进入 `RECONCILE_REQUIRED`。

单一 `world.db` transaction 提交：

```text
Committed Episode
Character current state
Knowledge / Belief
Relationship
Character Memory
World Events
Worldline metadata
StorySession → finalized
Projection Outbox
```

成功后 Session Overlay 标记已消费，不再作为 Effective State 的额外层重复叠加。

任意一步失败：全部 rollback，Session 保持可重试的 `closing / recovery_required` 状态。

`retrieval.db` 不参与该原子事务。

## 7. Transactional Outbox

Domain commit 与 Outbox 同一 transaction。

Projection Worker：

```text
pending outbox
  ↓
load authoritative object
  ↓
update retrieval.db
  ↓
mark processed
```

投影操作必须幂等。

## 8. Revision

三类 revision 至少包括：

- world_revision
- character/domain aggregate revision
- story_revision

提交前使用 expected revision。冲突进入 `RECONCILE_REQUIRED`，禁止盲写。

## 9. Retry

| Failure | Retry | 不重跑 |
|---|---|---|
| ASR | ASR | Story state |
| Advice parse | Advice stage | Resolver |
| Character Reasoner | Character stage | earlier committed work |
| Resolver validation | candidate / rules | committed state |
| Director | Director | Outcome |
| Narrative | Narrative | Decision / Resolver |
| TTS | Audio | Narrative / State |
| Projection | Outbox | Domain Commit |

## 10. Crash Recovery

启动扫描非终态 Turn：

- `COMMITTED` 无 Narrative → 从 committed state 继续 Director/Narrative。
- `NARRATIVE_READY` 无 Audio → 只生成 Audio。
- `RESOLVED` 未 Commit → 重新 Validate + Commit。
- `INTERPRETED` → 可重新执行 Character Reasoner。
- Episode finalization transaction 未 Commit → world.db 保持旧状态。

## 11. Voice Barge-in

### PRE_COMMIT
用户打断可取消当前未提交 Turn。

### POST_COMMIT
停止 Narrative/Audio 播放，但不回滚事实。后续输入创建新 Turn。

## 12. StorySession 生命周期

MVP 每个 Worldline 最多存在一个未终结 StorySession：

```text
active
↔ suspended
→ closing
→ finalized
```

例外：

```text
active (0 committed turns)
→ cancelled
```

规则：

1. 只要已有至少一个 `COMMITTED` Turn，StorySession 不允许被静默删除或 `cancelled`。
2. 用户离开 Story Player 或退出 App 时，Session 进入 `suspended`，已提交 StoryState 持久化。
3. 用户再次进入时从最近 committed story revision 恢复。
4. 用户明确提前结束当前故事时执行 `request_closure`，基于最后 committed state 形成有效 Episode。
5. 不可恢复的异常进入 `recovery_required`，保留最近 durable state，不制造“空白重置”。
6. 新 Story 开始前，当前 Worldline 的 suspended/active Session 必须先恢复或 Closure；MVP 不并行运行多个 StorySession。

这保证 `COMMIT Story State` 具有持续语义，不会因用户关闭页面而被抹除。

## 13. World Lifecycle

MVP：

```text
App launch → Engine launch → handshake → DB open → recovery → ready
App exit → stop accepting new turns → finish/abort safe stage → checkpoint → Engine exit
```

App 关闭后世界时间不自动推进。

## 14. Background Tasks

允许：

- projection / embedding；
- audio render；
- snapshot / backup；
- memory consolidation；
- diagnostics。

不允许持续 MMO 式所有 NPC 自主运行。

## 15. Durability

权威 `world.db` 采用 WAL、FK、STRICT；durability profile 以 `synchronous=FULL` 为基线。性能优化必须通过故障注入测试后变更。
