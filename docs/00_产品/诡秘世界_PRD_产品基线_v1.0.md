# 《诡秘世界》产品需求文档 PRD · v1.0

> **版本**：v1.0  
> **状态**：产品基线  
> **首发平台**：macOS 26+，Apple Silicon arm64  
> **产品形态**：单人持续世界 × 卡牌收藏 × 角色演绎 × 互动叙事 × 沉浸式声音故事  
> **产品边界**：单真实用户；个人世界；首发本地持久化；平台可扩展；同步为可选能力

---

## 0.1 系统设计绑定

本 PRD 的工程实现遵循以下架构不变量：

- macOS App 与 Local Engine Service 位于同一设备、分进程运行；
- AgentScope 负责 AI execution，不拥有 Domain Truth；
- `canon.db` 与 `world.db` 分离；
- `world.db` 是用户世界权威持久层；
- Context Compiler 在模型调用前执行 Knowledge / Visibility / Spoiler 授权；
- Narrative 与 Audio 位于 State Commit 之后；
- Domain Memory / Knowledge 不由 AgentScope Runtime Memory 代管。

详细工程约束以 `01_总体架构` 与 `03_工程规范` 中的 v1.0 文档为准。


## 0. 执行摘要

《诡秘世界》不是“AI 续写《诡秘之主》”，也不是“卡牌附带一个故事生成器”。它是一套以《诡秘之主》的世界观、历史、人物、途径与神秘学规则为 **Canon 底座** 的单人持续世界演绎应用。

用户通过已有卡牌进入这个世界：

- **原著人物卡**：进入一个已经具有完整历史、人格、关系与知识边界的人物视角；
- **序列卡**：以序列原型为约束，诞生一个新的原创人物，从原著未曾照到的角落探索世界；
- **特殊存在卡**：以符合位格的高层叙事语法影响世界，而不是沿用普通冒险模板。

一次互动故事不是孤立内容。人物经历、关系变化、知识增长、地点变化与重要世界事件都会沉淀为该用户个人世界的历史，影响未来从其他人物视角展开的故事。

产品最终希望建立的体验不是：

> “AI 给我生成了一篇好故事。”

而是：

> **“这是我的那个诡秘世界；它记得发生过什么，而其中的人也记得。”**

核心原则：

1. **世界先于故事。**
2. **角色先于剧情。**
3. **Canon 定义已经发生的历史，但不锁死尚未发生的未来。**
4. **玩家影响命运，但不把人物变成木偶。**
5. **每一个重要故事都必须留下记忆或世界痕迹。**
6. **故事结束，世界不结束。**

---

# 1. 产品背景与机会

## 1.1 当前产品基础

现有《诡秘之主》应用已经围绕卡牌建立内容资产，并持续扩展：

- 22 条成神途径、序列 9 至 0 的序列卡体系；
- 原著人物卡系列，并将持续丰富；
- 特殊存在、高位存在及其他世界要素卡牌；
- 卡牌强调设定准确、系列美学、身份与能力的可辨识度。

其中序列卡并不默认等同于某个具体原著人物，而是“序列原型”；现有设计语义包含身份、扮演、能力、魔药、晋升、限制等维度。这使卡牌天然可以从“收藏物”升级为“世界入口”。

## 1.2 产品机会

原著描绘的是一个庞大世界中少数人物、少数地点、少数时间段被照亮的部分。大量空间天然存在：

- 原著人物没有被书写的日常与事件；
- 原著事件之间的时间空隙；
- 已离开主叙事人物之后的人生；
- 贝克兰德、海上、教会、秘密组织等未被主线触及的人与事；
- 完全原创人物在同一世界规则下的生命轨迹；
- 从 Canon 某一点开始产生的另一条命运。

本产品的机会是：**把“未被讲述的空间”变成可持续演绎的世界。**

---

# 2. 产品定位

## 2.1 一句话定位

**《诡秘世界》是一款以《诡秘之主》世界观、原著人物、途径序列和历史设定为基础的单人持续世界演绎应用。用户通过卡牌进入不同人物的视角，与原著人物或原创人物共同经历原著未曾讲述的故事，每一次重要经历都会成为这个个人世界新的历史。**

## 2.2 产品不是

本产品不是：

- 原著剧情重演器；
- 单篇 AI 同人小说生成器；
- AI Chat 角色陪聊产品；
- 传统视觉小说；
- MMO / 多人在线世界；
- PvP / 卡牌对战游戏；
- 数值型开放世界 RPG；
- 数百 NPC 永久在线自主模拟器。

## 2.3 核心价值

### 对原著人物爱好者

体验“熟悉人物未曾被写下的人生”，并让这些经历长期成为该人物在个人世界中的历史。

### 对世界观爱好者

从原著主视角之外探索世界，看到普通人、基层非凡者、组织成员与城市角落中的另一面。

### 对卡牌收藏用户

卡牌从静态收藏品升级为世界访问入口和人物经历载体。

### 对声音故事用户

获得以人物稳定音色、环境声、旁白与关键音效构成的沉浸式互动有声故事。

---

# 3. 用户模型与平台策略

## 3.1 单真实用户

产品只有一个真实用户。

```text
Real User = 1
World Characters = N
```

世界内部可以拥有大量角色、NPC、组织和关系，但不存在多个真实用户共享同一 World State 的产品需求。

明确不做：

- 玩家联机；
- 用户之间交易；
- 公会；
- 排行榜；
- 世界频道；
- PvP；
- 多真实用户共同推动一条世界线。

## 3.2 首发平台

首发为 **macOS 应用**。

产品定义不绑定具体设备。未来允许扩展：

- Windows；
- iPad / 其他终端；
- 多设备访问；
- 可选的数据备份与同步。

即使未来支持同步，它仍然是一名真实用户的个人世界，而不是多人共享世界。

## 3.3 持久世界 ≠ 后台实时模拟

“持续存在”指世界状态在会话之间保持，而不是应用关闭后仍持续消耗资源模拟整个世界。

默认：

```text
应用运行 → 世界发生演绎
应用关闭 → 世界状态持久化并暂停
```

MVP 中应用关闭后世界暂停。任何离线时间推进都属于显式产品模式，不以现实时间自动驱动世界历史。

---

# 4. 产品核心模型

整个产品围绕三个一级对象构建：

## 4.1 World

这个世界已经发生什么、目前是什么状态。

## 4.2 Character

是谁在这个世界中经历事情，以及这个人如何理解世界。

## 4.3 Story

用户这一次通过某个角色视角，看见并参与了什么。

关系：

```text
World
  ├── Character
  │     └── Story / Episode
  ├── Character
  │     └── Story / Episode
  └── Character
        └── Story / Episode
```

**故事属于世界，而不是每次故事重新创造一个世界。**

---

# 5. 卡牌在产品中的角色

## 5.1 卡牌是“世界入口”

卡牌不仅用于收藏、设定阅读与美术欣赏，也承担进入不同叙事视角的功能。

```text
卡牌
  ├── 原著人物卡 → 进入已存在人物
  ├── 序列卡     → 创造受该序列约束的原创人物
  └── 特殊存在卡 → 进入高位叙事模式
```

## 5.2 原著人物卡

人物卡代表一个 Canon 中已经存在的具体人物。

进入故事时必须继承：

- 身份与社会位置；
- 外貌与阶段性形象；
- Canon 经历；
- 当前时间点的序列与能力；
- 当前时间点已经获得的知识；
- 人际关系；
- 价值观；
- 行为习惯；
- 语言风格；
- 重要记忆。

目标不是“一个像奥黛丽的人”，而是：**这个世界里的奥黛丽。**

## 5.3 序列卡

序列卡代表序列原型，而非固定人物。

选择序列卡后，Character Genesis 可以生成一名原创角色：

```text
序列卡
  ↓
时代 / 地域 / 社会身份
  ↓
原创 Character
  ↓
进入 World
```

其能力、限制、扮演原则和知识上限必须受序列 Canon 约束。

## 5.4 原创人物卡

原创人物可以来自：

- 序列卡生成；
- 产品预设角色；
- 故事中成长为重要人物的 NPC；
- 后续开放的用户角色创建。

原创人物的价值不是替代原著人物，而是 **深入原著没有照亮的世界**。

## 5.5 特殊存在卡

天使、真神、旧日、外神、源质等不能沿用普通人物的“走左边还是右边”式交互。

随着位格提升，叙事选择由“行动”逐渐升级为：

- 是否回应；
- 是否干涉；
- 通过何种象征或权柄施加影响；
- 是否让某件事情进入历史；
- 影响哪个锚、因果或群体。

---

# 6. Canon 与 Fate

## 6.1 Canon：已发生的历史

Canon 包括：

- 世界规则；
- 已确定历史；
- 某时间点的人物身份；
- 人物已经经历的重要事件；
- 当前阶段已经掌握的能力；
- 已建立的关系；
- 组织存在时间；
- 重要地点和事件状态。

Canon 的原则是：**不能为了让故事更刺激而随意修改。**

## 6.2 Fate：尚未发生的未来

```text
过去
━━━━━━━━━━━━━━━━━━●━━━━━━━━━━━━━━━━━━→
               Story Start

     Canon History          Open Fate
       已发生                 尚未发生
```

用户真正参与的是 Open Fate。

## 6.3 三种时间模式

### Canon Gap

发生于原著已知事件之间。

要求：

- 不破坏之后必须成立的重要 Canon；
- 人物知识、能力、关系对应准确时间点；
- 允许补充原著没有描写的小型事件与经历。

目标感受：**“这件事真的可能发生过。”**

### Open Future

从人物某个 Canon 时间点之后开始，未来完全开放。

适合：

- 原著已结束的人物未来；
- 离开主叙事人物的后续人生；
- 原创人物。

### Divergent Fate

如果故事中发生足以改变既有未来的重要事件，则明确创建新 Worldline。

```text
Canon Timeline ──────────────●────────────→
                              \
                               └──────────→ Divergent Worldline
```

从分叉后开始，不强制人物重新回到原著未来。

## 6.4 Canon Guard 的真正职责

Canon Guard 保护：

- 世界规则；
- 已经发生的历史；
- 能力边界；
- 知识边界；
- 时间一致性；
- 人物阶段一致性。

它不负责强制所有未来继续复制小说。

---

# 7. Persistent World：个人持续世界

## 7.1 World State

每个用户拥有一个持续存在的世界状态：

```text
World
├── Canon Baseline
├── Active Worldline
├── Worldlines
├── Characters
├── Relationships
├── Locations
├── Organizations
├── World Events
├── Active Mysteries
├── Episodes
├── Memories
└── User / Spoiler Progress
```

## 7.2 世界持续性

Story 完成后，其中具有长期意义的结果写回 World State。

示例：

- 一个据点被摧毁 → 后续故事中仍然是废墟；
- 一个原创 NPC 死亡 → 不能无理由正常出现；
- 一个角色知道了秘密 → 未来继续知道；
- 两个人建立信任 → 后续相遇时关系延续；
- 一桩案件没有解决 → 可以成为其他角色之后遇到的未解事件。

## 7.3 World Event 分级

### Personal Event
只影响当前人物，例如受伤、获得物件。

### Relationship Event
改变人物之间的信任、敌意、债务、共享秘密等。

### Local Event
改变某地点、组织或区域，例如据点被摧毁。

### Major World Event
可能影响多个未来故事或世界线的重要变化。

## 7.4 不做全量世界模拟

采用：

> **Persistent Important State + Generative Detail**

长期保存重要状态，大量普通居民、环境细节、一次性背景在进入具体场景时按规则生成。

---

# 8. Character Engine

## 8.1 Character 数据模型

```text
Character
├── Identity
├── Appearance
├── Personality
├── Values
├── Decision Pattern
├── Speech Pattern
│
├── Canon History
├── Generated History
│
├── Pathway
├── Sequence
├── Abilities
├── Limitations
│
├── Knowledge
├── Secrets
│
├── Relationships
├── Memories
│
├── Current State
├── Current Goals
└── Voice Persona
```

## 8.2 原著人物 Character Bible

原著人物不能只由“聪明、善良、谨慎”这类标签定义。

至少需要描述：

- 面对危险的判断方式；
- 对陌生人的态度；
- 对力量、秘密、组织的态度；
- 价值排序；
- 道德底线；
- 幽默与自嘲方式；
- 冲突处理方式；
- 长期愿望；
- 恐惧与内在矛盾；
- 压力下的人格变化；
- 典型措辞与语气；
- 明确的“不会这样做 / 不会这样说”的反例。

目标：**隐藏姓名后，仍能凭行为和声音认出这个人物。**

## 8.3 Character Agency

用户不是角色遥控器，而是“命运顾问”。

```text
角色遇到问题
  ↓
角色描述处境
  ↓
出现不同策略
  ↓
用户提供建议
  ↓
角色结合人格、知识与现实执行
  ↓
产生结果
```

原则：

```text
Player Advice ≠ Command
Advice = influence, not direct control
```

## 8.4 角色可以部分偏离建议

仅当：

1. 建议事实上无法执行；
2. 严重违反角色核心人格；
3. 人物没有必要知识；
4. 违反 Canon 能力或世界规则；
5. 执行前发现新的关键信息。

角色偏离必须有自然、可理解的原因，且不能高频发生。

## 8.5 Character Development

人物不是静态 Prompt。

```text
Core Personality  → 极慢变化
Worldview         → 可长期成长
Relationships     → 持续变化
Knowledge         → 持续增长
Emotional State   → 快速变化
```

人物可以成长，但不能因为模型随机性突然变成另一个人。

---

# 9. Knowledge Engine 与剧透系统

## 9.1 World Truth ≠ Character Knowledge

同一个世界事件，不同人物只能看到自己能够接触到的部分。

```text
                    WORLD TRUTH
                         │
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
       Character A   Character B    普通 NPC
        Knowledge     Knowledge      Knowledge
```

## 9.2 Fact、Knowledge 与 Belief

世界中的命题与人物的认知记录分离。

事实来源：

```text
CanonFact / WorldFact / WorldEvent-derived proposition
```

每个角色独立持有 `CharacterKnowledge`：

```text
character_id
proposition_id
certainty
source
acquired_world_time
status
revision
```

`known_by` 是查询结果，不作为某条 Fact 上的可变人物列表。

错误认知使用独立 `Belief` 对象，因此：

```text
World Truth
≠ CharacterKnowledge
≠ CharacterBelief
```

事实/知识可以具有分类：

```text
public
social
professional
organization
church
pathway
high_sequence
secret
forbidden
cosmic
personal
```

## 9.3 Knowledge Gate

Character Reasoner 不直接获得完整 Lore Kernel。

输入给角色的世界事实必须经过 Knowledge Gate，避免：

- 低序列人物知道高位秘密；
- 人物提前知道后来才发生的事件；
- 一个组织成员自动知道组织最高层真相；
- 角色拥有用户/模型的上帝视角。

## 9.4 Spoiler Profile

用户设置原著阅读进度，例如：

- 无剧透；
- 第一部 · 卷 X；
- 第一部完成；
- 续作进度 X；
- 完整设定。

图鉴、人物卡、卡牌详情、Story Genesis、NPC 和 World Event 均遵循统一 Spoiler Policy。

---

# 10. Story Engine 总体架构

逻辑架构：

```text
World / Lore / Memory & Knowledge
              │
              ▼
       Context Compiler
              │
       Authorized Context
              │
Player Advice ─┼──→ Character Reasoner
              │              │
              │              ▼
              │         ActionIntent
              │              ▼
              │       Outcome Resolver
              │              ▼
              │          StateDelta
              │              ▼
              │          Validators
              │              ▼
              │            COMMIT
              │              ▼
              │       Story Director
              │              ▼
              │          BeatPlan
              │              ▼
              └────→ Narrative Compiler
                             ▼
                    Audio / Voice Engine
                             ▼
                            User
```

这些是职责，不要求一项职责对应一个独立模型。

---

# 11. Story Genesis：先创建真相

## 11.1 Story Seed

故事正式开始前必须生成隐藏 Story Seed：

```text
主角 / 当前人物阶段
时间与地点
表层事件
真正发生的事情
核心冲突
关键 NPC
各自目标
隐藏真相
秘密
线索分布
时间压力
故事主题
潜在转折
可接受结局集合
Narrative Scale
```

## 11.2 Truth First

故事采用：

> **先存在真相，再让人物逐步发现。**

顺序：

```text
真正发生了什么？
  ↓
是谁造成的？为什么？
  ↓
留下了什么证据？
  ↓
谁知道？谁不知道？
  ↓
角色通过哪些路径可能发现？
```

禁止每一轮临时修改幕后真相来制造“反转”。

## 11.3 Narrative Commitment Ledger

### Hard Commitments

不能随意改变：

- 已确定死亡；
- 人物身份；
- 核心真相；
- 重要物件位置；
- 时间；
- 当前序列与能力；
- 已经获得的知识；
- Canon 事实。

### Soft Commitments

导演层计划：

- 待回收伏笔；
- 可能再次出现的 NPC；
- 冲突发展方向；
- 计划中的揭示窗口。

### Mutable State

允许介入结果改变：

- danger；
- exposure；
- spirituality；
- injury；
- corruption；
- trust；
- suspicion；
- clues；
- relationships；
- location；
- time。

---

# 12. Story State 与因果链

## 12.1 Story State

核心状态示例：

```text
story_id
turn
phase
scene
time
location
character_state
world_context
known_clues
secrets
npc_states
relationships
commitments
current_goal
danger
exposure
spirituality
injury
corruption
```

## 12.2 Outcome First

用户作出语音或界面建议后：

```text
Player Advice
     ↓
Character Reasoner
     ↓
ActionIntent
     ↓
Outcome Resolver
     ↓
StateDelta
     ↓
Validation
     ↓
COMMIT Story State
     ↓
Story Director / BeatPlan
     ↓
Narrative Generation
```

不采用：

```text
PlayerAdvice → LLM 自由续写 → 再猜发生了什么
```

数据库和结构化状态是事实，文学叙述是事实的演绎。

---

# 13. 互动叙事体验

## 13.1 Character-Grounded Narrative

叙事始终以人物真实处境和可知边界为中心。人物对白、行动、环境声与克制旁白共同构成场景；旁白不替人物获得上帝视角，也不抢占人物主体。

人物在需要外部判断的重大节点进入“世界正在聆听”状态，用户可以直接给出自然语言 Advice。

## 13.2 Intervention System

语音 Advice 是主要交互。系统可以在关键节点提供少量“建议方向”，帮助用户理解可行策略，但这些方向不是必须点击的菜单，也不限制用户自由表达。

示例方向：

| 建议方向 | 策略 | 主要代价 |
|---|---|---|
| 再验证一次异常 | 信息优先 | 灵性 / 时间 |
| 调查相关人的过去 | 稳健调查 | 时间成本 |
| 暂时隐藏并观察 | 风险观察 | 暴露风险 |

同时用户始终可以直接说出其他合理建议。

建议方向必须具有真实策略差异，不能只是同一行为的不同措辞。

## 13.3 Advice Intent

自然语言 Advice 先被解释为策略 Intent，再由 Character Reasoner 转换为人物在当前知识、人格、能力与风险下可执行的 `ActionIntent`：

```text
investigate
observe
confront
deceive
retreat
protect
cooperate
sacrifice
manipulate
conceal
risk
```

## 13.4 介入的真实意义

一个重要介入至少应改变以下一种或多种内容：

- 后续可获得信息；
- 时间；
- 关系；
- 风险；
- 身份暴露；
- 灵性 / 状态；
- NPC 行为；
- 是否进入某个场景；
- 最终结局条件；
- World Event。

---

# 14. 故事长度与戏剧结构

## 14.1 长度

单个 Episode 通常包含约 **4–10 个重大介入节点**，不按固定轮数机械推进。

Story Director 根据冲突、压力、秘密揭示程度与 Closure 条件自然决定长度。

## 14.2 标准节奏

```text
Opening
  ↓
Discovery
  ↓
Investigation
  ↓
Escalation
  ↓
Midpoint Revelation
  ↓
Crisis
  ↓
Truth / Partial Truth
  ↓
Final Intervention
  ↓
Resolution
```

介入节点由剧情需要触发，不按固定字数机械弹出。

## 14.3 收束命运

用户可在任何合适节点选择 **“收束命运”**。

Closure Mode 要求：

- 不再引入新的主要冲突；
- 不再引入新的核心人物；
- 处理当前主线；
- 回收必须回收的伏笔；
- 允许部分秘密保持未知；
- 在 1–2 个主要 Story Beat 内形成自然结局。

## 14.4 结局类型

允许：

- 真相结局；
- 胜利结局；
- 幸存结局；
- 代价结局；
- 失败结局；
- 逃离结局；
- 错误真相结局；
- 开放结局；
- 失控结局；
- 死亡结局。

所有选项最终都成功属于设计缺陷。

---

# 15. Secrets System

Story Seed 在开场前建立秘密集合：

```text
secret_01
secret_02
secret_03
...
```

秘密状态：

```text
hidden
partial
revealed
```

Episode 结束可以展示：

> **已揭开 4 / 7 个秘密**

未发现秘密不直接公开答案，为重玩、其他人物视角和未来 World Event 保留空间。

---

# 16. Narrative DNA：途径与位格决定叙事语法

## 16.1 途径 Narrative DNA

22 条途径不能只是换能力名称，需要各自拥有叙事倾向。

示例：

### 愚者相关途径
信息差、预兆、命运、身份、欺骗、仪式、线索。

### 观众相关途径
心理、观察、关系、人格、谎言、影响与操纵。

### 猎人相关途径
冲突、挑衅、陷阱、战争、群体与阴谋。

### 门相关途径
探索、旅行、空间、陌生区域、边界与未知。

Narrative DNA 至少描述：

```text
genre_weights
preferred_conflicts
pacing
motifs
intervention_axes
typical_costs
forbidden_cliches
```

## 16.2 Sequence Narrative Scale

### 序列 9–7：人的尺度
案件、生存、城市异常、小型神秘事件、身份与初步非凡风险。

### 序列 6–5：成熟非凡者尺度
教会、秘密组织、团队、复杂仪式、区域阴谋与主动博弈。

### 序列 4–3：半神尺度
城市级异常、大型仪式、规则与权能冲突、污染与大规模后果。

### 序列 2–1：天使尺度
历史、锚、命运、象征、高位存在、大范围现实影响。

### 序列 0：神灵叙事
用户不再主要决定“下一步走哪里”，而决定“是否回应、如何施加影响、允许哪种因果进入现实”。

高位叙事必须维护位格感，不能只是把低序列冒险换成更大的特效。

---

# 17. Memory System

人物长期连续性使用五类 Memory，并与 Knowledge / Belief 严格分离。

## 17.1 Canon Memory

原著明确发生且对该人物构成重要人生经历的 Canon 记忆。Canon Fact 仍由 Lore Engine 持有；Canon Memory 只描述人物经历与心理意义，不作为独立的世界事实源。

## 17.2 Episode Memory

该人物在用户个人世界中亲历的重要 Episode 及其长期意义。

## 17.3 Emotional Memory

具有持续情绪重量的经历，例如重大失去、救助、背叛、恐惧或宽慰。

## 17.4 Relationship Memory

记录“为什么关系变成现在这样”，并引用具体 Episode / Event evidence。`trust / fear / respect / affection / hostility / debt / shared_secret` 等当前关系值属于 Relationship State，而不是 Memory 本身。

## 17.5 Identity Memory

改变人物如何理解自身身份、价值、责任或能力边界的长期经历。其晋升门槛高于普通 Episode Memory。

## 17.6 Knowledge / Belief

人物知道的世界事实与人物记忆分开维护：

```text
World Truth
≠ Character Knowledge
≠ Character Belief
≠ Character Memory
```

World Truth 发生变化不代表人物自动知道；错误 Belief 也可以长期存在。

## 17.7 Memory Distillation

Episode Finalization 产生 Memory Candidate，而不是让模型直接写入长期记忆。Memory & Knowledge Engine 根据来源、重要性、关系、身份影响和保留策略完成审核与 Consolidation。

长期交互使用结构化 Knowledge / Belief / Memory 与授权检索，不把全部历史全文持续塞入模型上下文。

---

# 18. Audio Engine：声音是第一公民

## 18.1 Audio First

本模块不是“文字小说 + TTS”，而是互动有声故事。

基本体验：

```text
环境声
  ↓
人物对白 / 行动
  ↓
必要旁白 / NPC
  ↓
声音事件与情绪变化
  ↓
命运介入节点
  ↓
世界进入聆听状态
  ↓
用户自由给出 Advice
```

## 18.2 Voice Persona

重要人物拥有稳定声音身份：

```text
Timbre
Age Impression
Breath
Tempo
Rhythm
Emotional Range
Distance
Narration Style
Forbidden Traits
```

同一人物跨越不同故事仍应明显是同一个声音。

## 18.3 声音层次

### Character Voice
主要人物第一人称讲述与对白。

### Narrator
仅用于必要的时间、空间和镜头转换，不抢人物主体。

### Ambient
雨、海、街道、房间、教堂、工厂、地下空间等持续环境层。

### SFX
钟声、枪声、敲门、脚步、仪式、呼吸、低语等关键事件。

## 18.4 声音资产原则

V1 优先使用高质量可复用 Soundscape Library，而不是为每一个背景声音实时生成 AI 音频。

Narrative / Performance 层根据已提交场景输出结构化 Ambient / SFX Cue，Audio Engine 负责资产解析、渲染、混音和衔接。

---

# 19. 信息架构与核心界面

首版一级区域固定为：

```text
世界
人物
命运
故事书
卡牌收藏
世界线
笔记
设置
```

Story Player 是沉浸式运行态，不作为传统内容频道。

## 19.1 世界首页

目标：用户一打开就感觉自己“回到了同一个世界”。

展示：

- 当前世界时间 / 世界线；
- 最近发生的重要事件；
- 正在进行的命运；
- 最近活跃人物；
- 用户已感知但尚未解决的事件；
- 重要地点变化；
- 最近完成的故事。

不是内容平台首页，不出现“热门玩家故事 / 排行榜 / 社区动态”等社交元素。

## 19.2 卡牌详情

保留收藏、设定和视觉价值，并增加：

> **开启命运**

人物卡：进入该人物。  
序列卡：创建对应序列原创人物。  
特殊卡：进入对应 Narrative Scale。

## 19.3 命运介入

命运页承接卡牌、人物或世界事件，让用户靠近一个已经处于发展中的局势。

页面只展示用户当前有资格知道的内容：

```text
当前局势
已知事实
不确定性
相关人物
时间 / 风险压力
可能受影响的对象
```

Story Genesis 可以在后台形成 Story Seed，但隐藏真相、NPC 私有目标、Secret Graph 与 Hard Commitments 不直接展示。

语音是主入口。用户提供 Advice；界面提供少量方向提示，但不把交互限制为按钮选择。

## 19.4 Story Player

Story Player 以场景、人物声音和环境声为主体，常态下 UI 最大限度退场。

主要元素：

- 当前场景；
- 人物与必要视觉焦点；
- 克制字幕；
- Listening Ring；
- 文学化状态提示；
- 命运节点的少量建议方向；
- 收束命运。

用户可以直接自由说出 Advice，不要求从 2–3 个选项中选择。播放控制在需要时显现，不形成持续占据注意力的媒体播放器 UI。

避免复杂 RPG HUD、聊天窗口和人物档案式面板。

## 19.5 状态文学化

后台：

```text
spirituality = 21
exposure = 78
```

用户看到：

> “你的灵性已经接近枯竭。”  
> “有人开始怀疑你的真实身份。”

数值属于引擎，不属于主要叙事界面。

---

# 20. Story Book：把经历变成历史

一次 Episode 完成后生成一本真正的命运故事书。

包含：

- 封面；
- 标题；
- 主角；
- 时间与地点；
- 章节；
- 终章与结局；
- 命运介入路径；
- 已发现秘密；
- 关键人物；
- 重要关系变化；
- 对世界造成的影响。

## 20.1 阅读模式

完整故事以实际发生过的 Narrative Blocks 为主，允许加入必要过渡，但不能在结束后让模型重新改写一篇“差不多”的小说并改变事实。

## 20.2 聆听模式

重用 Story Session 已生成音频，补齐转场和终章，形成完整有声故事。

## 20.3 命运记录

例如：

```text
调查尸体
  ↓
隐藏身份
  ↓
相信陌生人
  ↓
拒绝仪式
  ↓
保护受害者
  ↓
开放结局
```

## 20.4 世界影响

只展示真正写入 World State 的重要结果，例如：

- 某 NPC 死亡；
- 某地点被摧毁；
- 某角色获得新秘密；
- 一个未解决事件被留在城市中。

---

# 21. 跨故事连续性

产品区别于普通故事生成器的核心是：**Episode 之间互相有历史。**

例如：

1. 奥黛丽在 Episode A 调查一次失踪事件；
2. 事件没有完全解决，成为 World Event；
3. 佛尔思在 Episode B 从报纸或关系网络中听到它；
4. 一个原创记者在 Episode C 到达事件地点；
5. 三篇故事共同丰富同一个世界，而非三次独立生成。

长期效果：

```text
Canonical Character
       +
User World Experiences
       =
My World Character
```

---

# 22. Worldline 与平行命运

发生重大分叉时创建新 Worldline，而不是静默覆盖历史。

```text
Worldline A ───────────●────────────→
                        \
                         └──────────→ Worldline B
```

未来能力：

- 查看分叉点；
- 从重要节点创建平行命运；
- 切换主要世界线；
- 比较不同介入路径造成的长期世界差异。

默认体验仍强调：**已经发生的事情应该具有重量。**

---

# 23. 核心数据对象

V1 正式对象包括：

```text
World
Worldline
WorldEvent
WorldObservation

Character
Relationship
CharacterKnowledge
Belief
CharacterMemory

Card
CanonFact

StorySeed
StorySession
StoryState
PlayerAdvice
ActionIntent
StateDelta
BeatPlan
ClosurePlan
Secret
NarrativeBlock
EpisodeDraft
Episode

PerformancePlan
AudioAssetRef

ContextRequest
ContextPacket
TurnTransaction
```

其中 Candidate 与 Committed Object 分离；AI 只产生 Proposal/Candidate，Domain Commit 后才形成长期事实。

## 23.1 核心数据链

```text
Card / Character / World Entry
          ↓
World + Lore + Character Context
          ↓
StorySeed / StorySession
          ↓
PlayerAdvice
          ↓
Character Reasoner
          ↓
ActionIntent
          ↓
Outcome Resolver
          ↓
StateDelta
          ↓
Validation
          ↓
COMMIT StoryState
          ↓
Story Director / BeatPlan
          ↓
NarrativeBlock
          ↓
PerformancePlan / AudioAssetRef
```

Closure 后：

```text
ClosurePlan
    ↓
EpisodeDraft
    ↓
Memory / Knowledge / Relationship / WorldEvent Candidates
    ↓
Domain Validators
    ↓
Atomic world.db Finalization
    ↓
Episode + Character/World Updates
    ↓
Transactional Outbox
    ↓
Story Book / Retrieval Projection
```

# 24. Runtime 状态机

Story Turn 的事实状态机固定为：

```text
WAITING_INPUT
      ↓
INPUT_RECEIVED
      ↓
ADVICE_READY
      ↓
CHARACTER_READY
      ↓
STATE_DELTA_READY
      ↓
VALIDATED
      ↓
COMMITTED
      ↓
BEAT_READY
      ↓
NARRATIVE_READY
      ↓
AUDIO_READY
      ↓
WAITING_INPUT
```

`COMMITTED` 是事实与表达的硬边界。

交互层将运行时映射为：

```text
listening
→ transcribing
→ interpreting
→ deciding
→ resolving
→ pre_commit
→ committed
→ directing
→ narrating / speaking
→ listening
```

结束流程：

```text
CLOSURE_REQUESTED
      ↓
CLOSURE_PLAN
      ↓
EPISODE_DRAFT
      ↓
MEMORY / KNOWLEDGE DISTILLATION CANDIDATES
      ↓
DOMAIN VALIDATION
      ↓
ATOMIC EPISODE FINALIZATION
      ↓
STORY_BOOK / AUDIO REPLAY / RETRIEVAL PROJECTION
```

应用退出不会删除已提交 StorySession。已有 committed Turn 的 StorySession 持久化并可恢复；用户主动提前结束故事时通过 Closure 完成 Episode Finalization，而不是丢弃已发生的事实。

# 25. 内容与系统分层

底层引擎与《诡秘之主》内容尽量解耦：

```text
World / Story / Character Engine
            ↑
      Canon Content Pack
```

《诡秘之主》的：

- Canon；
- 人物；
- 卡牌；
- 途径；
- Narrative DNA；
- 世界 Lore；

属于内容层。

这样既有利于内容治理，也避免未来产品平台与具体 IP 内容在代码层不可分离。

现有卡牌美术/设定生产体系继续保持独立职责，通过经过审核的 Content Pack 输出给应用使用，而不是把 Story Engine 直接塞进卡牌美术仓库。

---

# 26. 质量体系

质量优先级必须固定为：

```text
世界设定正确
  ↓
人物正确
  ↓
知识边界正确
  ↓
历史连续
  ↓
介入具有因果意义
  ↓
故事精彩
  ↓
语言优美
```

不能为了“更炸裂”牺牲 Canon、人物真实性、位格、时间线与知识边界。

## 26.1 Canon Accuracy

检查：

- 序列能力；
- 能力获得时间；
- 当前身份；
- 组织与时间；
- 世界规则；
- 重大历史；
- 高位知识。

目标：**重大 Canon Violation = 0**。

## 26.2 Character Fidelity

检查：

- 决策是否符合人物；
- 用词是否符合人物；
- 情绪变化是否有原因；
- 是否拥有不应知道的信息；
- 长期经历是否真正产生影响。

## 26.3 Continuity

检查：

- 谁已死亡；
- 谁知道什么；
- 物品位置；
- 时间与地点；
- 伤势与灵性；
- 关系；
- 伏笔；
- World Event。

目标：**Hard Commitment Conflict = 0**。

## 26.4 Intervention Meaningfulness

关键介入节点提供的建议方向必须具备策略差异；无论用户采用建议方向还是自由语音 Advice，实际执行结果都必须至少产生一项可验证的状态变化或明确的无变化原因。

## 26.5 Narrative Quality

评估：

- 悬念；
- 节奏；
- 伏笔；
- 决策压力；
- 因果；
- 结局完整度；
- 世界感；
- 文学表现。

## 26.6 Audio Identity

评估：

- 同一人物跨文本音色一致；
- 情绪演绎不破坏角色身份；
- 旁白 / 角色 / 环境层次清晰；
- 长篇播放无明显断裂和声音漂移。

---

# 27. MVP

MVP 不追求一次实现完整世界，而验证最核心闭环：

> **卡牌 / 人物 → 世界上下文 → Advice → ActionIntent → StateDelta → Episode → Memory / Knowledge → 世界更新。**

## 27.1 MVP 内容范围

- 3–5 名原著人物；
- 1 条途径的若干序列；
- 一批原创 NPC；
- 1 个重点城市；
- 若干必要组织；
- 最小 Lore Kernel；
- 少量高质量 Soundscape。

## 27.2 MVP P0

必须具备：

- World / Worldline / WorldEvent / Observation；
- Character Core / State / Relationship；
- Lore / Canon Fact / Canon Rule / Capability；
- Memory & Knowledge / Belief；
- Context Compiler 与 Knowledge / Visibility / Spoiler Gate；
- StorySeed / StorySession / StoryState / Commitment / Secret / Clue；
- PlayerAdvice / ActionIntent；
- deterministic Outcome Resolver / StateDelta；
- Canon / Capability / Knowledge / Continuity Validators；
- BeatPlan / ClosurePlan / EpisodeDraft / Episode；
- NarrativeBlock；
- Voice Persona / PerformancePlan / 基础 Audio Engine；
- Story Book；
- `world.db` 权威事务与 `retrieval.db` 可重建投影；
- AgentScope AI Runtime 边界；
- Golden 001 回归夹具。

## 27.3 MVP 非目标

- 多真实用户；
- 社交；
- 联机；
- 玩家交易；
- PvP；
- 完整 RPG 战斗；
- 装备与经济系统；
- 开放地图自由移动；
- 数百 AI NPC 实时自主运行；
- 完整世界沙盒；
- 大规模多角色同时演绎。

---

# 28. 实施基线

工程实施以 `06_实施基线/Executable_Baseline_v1.0.md` 与 `07_工程启动/` 为准。

## 28.1 Engineering GO

大规模并行开发前必须通过：

```text
GATE-PACKAGE
GATE-PROTOCOL
GATE-DATA
GATE-AI
GATE-GOLDEN-MOCK
```

这五项验证 Local Engine 分发、Swift/Python Contract、SQLite Truth Kernel、AgentScope 执行边界以及 Golden 001 的确定性纵向链路。

## 28.2 第一条可执行纵向切片

首个工程闭环同时包含：

```text
World / Character / Memory & Knowledge
        ↓
Story Session
        ↓
Voice / Text Advice
        ↓
Character Reasoner
        ↓
Outcome Resolver
        ↓
Commit
        ↓
Narrative / Audio
        ↓
Episode Finalization
        ↓
App Restart Persistence
```

因此不存在“先做一次性文本故事、再补持久世界”的中间产品架构。

## 28.3 内容扩展

Engine Architecture v1.0 通过 Golden 001 后，内容按 Vertical Lore Slice 扩展：

- 原著人物 Canon Snapshot；
- 更多途径与序列；
- 更多组织、城市、时代；
- 多人物连续性；
- Major Divergence / Worldline；
- NPC Promotion；
- 高序列与特殊存在独立叙事语法；
- 更完整的声音世界。

每一批扩展都使用相同 Domain Contract、Knowledge Gate、Golden/Eval 机制，不绕过底层架构。

---

# 29. 产品成功标准

产品真正成功不是“单次生成质量很高”，而是长期使用以后用户产生以下明确感受：

> **“这个世界记得以前发生过什么。”**

> **“这个人物真的认识以前遇见过的人。”**

> **“这是奥黛丽，但这是我这个世界里的奥黛丽。”**

> **“上一段故事发生的事情，这一次仍然存在。”**

> **“即使没有故事正在播放，我仍然感觉这个世界存在。”**

---

# 30. 核心产品循环

```text
认识世界
  ↓
收藏卡牌
  ↓
进入人物 / 创造人物
  ↓
开启命运
  ↓
聆听故事
  ↓
参与抉择
  ↓
承担后果
  ↓
形成历史
  ↓
改变人物
  ↓
改变世界
  ↓
再次从另一个视角进入
```

---

# 31. 不可动摇的产品原则

1. **世界先于故事。**
2. **角色先于剧情。**
3. **Canon 定义过去，但不锁死未来。**
4. **原著人物必须保持人物真实性。**
5. **原创人物负责扩展原著没有描写的世界。**
6. **每个人物只能知道自己应该知道的事情。**
7. **用户影响人物，而不是操纵人物。**
8. **每一次重要介入都必须产生真实状态变化或明确的无变化原因。**
9. **每一个重要故事都必须留下记忆或世界痕迹。**
10. **故事结束，世界不结束。**

---

# 32. 最终产品叙事

这里不是重新讲一遍《诡秘之主》。

原著告诉了我们一些人的故事，但那个世界远远没有因此停止存在。

在贝克兰德某一扇从未被小说推开的门后，在大海某一段没有被记录的航程中，在某个教会的地下档案室，在某个普通人的梦里，都可能发生着新的故事。

那些我们熟悉的人，也拥有原著没有记录的日子。

用户可以进入原著人物的视角，见证他们新的经历；也可以让一个此前从未存在的人第一次在这个世界醒来。

他们拥有自己的性格、记忆、知识、秘密和关系。

他们会听取用户的意见，但他们仍然是他们自己。

他们可能成功，可能犯错，可能失去某个人，也可能发现不该发现的秘密。

而当故事结束以后，这些事情不会被清空。

人物会记住。关系会改变。地点可能已经不同。某个秘密会继续存在。

下一次，从另一个人的视角再次进入这个世界时，用户会发现：

> **以前发生过的事情，真的已经成为历史。**

因此《诡秘世界》真正创造的不是无限数量的 AI 故事。

# 而是一个能够不断产生故事、记住故事，并因为这些故事而改变的诡秘世界。

---

## 附录 A：结构化工程契约

当前产品基线对应的可执行 Contract 为：

1. `action_intent.schema.json`
2. `audio_asset_ref.schema.json`
3. `beat_plan.schema.json`
4. `belief.schema.json`
5. `character.schema.json`
6. `character_knowledge.schema.json`
7. `character_memory.schema.json`
8. `closure_plan.schema.json`
9. `common.schema.json`
10. `context_packet.schema.json`
11. `context_request.schema.json`
12. `episode.schema.json`
13. `episode_draft.schema.json`
14. `narrative_block.schema.json`
15. `performance_plan.schema.json`
16. `player_advice.schema.json`
17. `relationship.schema.json`
18. `state_delta.schema.json`
19. `story_seed.schema.json`
20. `story_session.schema.json`
21. `story_state.schema.json`
22. `turn_transaction.schema.json`
23. `world_event.schema.json`
24. `world_observation.schema.json`
25. `world_snapshot.schema.json`

Contract 以 `03_工程规范/schemas/` 中的 v1.0 JSON Schema 为准。

## 附录 B：规范分册

产品实现受以下规范分册共同约束：

- World Engine v1.0
- Character Engine v1.0
- Memory & Knowledge Engine v1.0
- Story Engine v1.0
- Lore / Canon Engine v1.0
- Audio / Voice Engine v1.0
- Context Compiler v1.0
- AgentScope Integration v1.0
- Data Architecture v1.0
- Runtime Orchestration v1.0
- Engine API Contracts v1.0
- Engine Quality Gates v1.0
- UI / Interaction Baseline v1.0
- Interaction Runtime State v1.0
- Canon Content Accuracy Baseline v1.0
