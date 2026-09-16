# 《诡秘世界》Audio / Voice Engine v1.0

> **状态**：Domain/Media Engine 规范基线  
> **原则**：声音表达事实，不决定事实。

> **核心定位**：世界的听觉运行时，而不是单纯 TTS 模块。

## 1. 端到端职责与进程所有权

Audio / Voice 是跨 App 与 Local Engine 的子系统，职责分层如下：

```text
SwiftUI / Media Runtime
├─ Microphone Capture
├─ VAD / Input Endpoint
├─ ASR Adapter
└─ Audio Playback / Device

Local Engine
├─ Voice Turn Coordinator
├─ Performance Planner
├─ Audio Renderer / Asset Manager
└─ AudioScene / AudioTimeline semantics
```

MVP 中只有 `FinalTranscript` 进入 Story Turn。ASR partial 只服务 UI，不触发 Domain Action。

Voice Turn Coordinator 负责 listening / interruption / Commit Boundary 的语义；Performance Planner 负责“怎么说”；Renderer 生成可缓存 AudioAsset；SwiftUI Media Runtime 负责实际麦克风与扬声器设备、字幕播放同步和 barge-in 采集。

ASR/TTS 均通过 Adapter 抽象。MVP 的 ASR 物理执行位于 App Media Runtime；未来迁移为本地 media helper 时不改变 `FinalTranscript → PlayerAdvice` Domain Contract。

## 2. 事实边界

```text
Committed Story State
  ↓
NarrativeBlock
  ↓
PerformancePlan
  ↓
AudioAsset
```

Audio 重试、音色替换、语速调整不得改变 Narrative 或 Story State。

## 3. Voice Runtime 状态机

UI 交互状态与 Story Runtime 对齐：

```text
idle
→ listening
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

并支持：`interrupted / recovering / closure / error`。

`cancelled` 只用于尚无 committed fact 的 pending Turn/Session，不表示已提交故事被删除。

## 4. 三种主要交互模式

- Observe Mode：世界首页，低干预问答；
- Fate Mode：用户给人物 Advice；
- Story Mode：语音成为主要故事交互。

Character Conversation Mode 不属于 MVP；该模式沿用相同的 Character / Memory / Knowledge 边界。

## 5. Barge-in 与 Commit Boundary

- PRE_COMMIT：允许用户取消 pending turn；
- POST_COMMIT：可停止叙事播放，但已经提交的事实不可撤销。

这是 Voice Runtime 与 Story Transaction 的关键边界。

## 6. Voice Persona 与 Performance

长期 `VoicePersona` 与单句 `PerformancePlan` 分开：

```text
Voice Output = Voice Persona + Performance Plan + Text
```

Performance 至少处理 emotion、intensity、speech intent、pace、energy、volume、pause、emphasis。

## 7. Audio Scene

环境声由场景状态驱动，而非每句由 LLM 自由描述。Ambience 与 SFX 使用结构化资产 ID；音乐只在重大节点克制使用，Silence 也是正式音频元素。

## 8. AudioTimeline

`NarrativeBlock → PerformancePlan → AudioAssetRef` 后形成播放 `AudioTimeline`。AudioTimeline 同步语音、环境声、SFX、字幕与 UI 状态，但不属于 Domain Truth；它可以从 NarrativeBlock、PerformancePlan 和资产元数据重新构建。

## 9. Provider Adapter

ASR/TTS 通过 Provider Protocol 接入。Story Engine 不感知具体 TTS/ASR 模型。

- ASR 输出 `FinalTranscript`，作为 PlayerAdvice 的原始输入来源。
- TTS 消费 `PerformancePlan`，输出 `AudioAssetRef`。
- 历史 AudioAssetRef 记录 voice/model revision 与 hash，支持缓存和可重复播放。

Provider 更换不改变 Story State、NarrativeBlock 或历史 Episode。

## 10. MVP

优先实现：点击/按键说话、Streaming ASR、旁白 + 少量角色音色、基础 Performance、环境循环、SFX、播放打断、缓存、Story Book replay。

AgentScope 的实验性 realtime voice 能力只作为实现适配层，不作为第一版关键依赖。

---

## 11. 进程边界

SwiftUI 进程持有麦克风、播放设备与最终 UI 播放状态；Local Engine 持有 Story/Narrative/Performance 语义。

MVP 控制通道只传递：

- transcript；
- Narrative / Performance metadata；
- Audio asset reference；
- playback / interrupt event。

大型音频二进制不以内嵌 base64 进入 Domain IPC 消息。

## 12. Commit Boundary

### PRE_COMMIT

用户中断可以取消尚未提交的 Turn。

### POST_COMMIT

用户中断只停止 Narrative/Audio 表达；已提交 StateDelta 保持不变。
