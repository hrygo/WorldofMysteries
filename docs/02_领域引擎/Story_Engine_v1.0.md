# 《诡秘世界》Story Engine v1.0

> **状态**：Domain Engine 规范基线  
> **前置依赖**：World、Character、Memory & Knowledge、Context Compiler  
> **原则**：Story Engine 运行一次值得被经历的命运，不拥有世界真相或人物人格。

## 1. 职责边界

Story Engine 回答：

> 在当前 World State 与 Character State 下，一段事件如何产生、发展、响应用户语音介入、形成后果，并最终沉淀为 Episode？

```text
World Engine      → 决定现实
Character Engine  → 决定人物理解与行动倾向
Story Engine      → 组织一次经历
Narrative Compiler→ 决定如何讲述
Audio Engine      → 决定如何被听见
```

Story Engine 可以：生成 StorySeed、维护 StorySession/StoryState、管理 Commitment/Clue/Secret、协调 Story Director 与 Advice Interpreter、请求 OutcomeResolver、规划 Closure，并输出 EpisodeDraft。NarrativeBlock 由独立 Narrative Compiler 基于已提交状态生成。

Story Engine 不可以：修改 Canon、越过 Character Engine 强迫人物、绕过 World Engine 永久写世界、为人物注入未知知识、用文学文本反向修改已提交状态。

## 2. 内部逻辑模块

```text
Story Genesis
    ↓
Opening BeatPlan
    ↓
Narrative / Audio
    ↓
User Input
    ↓
Advice Interpreter
    ↓
Character Reasoner
    ↓
ActionIntent
    ↓
Outcome Resolver ←──── Secret / Clue / StoryState
    ↓
StateDelta
    ↓
Validators
    ↓
COMMIT StoryState
    ↓
Story Director ←────── Secret / Clue / Pressure / Commitments
    ↓
Next BeatPlan
    ↓
Narrative Compiler
    ↓
Audio Engine
    └──────────────→ User Input
```

逻辑职责不等于独立模型。MVP 允许一个强模型承担多个角色，但每个阶段的数据契约必须分开。

## 3. Story Genesis

故事开始前先生成隐藏的 `StorySeed`，不能直接自由续写。

必须先确定：

```text
真正发生了什么？
  ↓
为什么发生？
  ↓
谁参与？
  ↓
谁知道？
  ↓
留下什么证据？
  ↓
哪些信息真实、哪些是误导？
```

### Truth First

核心真相在 Opening 前成立。中途只能揭露、误解、延迟，不允许为制造反转替换核心真相。

### Secret Graph

秘密采用小型因果图：

```text
Secret A
 ├─ 导致 → Effect 1
 └─ 留下 → Clue A
               ↓
            Location B
               ↓
            Secret B
```

避免无限“幕后还有幕后”。

## 4. Story State

`StoryState` 是本次 Episode 的当前现实，而不是从聊天历史猜测出来的状态。

至少包含：
- revision / turn / phase；
- scene / world_time；
- protagonist_goal；
- active_conflicts；
- discovered_clues；
- secret states；
- active_npcs；
- commitments；
- local_state；
- pressure；
- last_outcome / pending_input。

## 4.1 Session Overlay

`StoryState` 与人物/关系/认知的 Story 内变化共同构成 durable Session Overlay：

```text
Base World / Character Snapshot
            +
Committed Session Overlay
            =
Effective Session State
```

Turn `COMMIT` 只提交 Session Fact；它足以约束后续 Narrative 和下一 Turn，但不直接覆盖全局 Character/World Current Projection。

Overlay 包含：

- StoryState；
- Session Character State；
- Session Knowledge / Belief；
- Session Relationship State；
- Pending WorldEvent Candidates。

长期 Memory 不在每 Turn 生成；Memory Distillation 发生在 Episode Finalization。

## 5. Commitment Ledger

### Hard Commitment
已经成立，不能重写：真相、身份、死亡、物品位置、已获得知识、已执行动作等。

### Soft Commitment
导演层戏剧承诺：伏笔、潜在回收、NPC 再出现机会、秘密揭示机会等。

### Mutable State
危险、暴露、时间、线索、关系、伤势、灵性、位置等。

## 6. Story Director

Director 输出 `BeatPlan`，不直接写小说。

```json
{
  "schema_version": "1.0",
  "id": "beat_x",
  "story_session_id": "session_x",
  "source_story_revision": 12,
  "beat_type": "escalation",
  "dramatic_goal": "让主角意识到自己已被观察",
  "world_event_opportunities": [
    {
      "event_type": "outside_footsteps",
      "actor_ids": [],
      "target_ids": ["scene.current"],
      "purpose": "raise_pressure"
    }
  ],
  "reveal_ids": [],
  "npc_intents": [
    {
      "character_id": "npc_witness",
      "intent": "attempt_escape",
      "purpose": "protect_self"
    }
  ],
  "intervention_required": true,
  "tension_delta": "increase",
  "constraints": []
}
```

如果 Director 规划与 Character Engine 决策冲突，**Character Engine 优先**。Director 只能重新设计情境，不能操纵人物。

## 7. 语音优先的 PlayerAdvice

用户可自由语音表达，不受 A/B/C 限制。系统将语音解释为：
- primary intent；
- secondary intents；
- proposed actions；
- risk preference；
- confidence；
- original transcript。

建议方向可作为认知辅助，但不是输入边界。

## 8. Character Agency

```text
PlayerAdvice
   ↓
Character Interpretation
   ↓
ActionIntent
```

Advice 遵从类型：`full / partial / reinterpret / reject`。

拒绝或重解释仅应来自：能力冲突、知识不足、核心价值冲突、极端风险、新信息。

## 9. Outcome Resolver

Resolver 综合：

```text
ActionIntent
+ Capability
+ World Conditions
+ Opponent State
+ Resources
+ Risk
+ Uncertainty
```

结果等级：
- clean_success；
- success_with_cost；
- partial_success；
- complication；
- failure；
- catastrophic_failure。

最重要输出是 `StateDelta`，不是文学文本。

## 10. Turn Transaction

每轮严格按：

```text
1 User Voice/Input
2 ASR
3 Advice Interpreter
4 Character Reasoner
5 Outcome Resolver
6 StateDelta
7 Validators
8 Commit StoryState
9 Story Director plans next Beat
10 Narrative Compiler
11 Audio
12 Deliver
```

**状态先提交，Narrative / Audio 后生成。** Narrative 或 TTS 重试不得重新 roll 命运。

## 11. 分支策略

不构建指数剧情树，采用 `State Space Narrative`：

```text
Current StoryState
      ↓
Different ActionIntent / Outcome
      ↓
Different StateDelta
      ↓
Committed New StoryState
      ↓
Next Beat
```

宏观可采用 `Branch → Consequence → Gather`，差异保存在状态、关系、知识、世界事件与结局中。

## 12. Story Arc

目标 4–10 次重大介入，不机械凑轮数：

```text
Opening
→ Discovery
→ Investigation
→ Escalation
→ Midpoint Revelation
→ Crisis
→ Truth
→ Final Intervention
→ Resolution
```

内部可维护 Dramatic Clocks，但 UI 不显示 RPG 数值。

## 13. Clue / Secret

Clue、Knowledge、Secret 分开：

```text
黑色粉末 = Clue
发生过仪式 = Knowledge
死者主动参与 = Secret
```

Secret 状态：`hidden → suspected → partial → revealed`。

结局揭露必须具备 Foreshadowing Coverage，不允许最后临时创造此前不存在的幕后事实。

## 14. Closure Planner

用户可随时“收束命运”。Closure Mode：
- 禁止新增主要人物 / 秘密 / 核心矛盾；
- 处理当前冲突与必须回收承诺；
- 允许未知秘密保持未知；
- 允许失败、逃离、死亡、开放结局。

结局类型由最终状态推导，而不是由 Director 任意命名。

## 15. Narrative Compiler

输入：`BeatPlan + committed StateDelta + Character Speech Intent + Scene Context`。

输出 `NarrativeBlock`。NarrativeBlock 必须绑定 `source_story_revision`，以保证文学表达不反向修改事实。

## 16. Episode Finalization

Story Engine 将已经提交的 Story 历史收束为 `EpisodeDraft`：

```text
StorySession
   ↓
EpisodeDraft
   ├─ ending
   ├─ narrative_block_ids
   ├─ discovered_clue_ids
   ├─ secret_states
   ├─ unresolved_threads
   └─ story_evidence_ids
```

`EpisodeDraft` 不直接携带长期 Domain Mutation。Session Orchestrator 以其证据和已提交 StateDelta 为输入，分别请求各领域生成候选：

```text
EpisodeDraft / Story Evidence
        │
        ├─ Memory Distiller → MemoryCandidate
        ├─ Memory & Knowledge → Knowledge / Belief Candidate
        ├─ Relationship Domain → Relationship Delta
        ├─ Character Domain → Character State Delta
        └─ World Engine → WorldEvent Candidate
        ↓
Domain Validators
        ↓
Atomic world.db Finalization
        ↓
Committed Episode
```

Committed `Episode` 只引用最终提交的 CharacterEvent、RelationshipEvent、KnowledgeChange、Memory 和 WorldEvent IDs，不保存未决 Candidate。

## 17. Crash Recovery

Turn 阶段状态：
`received → interpreted → decided → resolved → validated → committed → beat_ready → narrative_ready → audio_ready → delivered`。

恢复规则：
- committed but not beat_ready → 从 Story Director 继续；
- beat_ready but not narrative_ready → 只重跑 Narrative；
- narrative_ready but no audio → 只重跑 Performance / TTS；
- resolved but not committed → 重跑 Validator 后提交；
- 同一 idempotency_key 不重复 Commit。

## 18. 核心对象

`StorySeed / StorySession / StoryState / BeatPlan / ClosurePlan / PlayerAdvice / ActionIntent / StateDelta / Commitment / Clue / Secret / NarrativeBlock / EpisodeDraft / Episode`。`StateDelta` 内含 Outcome Grade，因此不维护第二个可持久化 Outcome 对象。

---

## 19. StorySession 持久语义

StorySession 是 durable Domain state，不是一次模型会话。

```text
active ↔ suspended → closing → finalized
```

- 第一个 committed Turn 之前可以 `cancelled`。
- 第一个 committed Turn 之后，用户离开页面或关闭 App 只会 suspend，不会抹除已发生的 StoryState。
- 提前结束通过 ClosurePlan 收束为 Episode。
- 同一 Worldline 在 MVP 中只允许一个未终结 StorySession。
- `recovery_required` 保存最近 durable revision，恢复流程不得重新 roll 已提交 StateDelta。

## 20. AI Runtime 映射

Story Engine 的 Domain 对象与 AgentScope 执行方式固定为：

| Story 能力 | 执行方式 |
|---|---|
| Story Genesis | structured model call |
| Story Director | bounded AgentScope Agent |
| Advice Interpretation | structured model call |
| Character Reasoner | Character Engine structured call |
| Outcome Resolver | deterministic Domain code |
| Closure Planner | Story Director / structured call |
| Narrative Compiler | structured model call |

AgentScope 不持有 `StoryState` 的权威副本。`StoryState` 只在 Domain Runtime 中提交。

## 21. 长期写回

Episode Finalization 生成的所有长期变化在同一个 `world.db` transaction 中完成：

- Character State；
- Relationship；
- Knowledge / Belief；
- Character Memory；
- World Events；
- Episode；
- Projection Outbox。

`retrieval.db` 不参与该原子事务。
