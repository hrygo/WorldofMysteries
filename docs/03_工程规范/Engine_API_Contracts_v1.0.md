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
