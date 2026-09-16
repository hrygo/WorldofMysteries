# Schema Contracts v1.0

> **状态**：可执行结构化协议基线  
> JSON Schema Draft 2020-12。

## 1. Contract 列表

`schemas/` 包含：

- common.schema.json
- character.schema.json
- character_memory.schema.json
- character_knowledge.schema.json
- belief.schema.json
- relationship.schema.json
- world_snapshot.schema.json
- world_observation.schema.json
- world_event.schema.json
- story_seed.schema.json
- story_state.schema.json
- story_session.schema.json
- player_advice.schema.json
- action_intent.schema.json
- state_delta.schema.json
- beat_plan.schema.json
- closure_plan.schema.json
- narrative_block.schema.json
- performance_plan.schema.json
- audio_asset_ref.schema.json
- episode_draft.schema.json
- episode.schema.json
- turn_transaction.schema.json
- context_request.schema.json
- context_packet.schema.json

## 2. 原则

1. 持久对象带 `schema_version`。
2. IDs 为稳定 Domain ID，不使用自然语言名称作为主引用。
3. AI 输出必须先满足 Contract，再进入 Domain Validator。
4. Candidate 与 committed object 分离。
5. `StateDelta` 是一次已解析行动结果的事实变化描述。
6. `NarrativeBlock` 只能引用已提交 Story revision。
7. Schema 不表达所有业务规则；Canon/Knowledge/Capability 等由 Domain Validator 执行。
8. Contract 向后兼容由 explicit version / migration 管理。
9. `additionalProperties=false` 用于 AI 边界对象，避免静默协议漂移。
10. Golden Fixture 必须通过当前 schema validation。

## 3. Candidate / Committed

```text
WorldEventCandidate != WorldEvent
MemoryCandidate != CharacterMemory
KnowledgeCandidate != CharacterKnowledge
CharacterDelta != CharacterState
```

AI 产生 Candidate。Domain commit 后才获得事实身份和 revision。

## 4. Reasoning

Contract 允许简短 `reason_summary` / evidence ids，不保存模型私有 chain-of-thought。

## 5. Pydantic

Python Local Engine 以同一 Contract 生成/维护 Pydantic models。JSON Schema 是跨语言协议；Pydantic 是 Python runtime representation。

Swift IPC model 与同一协议版本同步。
