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

### 6.1 VoicePersona 注册与供应商音色映射表 (Voice Persona Mapping)
系统建立中心化的 `VoicePersonaRegistry`，将角色身份与各底层服务商的物理音色深度解耦：
1. **抽象音色标识 (Logical Voice ID)**：
   - 每个角色与叙事视角持有逻辑音色 ID（例如 `narrator.omniscient`, `char.evelyn_gray`, `char.morris_clinic`）。
2. **多供应商映射矩阵 (Provider Mapping Matrix)**：
   - **SpeechRail (本地自建)**：映射至微调音色（如 `evelyn_seer_v1`, `morris_tired_v1`, `narrator_victorian_v1`）；
   - **OpenAI 官方**：映射至标准音色（如 `nova` for Evelyn, `onyx` for Morris, `fable` for Narrator）；
   - **Azure / Groq / ElevenLabs**：映射至对应服务商特有音色 ID。
3. **平滑回退 (Fallback Tier)**：
   - 若当前激活的 Provider 缺少特定角色的定制音色，自动回退到 Provider 的 `default_voice`（中性音色），不阻塞合成管线。

## 7. Audio Scene

环境声由场景状态驱动，而非每句由 LLM 自由描述。Ambience 与 SFX 使用结构化资产 ID；音乐只在重大节点克制使用，Silence 也是正式音频元素。

## 8. AudioTimeline

`NarrativeBlock → PerformancePlan → AudioAssetRef` 后形成播放 `AudioTimeline`。AudioTimeline 同步语音、环境声、SFX、字幕与 UI 状态，但不属于 Domain Truth；它可以从 NarrativeBlock、PerformancePlan 和资产元数据重新构建。

## 9. Provider Adapter 与 OpenAI SDK 标准接入架构

ASR/TTS 统一通过标准 Provider Protocol 接入，彻底与底层模型解耦。Story Engine 与 UI 不感知具体语音服务商细节。

### 9.1 OpenAI SDK 标准化协议基线
为了保证行业通用性与极简集成度，系统语音层统一采用 **OpenAI Audio API Spec** 作为标准适配契约：
- **ASR (转录)**：调用兼容 `client.audio.transcriptions.create(model=..., file=..., ...)` 接口，输出标准化的 `FinalTranscript`。
- **TTS (语音合成)**：调用兼容 `client.audio.speech.create(model=..., voice=..., input=..., response_format=...)` 接口，输出音频二进制并写入缓存生成 `AudioAssetRef`。

### 9.2 默认对接 SpeechRail 与第三方无感切换
系统设计为 **100% 可插拔 (Pluggable)** 架构，通过外部注入的 `AudioProviderConfig` 进行路由：
- **默认提供商**：对接本地/自建的 **SpeechRail** 服务，默认 `base_url` 路由至 SpeechRail 兼容端点（例如 `http://localhost:8080/v1`），音色与 Character VoicePersona 绑定。
- **热插拔第三方**：无需改动任何领域业务代码，仅需修改 `AudioProviderConfig` 中的 `base_url`、`api_key`、`asr_model`（如 `whisper-1`）与 `tts_model`（如 `tts-1` / `tts-1-hd`），即可随时平滑切换为：
  - OpenAI 官方云端服务；
  - Azure OpenAI Audio；
  - Groq Whisper / Cloudflare Workers AI；
  - ElevenLabs（经 OpenAI 兼容代理网关）；
  - LocalAI / 自建 FastAPI Whisper & XTTS / CosyVoice 服务。

### 9.3 历史回放与事实隔离
- 历史 `AudioAssetRef` 记录 `provider_id`、`model`、`voice` 与音频指纹 Hash，保证缓存命中与离线回放。
- Provider 的切换、重试或网络抖动，绝对不反向篡改已提交的 `StoryState`、`NarrativeBlock` 或历史 `Episode`（严格遵循不变量 9）。

### 9.4 内容寻址音频缓存管线 (Content-Addressable Audio Asset Pipeline)
为兼顾高响应速度、杜绝重复网络计费与实现纯离线剧目回放，系统强制推行内容寻址缓存：
1. **全局唯一资产指纹 (Deterministic Audio Hash)**：
   $$\text{AudioHash} = \text{SHA256}(\text{provider\_id} + \text{":"} + \text{model} + \text{":"} + \text{voice} + \text{":"} + \text{speed} + \text{":"} + \text{UTF8}(\text{text}))$$
2. **持久化寻址存储规范**：
   - 存储路径：`~/Library/Application Support/WorldOfMysteries/assets/audio/{AudioHash[0:2]}/{AudioHash}.{ext}`
   - 格式统一采用 MP3 (可配置为 AAC/Opus)；
3. **合成命中策略**：
   - 在向底层 Adapter 发起 TTS 请求前，强制优先检索本地缓存；
   - 若缓存已存在且校验完整，直接返回 `AudioAssetRef`，API 调用耗时归零；
   - 用户在 Story Book 翻阅过往章节时，100% 消费本地缓存音频，无网络依赖。

### 9.5 网络异常韧性与无感字幕降级 (Resilience & Graceful Fallback)
语音合成属于体验增强层（Performance Layer），绝不成为叙事推进的阻塞性单点故障：
1. **分级异常降级**：
   - **Level 1 (原位重试)**：遇到偶发网络超时或连接重置时，执行 1 次带 Jitter 的指数退避快速重试（最多等待 1.5s）；
   - **Level 2 (备用端点切换)**：若配置了 Fallback Provider（如 OpenAI 官方云端备用），自动尝试备用端点；
   - **Level 3 (静默字幕降级 - Mute Subtitle Fallback)**：若所有语音服务均不可达，TTS 层静默记录日志并返回纯文本占位符，UI 自动无缝以字幕滚动形式呈现台词，不阻断故事生命周期。
2. **不变量守卫**：
   - 无论发生何种 TTS 故障，已提交的领域事实（`world.db` / `TurnTransaction`）绝对保持不可篡改。

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


## v2 演进方案（待实施，保留 v1 历史行为）

[Voice-First v2技术与实施入口](../03_工程规范/voice/README.md)提出稳定身份、有效表演、
流式媒体控制、动态选角与恢复方案。其中“缺少音色直接fallback到default_voice”和“仅以旧AudioHash配方缓存”
拟由显式身份保真降级与版本化RenderManifest替代；这是待实施修订，不表示当前adapter已完成变更。
公共协议、DTO和持久化迁移须走独立实现PR与对应门禁，不能只据本文调用尚未支持的新字段。
