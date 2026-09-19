# 《诡秘世界》Gameplay Context & Cache Strategy v1.0

> 状态：PR #65 第二阶段实施基线。本文描述玩法到上下文/缓存的映射，不改变 Domain Truth、Commit 或公共 Schema。

## 1. 设计目标

缓存不是目标，**正确回合的端到端体验**才是目标。优化顺序固定为：

1. 不需要 LLM 的玩法不调用 LLM；
2. 需要 LLM 的玩法先做语义授权与一致性快照；
3. 只把任务所需的最小充分上下文送入模型；
4. 稳定前缀按真实复用寿命组织；
5. 只有预计会复用的前缀才请求显式 Provider 缓存；
6. 缓存丢失只能影响性能，不能影响世界记忆、知识或事实。

## 2. 玩法分类

### 2.1 No-model：最快的 cache 是不调用模型

以下体验默认直接消费权威 Projection / 已提交资产：

- 世界首页；
- 卡牌浏览；
- 人物存在档案；
- 地点页；
- 关系网络；
- Story Book 已提交内容与音频回放；
- 世界线结构化差异查看。

如果未来增加“帮我解释这个页面”的自然语言能力，应创建独立 `WORLD_OBSERVATION_QA` 调用，而不是让页面本身依赖模型。

### 2.2 Burst：短时间重复

`CHARACTER_GENESIS` 属于典型 burst：用户可能连续重抽/微调原创人物，但离开创建流程后通常不会继续复用。
稳定区主要是 Canon Pack、时代、序列原型、Narrative DNA；当前用户选择在尾部。

### 2.3 World：世界级低频

`WORLD_OBSERVATION_QA / WORLD_PULSE / TIME_SKIP` 以当前 Worldline 的世界检查点为共享根。
World Pulse 与 Time Skip 是显式低频操作，默认不为一次调用支付显式缓存写入成本，也禁止后台 keepalive。
世界首页问答若形成连续追问，可在短 TTL 内复用 Observation 前缀。

### 2.4 Session：Story Player 高价值热路径

`CHARACTER_REASONING / STORY_DIRECTION / NARRATIVE_COMPILATION / CLOSURE / HIGH_ORDER_INTERVENTION`
是最值得优化的路径。

```text
Worker contract
+ authorized content pack
+ Character Core / Narrative DNA
+ StorySeed / Hard Commitments
+ frozen checkpoint
+ committed append-only history
---------------- cache boundary ----------------
+ current effective state
+ turn recall / action intent / committed delta
+ current task
```

一次 Episode 约 4–10 个重大介入节点，而每个节点还会触发 Character、Director、Narrative 等阶段，因此同一 Session 前缀具有明显局部性。

## 3. 玩法策略矩阵

| 玩法 | Worker | Domain Facets | 缓存寿命 | 显式 Provider 策略 | 关键失效条件 |
|---|---|---|---|---|---|
| 世界首页 | none | projection | none | 不调用 | projection revision |
| 世界首页问答 | observation_narrator | Lore + World | world | hot-only | spoiler / world checkpoint / worldline |
| 原创人物生成 | character_genesis | Lore + World | burst | hot-only | era / sequence / content pack |
| Story Genesis | story_genesis | Lore + World + Character + Memory | episode | 默认避免 | Character stage / episode seed |
| Advice 解释 | advice_interpreter | World + Character + Story | scene | hot-only | scene / checkpoint |
| Character Reasoner | character_reasoner | Lore + World + Character + Story + Memory | session | 优先 | core / seed / checkpoint / policy / lineage |
| Story Director | story_director | Lore + World + Story | session | 优先 | seed / checkpoint / policy / lineage |
| Narrative Compiler | narrative_compiler | Lore + Character + Story | session | 优先 | Narrative DNA / voice persona / checkpoint |
| 收束命运 | story_director | World + Story | session | 优先 | checkpoint / closure transition |
| Memory Distillation | memory_distiller | Character + Story + Memory | episode | 默认避免 | committed episode |
| World Pulse | world_pulse_planner | Lore + World | world | 默认避免 | world checkpoint |
| Time Skip | world_pulse_planner | Lore + World | world | 默认避免 | world checkpoint |
| 高位存在介入 | story_director | Lore + World + Story | session | 优先 | Narrative DNA / seed / checkpoint |
| Story Book 回放 | none | committed assets | none | 不调用 | committed asset revision |

“优先”不表示无条件开启：Provider 必须被明确配置为支持该显式缓存模式；兼容接口不能按模型名字猜测。

## 4. 五个 Domain 模块的接线边界

新增 `GameplayContextCoordinator` 不访问数据库，而是绑定五类只读端口：

```text
LoreContextPort
WorldContextPort
CharacterContextPort
StoryContextPort
MemoryContextPort
```

每个端口在未来可直接适配已有 Domain/Application Service；当前某领域只有 Protocol 而没有读取实现时，端口就是稳定接线契约，不允许为了“先跑起来”由 AI 层直查 SQLite。

### 4.1 两阶段授权

必须遵守现有 Context Compiler 的顺序：硬授权先于检索。

```text
ContextSnapshotPort
  ↓ 一致性 revision / world time / lineage
GameplayAuthorizationPort.eligibility
  ↓ EligibilityTicket
Domain Facet Ports
  ↓ structured / graph / FTS / vector on eligible corpus only
Candidate Evidence
  ↓
GameplayAuthorizationPort.authorize
  ↓ exact Evidence fingerprint grants
Context Compiler
  ↓ final model boundary checks
```

`EligibilityTicket` 是内部能力句柄，不进入 Prompt。最终 grant 绑定完整 Evidence 内容、来源、层级和版本；复制 source id 或修改正文不能继承旧授权。

## 5. Context Snapshot 与并发读取

所有 Facet Port 必须基于同一个 `ContextSnapshot` 读取。Coordinator 可并发读取 Lore/World/Character/Story/Memory，以降低模型调用前的准备延迟，但不能跨 revision 拼接。

Snapshot 至少包含：

- world / story revision；
- world tick；
- policy revision；
- lineage digest / ancestor fork limit；
- gameplay cache dimensions。

Cache dimensions 是稳定版本轴，不应直接使用每回合增长的 world revision。示例：

```text
content_pack
character_core
story_seed
checkpoint
scene
narrative_dna
voice_persona
world_checkpoint
spoiler_profile
```

这使“世界 revision 又前进了一步”不会无理由摧毁 Character Core 前缀，而 checkpoint / scene / policy 真正变化时会自然旋转 Epoch。

## 6. Story Player 的三层缓存

### 6.1 L1：内容与角色稳定层

- Worker contract；
- Canon / Narrative DNA；
- Character Core；
- 能力定义与永久限制；
- Voice/Linguistic Persona（Narrative 阶段）。

更新频率最低。

### 6.2 L2：StorySession 冻结层

- StorySeed；
- Hard Commitments；
- 固定 checkpoint；
- 已提交 HISTORY 只追加。

不得因每轮新的 request id、trace、world revision 重写旧字节。

### 6.3 L3：Turn 动态尾部

- Current Effective Session State；
- Player Advice；
- 本轮 Recall；
- ActionIntent / committed StateDelta / BeatPlan；
- 当前任务。

当前状态正确性优先于缓存；模型不能靠 HISTORY 自己重放出权威状态。

## 7. 不同玩法为何不能共用一个超级前缀

- Character Reasoner 不能获得 Director 的 Hidden Truth；
- Narrative Compiler 不能获得未获披露批准的 Secret；
- 用户 World Observation 不能读取 World Truth Feed；
- 高位存在模式需要独立 Narrative DNA 与位格语法；
- Character Genesis 与已存在人物 Reasoning 的输出契约不同。

因此缓存拓扑是按 Worker/权限域分叉的树，而不是一个全局大 Prompt。跨玩法共享主要发生在本地内容工件与 Domain 读取层；Provider 前缀只在相同模型输入链路上复用。

## 8. 高位存在与 Narrative Scale

特殊存在卡的交互不是普通人物行动升级版。高位模式将稳定 `Narrative DNA + authority/limitation + symbolism + anchor/cause rules` 放在前部，当前干涉目标、可观察后果和本轮选择位于尾部。

该模式通常跨多个 Beat 使用同一位格规则，显式缓存价值高；但权限仍由 Story Director scope 控制，不能把高位背景共享给普通 Character Reasoner。

## 9. 费用与用户体验策略

### 9.1 禁止付费预热

默认 `network_prewarm=false`：

- App 打开不为了缓存发模型请求；
- 不运行 NPC 缓存保活；
- World Pulse 不作为 cache heartbeat；
- 缓存 TTL 到期只在下一次真实用户需求时自然重建。

允许本地预编译/指纹计算，因为它不产生模型费用和世界事实。

### 9.2 显式缓存只用于可复用热路径

`GameplayCachePlanner` 以玩法的 `expected_reuse` 和运行时 `anticipated_reuse` 决定是否保留显式缓存模式：

- one-shot / low-locality → 降级为 provider AUTO；
- hot-only 且预计只调用一次 → AUTO；
- session hot path → 保留已验证 explicit capability；
- 未声明能力的 OpenAI-compatible endpoint → 永远不自动升级。

AUTO 不等于“关闭厂商隐式缓存”，只表示应用不发送未验证/可能付费的显式写入参数。

## 10. Crash / Suspend / Barge-in

- PRE_COMMIT barge-in：取消当前调用，稳定 Session Epoch 可保留；未提交 Proposal 不进入 HISTORY。
- POST_COMMIT barge-in：停止 Narrative/Audio，但事实已提交；下一 Turn 追加 committed record。
- suspended StorySession：Epoch 可在进程内继续；进程重启后从 Domain checkpoint 重建，不能依赖缓存恢复故事。
- crash after COMMIT before Narrative：从 committed state 重新 Narrative，前缀仍由相同 checkpoint/history 重建。

## 11. 真实验收指标

不能只看 cache hit%。至少同时统计：

- user-visible TTFT / total stage latency；
- total input / cache read / cache write / uncached token；
- 每个成功 COMMIT Turn 的模型成本；
- Schema/Domain retry；
- freshness rejection；
- knowledge leak / spoiler leak（必须为 0）；
- Epoch rebuild 原因；
- no-model bypass 次数和节省的调用次数。

目标是“更快且正确”，而不是让大量无关固定文字制造漂亮的缓存比例。
