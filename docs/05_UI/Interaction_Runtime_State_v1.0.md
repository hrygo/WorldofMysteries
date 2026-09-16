# Interaction Runtime State v1.0

> **状态**：交互运行态基线  
> **适用页面**：World Home、Fate Intervention、Story Player  
> **核心原则**：UI 映射 Engine 已定义的运行状态，不创建第二套事实状态机。

---

## 1. 状态层次

UI 只消费 Application 层发布的 `InteractionState`：

```text
idle
listening
transcribing
interpreting
deciding
resolving
pre_commit
committed
directing
narrating
speaking
interrupted
recovering
closure
error
```

技术子状态可以存在于 Engine Trace，但普通界面不显示 ASR、LLM、TTS、SQL 等技术名词。

## 2. World Home

### idle
世界处于观察态：
- 场景继续存在；
- Ambient 保持；
- World Observation 可轻量变化；
- Listening Ring 不抢占注意力。

### listening
用户主动发问：
- Listening Ring 激活；
- 不弹聊天框；
- 世界场景保持。

### responding
世界以可公开 Observation 为依据回应，不访问 Hidden Truth。

World Home 的语音行为不自动创建 Story Turn。

## 3. Fate Intervention

Fate Intervention 表示用户已选中一个人物、事件或局势并准备介入。

页面显示：
- current situation；
- known facts；
- uncertainty；
- involved characters；
- pressure；
- possible impact；
- Listening Ring。

### listening → interpreting
用户给出 Advice。

### deciding
Character Reasoner 正在形成 ActionIntent。

体验：
- 人物/场景保持；
- Ambient 连续；
- 不使用 loading spinner；
- 不伪造人物 filler response。

### pre_commit
ActionIntent / StateDelta 已形成但尚未完成 Domain Commit。

此时：
- 用户可以取消；
- 取消后不产生事实变化。

### committed
StateDelta 已提交。

此时：
- 事实不可通过“打断播放”撤销；
- UI 进入 Story Director / Narrative 阶段。

## 4. Story Player

Story Player 常态 UI 最小化。

### narrating
NarrativeBlock 正在以字幕/旁白表现。

### speaking
Character Voice 正在播放。

### listening
命运节点进入聆听：
- 建议方向可轻量出现；
- 用户可忽略建议方向直接说 Advice；
- 不要求点击固定选项。

### interrupted
用户在 Narrative / Character Voice 中途开始说话。

#### PRE_COMMIT 内容
当前未提交 Turn 可以取消并替换。

#### POST_COMMIT 内容
停止当前 Narrative/Audio 表达；已提交事实保持。新 Advice 创建下一 Turn。

## 5. 离开 / 暂停 Story

当 StorySession 已有 committed Turn 时：

- 返回 World Home = suspend，不是 discard；
- 关闭 App = suspend；
- 再次进入 Story = resume 最近 durable revision；
- 开启另一篇 Story 前必须恢复或收束当前 Session。

只有尚无 committed Turn 的新 Session 可以直接取消。

## 6. Closure

用户主动表达收束意图时：

```text
closure requested
→ ClosurePlan
→ EpisodeDraft
→ Domain Finalization
→ Story Book
```

Closure 后：
- 不生成新的主要秘密；
- 不生成新的核心冲突；
- 不为了“高潮”强行加入新敌人；
- 允许未解问题保留。

## 7. Recovering

Engine crash / reconnect / Narrative recovery 时，UI 进入 `recovering`。

### 已 Commit
从最近 durable stage 继续表达。

### 未 Commit
回到上一稳定状态或重新进入 listening。

不得因为恢复而重新 roll 已提交 StateDelta。

## 8. Error

### Presentation-degradable
如 TTS / Ambient 失败：
- 保留文本；
- Story 可继续。

### Domain-blocking
如：
- revision conflict；
- database failure；
- unrecoverable schema mismatch。

行为：
- 暂停 mutation；
- 保留最后 durable world state；
- 提供恢复/诊断入口；
- 不伪造成功。

## 9. UI 与 Engine Event 映射

| Engine Event | Interaction State |
|---|---|
| input.opened | listening |
| asr.partial | transcribing |
| input.final | interpreting |
| character.started | deciding |
| resolver.ready | pre_commit |
| turn.committed | committed |
| director.started | directing |
| narrative.ready | narrating |
| audio.playing | speaking |
| playback.interrupted | interrupted |
| recovery.started | recovering |
| closure.requested | closure |

UI 不以这些 event 名作为用户文案。

## 10. Listening Ring

Listening Ring 是跨页面统一的世界交互符号。

状态语义：

```text
dim       = available but inactive
breathing = listening
contract  = input accepted
quiet     = deciding / resolving
open      = waiting for user
```

不使用强科技感麦克风作为主视觉。

## 11. 建议方向

建议方向是辅助理解，不是 Action 白名单。

要求：
- 0–3 个；
- 策略必须有差异；
- 不泄露角色未知信息；
- 不保证建议一定被角色照做；
- 用户始终可以自由 Advice。

## 12. 不变量

1. UI 不改变 Domain Truth。
2. PRE_COMMIT 可取消。
3. POST_COMMIT 不回滚。
4. Narrative/TTS retry 不重新 Resolver。
5. UI 不显示 Hidden Truth。
6. UI 不把建议方向当作唯一合法输入。
7. Engine recovery 不创造第二份 Story State。
