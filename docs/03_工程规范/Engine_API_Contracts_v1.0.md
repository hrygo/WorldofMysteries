# Engine API Contracts v1.0

> **状态**：Domain / Application API 基线  
> Domain Protocol 与 AgentScope、SQLite、具体模型提供方解耦。

## 1. Session Orchestrator

负责：

- stage sequencing
- transaction
- revisions
- retry
- timeout
- cancellation
- idempotency
- recovery

不负责文学创作和人物人格判断。

## 2. World Engine

```text
snapshot(world_id, worldline_id, at_revision?)
observe(observer, scope) -> [WorldObservation]
validate(event_candidates, snapshot)
commit(command, expected_revision)
advance_time(command)
fork_worldline(command)
```

Story/Agent 只能提出 Event Candidate。

## 3. Character Engine

```text
snapshot(character_id, worldline_id)
decide(CharacterDecisionRequest) -> ActionIntent
validate(CharacterDelta)
capabilities(character_id, at_time)
```

Character Engine 不直接持久化长期 Memory/Knowledge。

## 4. Memory & Knowledge Engine

```text
knowledge_snapshot(character_id, worldline_id, at_time)
authorized_facts(request)
acquire(KnowledgeCandidate)
revise(BeliefOrKnowledgeCandidate)

recall(MemoryRecallRequest)
propose_from_episode(EpisodeDraft)
consolidate(MemoryCandidates)
supporting_memories(subject)
```

所有写入进入 Domain Command。

## 5. Story Engine

```text
create_seed(StoryGenesisRequest) -> StorySeed
open_session(StorySeed, StoryContext) -> StorySession
suspend_session(StorySessionID) -> StorySession
resume_session(StorySessionID) -> StorySession
plan_beat(BeatPlanningRequest) -> BeatPlan
request_closure(ClosureRequest) -> ClosurePlan
finalize(StorySession) -> EpisodeDraft
```

`plan_beat` 由 AgentScope Bounded Story Director 实现，但 Contract 属于 Domain Application 层。

## 6. Advice Interpreter

```text
interpret(final_transcript, story_state) -> PlayerAdvice
```

保存 original transcript。

## 7. Outcome Resolver

```text
resolve(
  ActionIntent,
  StoryState,
  SessionCharacterState,
  WorldSnapshot
) -> StateDelta
```

Resolver 是 Domain code；随机性如存在必须有显式 seed / policy，并可 replay。

## 8. Context Compiler

```text
compile(ContextRequest) -> ContextPacket
```

任何 AI Worker 不能绕过该接口读取完整数据库。

## 9. Narrative / Audio

```text
compile_narrative(NarrativeRequest) -> NarrativeBlock
plan_performance(NarrativeBlock, CharacterState) -> PerformancePlan
resolve_voice(VoicePersonaId, ProviderConfig) -> TargetPhysicalVoice
render_audio(PerformancePlan, TargetPhysicalVoice) -> AudioAssetRef
```

### 契约规则
1. **提交绑定**：`NarrativeBlock` 必须严格绑定已持久化的 `committed story revision`，严禁在 `COMMIT` 前生成。
2. **底层标准化**：语音渲染器统一基于 **OpenAI Audio API Specification**（`audio.speech`）标准协议对接，默认由 `SpeechRail` 本地服务支撑，且支持通过 `AudioProviderConfig` 热拔插至任何兼容第三方。
3. **内容寻址缓存**：`render_audio` 优先计算 $\text{AudioHash} = \text{SHA256}(\text{provider} + \text{":"} + \text{model} + \text{":"} + \text{voice} + \text{":"} + \text{speed} + \text{":"} + \text{UTF8}(\text{text}))$。若缓存已命中则跳过外部 API 请求直接返回已缓存的 `AudioAssetRef`。
4. **无感降级保障**：若语音提供商发生超时、限流或不可用，`render_audio` 优雅降级返回静音占位符，由 UI 自动退避至字幕纯文本呈现，绝对不中断剧情推进与状态持久化。

## 10. Repositories

Storage technology 被以下 Repository 隔离：

- WorldRepository
- CharacterRepository
- KnowledgeRepository
- MemoryRepository
- RelationshipRepository
- StoryRepository
- CanonRepository
- ProjectionOutboxRepository

检索独立：

- StructuredRetriever
- GraphRetriever
- LexicalRetriever
- VectorRetriever
- HybridRetrievalService

## 11. Local Engine Protocol

Swift App 只认识 Product/Domain API：

```text
handshake
open_world
world_home
get_character_view
start_story
submit_advice
stream_turn_events
request_closure
get_episode
get_asset
shutdown
```

IPC 不暴露 AgentScope `Msg`, `Agent`, `Pipeline` 类型。

### 11.1 可信首轮 Story Session Control Wire Mapping

现有 envelope 1.0、framing 与鉴权方式不变。Golden 001 工程验证入口在
`contracts/protocol/story_session_control.schema.json` 中冻结，使用独立 `$defs`，
不修改领域 Schema：

| 概念 API | Wire method | Payload schema |
|---|---|---|
| `world_home` / first story entry | `story.entry.get` | `entry_get_request` → `entry_get_response` |
| `start_story` | `story.session.open` | `session_open_request` → `session_open_response` |
| 只读恢复 | `story.session.get` | `session_get_request` → `session_get_response` |
| `submit_advice` | `story.advice.submit` | `advice_submit_request` → `advice_submit_response` |
| 结果查询 | `story.advice.get` | `advice_get_request` → `advice_get_response` |

固定范围：

- 仅接受 `scenario_id=golden_001`，仅支持服务端 entry 返回的原始首轮建议文本；
  固定工程模式 `golden_deterministic` 不替代 intake、领域裁决、Resolver、事务、
  Outbox 或恢复执行。
- `entry_get_request` 是只读入口；`session_open_request` 才创建且仅在
  服务端可信初始化成功后提交。
- 客户端不得发送数据库路径、worldline、protagonist、seed、初始状态、规则、
  hidden truth、初始 revision 或完整 `StorySession`。
- `public_story_session_view` 是独立 allowlist 投影，不是完整领域对象删字段后的结果。
  它禁止携带 `secret_states`、`hidden_truth`、压力、内部目标、未发现 clue、原始
  `StateDelta`、完整 world/character 或 seed digest。
- `story.advice.submit` 的 envelope `idempotency_key` 必须等于
  `input_turn_id`；`story.session.open` 必须等于 `open_request_id`。缺失或不一致
  按 `schema_invalid` 拒绝。`request_id` / `trace_id` 仅作为传输关联，不进入业务幂等摘要。
- `expected_story_revision` 与 `expected_store_revision` 是调用方在读取 view 后冻结的
  CAS 前提；前者比较 Story 进展，后者比较 SQLite store revision。两者不得互换。
  重试时业务幂等 ID、原始文本和预期 revision 必须保持首次值。
- `world/character` 基准 revision（Golden 001 为 103/27）是领域一致性前提，不是
  SQLite `world_meta.revision`，不得用于 store CAS。
- JSON Schema 负责字段、类型、上限、枚举、未知字段和 receipt 条件形状；session
  归属、scenario 绑定、receipt/session 身份一致性、幂等键相等性属于服务端与 DTO
  语义校验，必须 fail closed。

公共上限与版本：

- `schema_version="1.0"`；ID 非空、含至少一个非空白字符、无 NUL、最多 256 字符。
- revision 为 `0..2**63-1` 的 JSON 整数并拒绝 bool/字符串；写请求的
  `expected_*_revision` 小于 `2**63-1`。
- `raw_input` 非空、含至少一个非空白字符、无 NUL、最多 16,384 字符；
  服务端固定按 TEXT 处理，不支持本迭代的自由文本模型路径。
- `found=false` 时省略 receipt/session；`committed` receipt 必须同时包含
  `committed_store_revision` 与 `committed_story_revision`，其他状态禁止携带二者。

## 12. Error Taxonomy

标准错误至少包括：

- schema_invalid
- revision_conflict
- authorization_denied
- knowledge_violation
- canon_violation
- capability_violation
- continuity_violation
- model_timeout
- model_invalid_output
- projection_unavailable
- storage_failure
- recovery_required

## 13. Mutation Rule

所有 public mutation API 满足：

```text
typed command
+ idempotency key
+ expected revision
+ validator
+ atomic world.db transaction
```
