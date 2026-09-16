# 《诡秘世界》Character Engine v1.0

> **状态**：Domain Engine 规范基线  
> **核心输出**：`ActionIntent`，不是文学文本


## 1. 定位

Character Engine 回答：

1. 我是谁？
2. 我知道什么？
3. 我记得什么？
4. 我现在想要什么？
5. 面对这个局面，我为什么这样决定？

```text
World Engine
世界发生了什么？
      ↓
Character Engine
这个人怎么看？想怎么办？
      ↓
Story Engine
这次如何经历和讲述？
```

## 2. Character 是长期实体，不是 Prompt

```text
Character
├── Identity
├── Canon Profile
├── Personality
├── Values
├── Beliefs
├── Goals
├── Fears
├── Knowledge
├── Abilities
├── Memories
├── Relationships
├── Emotional State
├── Current Situation
├── Speech Style
└── Voice Persona
```

## 3. Core 与 State 分离

### Character Core

变化非常慢：身份、基础人格、价值底线、典型思考方式、语言风格、长期恐惧、核心欲望、Canon 过去。

### Character State

持续变化：当前情绪、伤势、灵性、位置、即时目标、怀疑对象、关系变化、新知识、当前冲突。

```text
Character = Core + Current State + History
```

## 4. 原著人物三层模型

```text
Canonical Character
        ↓
World Character
        ↓
Session Character State
```

- Canonical Character：原著确定，只读。
- World Character：用户世界新增经历、关系、知识与 worldview 变化。
- Session State：当前故事短期状态。

## 5. Observation 与 Knowledge

人物不能访问 World Truth，只能接收经过 Visibility / Position / Sense 规则形成的 `WorldObservation`。

```text
World Event / Fact
   ↓
Observation Engine
   ↓
WorldObservation
   ↓
Knowledge / Belief Candidate
   ↓
Memory & Knowledge Engine
   ↓
CharacterKnowledge / CharacterBelief
```

`CharacterKnowledge` 带来源和不确定性：

```yaml
character_knowledge:
  character_id: char_x
  proposition_id: fact_x
  certainty: 0.62
  source:
    type: observation
    ref: observation_x
    reliability: 0.8
  status: probable
  acquired_world_time: ...
```

`CharacterBelief` 独立表达人物可能相信但并未被世界真相确认的命题。Character Reasoner 使用人物自己的 Knowledge / Belief，不使用隐藏 Truth 自动纠偏。

## 6. Memory ≠ Knowledge

Knowledge 是事实；Memory 是经历及其情绪意义。

五类记忆：

```text
Canon Memory
Episode Memory
Emotional Memory
Relationship Memory
Identity Memory
```

Memory Consolidation：

```text
Raw Episode / Interaction
   ↓
Important Moments
   ↓
Memory Candidates
   ↓
Memory & Knowledge Engine
   ↓
Persistent Memory
```

同一 Episode 还可以独立产生 Belief Change、Relationship Delta 或 Identity Change Candidate；这些变化必须分别经过对应 Domain Validator，不由 Memory Summary 自动替代。

记忆按 overall / emotional / relationship / identity importance 评分。低价值记忆可降权、合并或标记 inactive；原始 Episode/Event provenance 保留。

## 7. Relationship

不是单一 trust 分数，而是有方向的多维关系：

```yaml
relationship:
  from_character_id: character.audrey
  to_character_id: character.fors
  dimensions:
    trust: 0.8
    affection: 0.5
    respect: 0.8
    fear: 0.0
    dependency: 0.1
    hostility: 0.0
  shared_secret_ids: []
  unresolved_conflict_ids: []
  debt_ids: []
  last_encounter_event_id: event.x
  evidence_ids: [...]
```

必须能通过 supporting memories 回答“为什么关系变成这样”。

## 8. Goals 与 Values

人物长期存在：Long-term / Medium / Immediate Goals。

Goals 不能全由 Story Director 临时发明；Character Engine 持有 Internal Goals。

Values 示例：

```text
Family
Truth
Safety
Faith
Freedom
Power
Loyalty
Compassion
Secrecy
```

决策综合：

```text
Goals
+
Values
+
Knowledge
+
Memory
+
Emotion
+
Risk
+
Relationships
+
Capabilities
```

## 9. Character Reasoning / Decision Pipeline

```text
WorldObservation
    ↓
Epistemic Update / Recall
(Memory & Knowledge Engine)
    ↓
Authorized Knowledge / Belief / Memory
    ↓
Goal Activation
    ↓
Emotion Update
    ↓
Generate Candidate Actions
    ↓
Capability Filter
    ↓
Personality / Value Evaluation
    ↓
Relationship Evaluation
    ↓
Risk Evaluation
    ↓
Choose Action Intent
```

Narrative Expression 最后发生。

## 10. 用户建议

```text
Player Advice
      ↓
Character Interpretation
      ↓
Character Reasoner
```

内部可标记：

```text
full
partial
reinterpret
reject
```

只有 Capability Conflict、Knowledge Conflict、Core Value Conflict、Extreme Risk、New Information 等情况允许明显偏离建议。

拒绝必须符合人物表达，不应像系统纠正用户。

## 11. Emotional State

不做 The Sims 式大量数值。可采用：

```yaml
emotion:
  primary: anxiety
  intensity: medium
  secondary:
    - curiosity
  cause: event.xxx
```

情绪只影响决策权重，不直接决定行为。

## 12. Character Arc 与 Drift Guard

变化速率：

```text
Core Personality  → 基本不动
Values            → 极慢
Beliefs           → 慢
Relationships     → 正常
Goals             → 正常
Emotion           → 快
```

人物长期变化必须有 Evidence。Character Drift Guard 检查：

- 是否突然违背核心人格
- 是否无理由改变道德底线
- 是否语言风格大幅漂移
- 是否忘记重大关系
- 是否无理由改变长期目标

原著人物尤其严格。

## 13. 原著人物证据库

Character Bible 不应只是一篇 prose 文档，而应结构化：

```text
Trait
Decision Pattern
Speech Pattern
Relationship Pattern
Canon Evidence
```

示例：

```yaml
trait:
  id: audrey.observant
  description: ...
  evidence:
    - canon_ref_x
    - canon_ref_y
  strength: strong
```

## 14. Speech 与 Voice 分离

### Linguistic Persona

- 礼貌程度
- 句子长度
- 用词
- 幽默
- 隐喻
- 停顿
- 情绪表达

### Voice Persona

由 Audio/SpeechRail 层使用：

```text
timbre
pace
breath
pitch
energy
emotional_range
```

## 15. Character Reasoner 输出

Character Reasoner 的正式输出只有 `ActionIntent`。`ActionIntent` 描述人物准备做什么，不描述行动已经成功，也不直接修改人物长期状态。

`ActionIntent` 包含：

```text
intent
actions
adherence
speech_intent
expected_costs
perceived_risks
reason_summary
evidence_ids
```

实际 Character State、Knowledge、Belief、Relationship 和 Memory 变化只有在 Outcome Resolver 确定结果后，由对应 Domain Engine 根据 `StateDelta / Observation / Evidence` 形成并验证。

Story/Narrative Layer 再依据已提交状态形成最终台词与叙述。

## 16. Capability Gate

所有行动检查：

- 当前序列
- 能力
- 灵性
- 伤势
- 道具
- 环境
- 知识

Ability 应结构化记录 availability / cost / limitations / knowledge_required / risk。

## 17. Character Genesis

序列卡生成原创人物：

```text
Sequence
+
Era
+
Location
+
Social Class
+
Occupation
+
Background
+
Conflict
+
Personality Seed
```

生成 Identity / History / Relationships / Goals / Secrets / Voice Persona，并经过 Canon Guard。

原创人物必须有合理的 Generated Backstory，但不得反向改写 Canon。

## 18. NPC Promotion 与 Card Revelation

```text
Minor NPC
   ↓
Recurring NPC
   ↓
Persistent Character
   ↓
Card
```

Card 与 Character 分离：Character 是世界中的人，Card 是用户对该人物的认知与收藏载体。

卡牌可逐步显影：

```text
??? / 模糊轮廓
→ 姓名
→ 身份
→ 途径
→ 关系
→ 经历
→ Biography
```

## 19. 持久化与 Memory / Knowledge 边界

Character Engine 的权威数据包括：

```text
characters
character_core
character_states
character_goals
character_abilities
character_voice
character_events
```

关系的当前语义由 Character/Relationship Domain 共同维护：

```text
relationships
```

以下数据由 Memory & Knowledge Engine 持有：

```text
character_knowledge
character_beliefs
character_memories
memory_links
```

所有数据仍位于同一 `world.db` 权威事务边界。Story 开始读取 Character Snapshot；Story Turn 由 Character Reasoner 产生 `ActionIntent`，Outcome Resolver 再形成 Character Delta Candidate；Episode Finalization 由相关 Domain Validator 审核后原子提交。

## 20. Context Compiler

Character Reasoner 每次只得到：

```text
Core Personality
+
Current Goal
+
Current Emotion
+
Relevant Knowledge
+
Relevant Memories
+
Relevant Relationships
+
Available Abilities
+
Player Advice
```

Memory Retrieval 综合：Relevance + Recency + Emotional Importance + Relationship Importance + Goal Relevance。

## 21. 架构

```text
World Observation / Current Scene
              │
              ▼
      Memory & Knowledge Engine
              │
      Authorized Epistemic Context
              │
              ▼
┌──────────────── Character Engine ────────────────┐
│                                                 │
│   Core Identity                                 │
│        │                                        │
│   Personality / Values                          │
│        │                                        │
│   Goals ───────┐                                │
│                ▼                                │
│   Memory → Reasoning ← Relationships            │
│                ▲                                │
│                │                                │
│         Emotional State                         │
│                │                                │
│         Capability Gate                         │
│                │                                │
│                ▼                                │
│          ActionIntent                           │
└─────────────────┬───────────────────────────────┘
                  ▼
            Outcome Resolver
```

## 22. 人物“活起来”的验收标准

1. 知道正确的东西。
2. 不知道不该知道的东西。
3. 记得真正重要的经历。
4. 关系连续。
5. 有自己的目标。
6. 决策符合人格。
7. 经历能够改变人物。
8. 语言和声音保持身份。

## 23. MVP

先支持：

```text
3–5 个原著人物
5–10 个原创人物
Knowledge
Memory
Goal
Relationship
Emotion
Decision
Voice Persona
```

MVP 不包含复杂心理模拟、大规模自主 NPC 或实时模拟所有人物生活。

最小 Character Loop：

```text
WorldObservation
      ↓
Memory & Knowledge Engine
      ↓
Authorized Knowledge / Belief / Memory
      +
PlayerAdvice
      ↓
Character Reasoner
      ↓
ActionIntent
      ↓
Outcome Resolver
      ↓
StateDelta / Observation
      ↓
Domain Validators
      ↓
Character / Relationship / Knowledge / Memory Commit
```

---

## 24. Memory / Knowledge 协作

Character Engine 不拥有长期记忆检索基础设施，也不把 Agent Runtime Memory 当作人物记忆。

决策上下文由 Memory & Knowledge Engine 提供：

```text
Character Core / Current State
       +
Authorized Knowledge
       +
Relevant Memories
       +
Relationships
       ↓
Character Reasoner
       ↓
ActionIntent
```

Character Reasoner 不产生长期 Knowledge、Belief、Memory 或 Relationship 变化。

这些变化由行动结果驱动：

```text
ActionIntent
  ↓
Outcome Resolver
  ↓
StateDelta / WorldObservation
  ↓
Memory & Knowledge / Relationship Domain
  ↓
Candidate
  ↓
Validator
  ↓
world.db Commit
```
