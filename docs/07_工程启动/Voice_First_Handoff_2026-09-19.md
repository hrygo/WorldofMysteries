# Voice-First Runtime 接续指南（2026-09-19）

> 目的：让没有当前聊天上下文的后续团队，仅凭仓库与 GitHub 记录即可继续 Voice-First 工作。  
> 本文记录的是 **2026-09-19 的执行快照**，不是永久不变的状态页；开工前必须重新读取 `main`、相关 PR、SpeechRail 实际合并 commit 与门禁结果。

## 1. 先读什么：唯一入口与优先级

按以下顺序获取事实，后面的层级不能覆盖前面的已发布事实：

1. **已合并代码 / contracts / tests on `main`**：当前可运行能力的最高事实源。
2. **当前正在实施的 PR**：尚未进入 main 的能力，只能按该 PR 的实际 head、diff 与 CI 解释。
3. `docs/03_工程规范/Engine_Media_Protocol_v1.0.md`：该文件当前只存在于 PR #71；**仅在 PR #71 合并后**成为 main 上的 W-V01 媒体协议事实源。在此之前请从 PR #71 查看该文件，不在 main 文档中制造断链。
4. [Voice-First 技术设计](../03_工程规范/voice/Voice_First_Technical_Design_v2.0.md)：架构与目标语义。
5. [实施计划](Voice_First_Implementation_Plan_v2.0.md) 与 [验收矩阵](Voice_First_Acceptance_v2.0.md)：任务边界、完成标准与测试 ID。
6. [SpeechRail 接入契约](../03_工程规范/voice/SpeechRail_Integration_Contract_v1.0.md)：跨仓边界与 SR-V01..SR-V12 任务映射。
7. Issue / 设计草案：只能说明“计划做什么”，**不能当作 API 已实现证据**。

若本文与代码事实冲突，以已合并代码、受保护 Schema 和最新成功 Work Receipt 为准；本文需要随后修订。

## 2. 当前总体状态

| Workstream | 状态 | 事实 |
|---|---|---|
| Voice-First v2 总体方案 | **已合并** | PR #69 已合并到 main，包含技术设计、实施计划、验收矩阵与 SpeechRail 跨仓任务 |
| W-V00 连接与能力基线 | **已合并** | PR #70；默认 SpeechRail 端点、unknown ASR confidence、保守 capability probe 已进入 main |
| W-V01 安全媒体通道 | **实现中 / 未放行** | PR #71；contracts、Python/Swift media primitive、media.open grant 已实现，但最终正式门禁尚未全绿 |
| W-V02 原生采集 / Realtime ASR | **未开始产品接线** | 依赖 W-V01 稳定边界；可先准备设计与 fake-event 测试 |
| W-V03 Realtime TTS / Playback | **未开始产品接线** | 依赖 W-V01；可与 W-V02 并行准备 |
| W-V04+ VoiceBinding / Casting / AudioTake | **设计完成、代码未落地** | 强版本保证需结合 SpeechRail 后续能力 |
| SpeechRail SR-V01..SR-V12 | **跨仓 backlog 已建立** | SpeechRail 团队已接单；真正接线前必须核对上游实际 merge commit / contract |

### 已合并的重要基线

- PR #69：Voice-First v2 方案包，merge commit `cfda5bc00602cf0384b61345d3ae8e6a93fca056`。
- PR #70：W-V00，merge commit `f720904c08fd754875fd320f9f615c17d215bf9f`。
- W-V00 的结论已经是 main 事实，不再使用技术设计 §2 中旧的“localhost:8080 / confidence=1.0”描述作为当前代码事实。

## 3. W-V01：当前实现事实

当前实施 PR：**WorldofMysteries #71**，分支 `feat/voice-v01-media-contract`。

已实现的主要能力：

### 3.1 Wire / contracts

- `contracts/protocol/engine_media.schema.json`
- `contracts/protocol/engine_media_control.schema.json`
- Python/Swift 共用媒体 fixture
- 严格 JSON、big-endian length framing、mono PCM16、16/24/48 kHz
- CHUNK sequence / offset / frame / byte / SHA-256 完整性约束
- bounded credit / backpressure
- unknown version / unknown field fail closed

### 3.2 Engine / control security

- `media.open` 通过已认证 control IPC 签发短时、一次性 bearer ticket
- ticket 绑定 engine epoch、stream、trace、generation、direction、format 与限额
- ticket 不落盘、不进入日志，消费后不可 replay
- 默认 Engine CLI 没有真实 media session handler 时 **不广告 `media.open`**
- 当前 primitive 不代表真实麦克风 / TTS / 播放器已经上线

### 3.3 Swift

- `MediaProtocol.swift`
- `EngineIPCClient.openMedia(...)`
- Python ↔ Swift field parity
- credit window / receive continuity / END totals / digest
- ticket redaction

### 3.4 Packaging 回归

W-V01 引入 `MediaProtocol.swift` 后，production packaging probe 的手工 Swift source closure 曾漏掉该依赖。已修复并补 host-independent 回归：

- package probe source closure fix 已有独立 Work Receipt；
- package regression test 已有独立 Work Receipt；
- 不允许通过放宽生产断言绕过此类错误。

## 4. W-V01 当前唯一收尾问题

正式提交 `07a800cc9696acc37fa6cf51c8fa997206b7e5ad` 将 Engine 启动职责从 `ContentView.task` 上移到 process-level App lifecycle：

```text
EngineAppDelegate
  └─ applicationDidFinishLaunching
       └─ AppState.startAndConnect()

SwiftUI Views
  └─ 只消费同一个 AppState，不负责进程 bootstrap
```

### 已得到的诊断证据

- 最新目标 main 的同一 `BUNDLED_RUNTIME_P0` 独立运行成功。
- W-V01 旧 head 可稳定复现 “Release App did not start its bundled Engine”。
- 失败 Release App 的主线程 sample 显示 AppKit event loop 正常，无 UI 死锁；问题是 bootstrap 没有可靠发生。
- 将 bootstrap 上移 AppDelegate 的诊断树：
  - Swift tests / Xcode build 成功；
  - Bundled Runtime 成功；
  - Release App 约 2.78 秒拉起 Engine；
  - Engine crash recovery / App force-quit cleanup 成功。

### 正式 head 尚未放行的原因

正式 CI 的 Swift 测试 `Process lifecycle owns Engine bootstrap instead of a SwiftUI view` 当前在 2 秒等待内仍观察到 `.connecting`，因此 Stage 3 失败；正式 Bundled gate 同一 head 也仍为失败记录。

**接手团队不得写“W-V01 已完成”。** 下一步应：

1. 从最新 main 重新同步 PR #71，保留 main 上 Component Gallery 的 `MyApp.swift` 变化，同时保留 AppDelegate 单一 AppState / process bootstrap。
2. 修复生命周期测试的确定性等待/可观察点，**不能删除测试或把失败条件放宽成只检查 Task 被创建**。
3. 在最终同步 head 上重新跑：
   - Capsule Audit
   - Python Engine & Contracts
   - Swift 6 Tests + Xcode build
   - Bundled Engine Engineering Verification
4. 为最终实质代码重新签发非 stale Work Receipt；不要使用 `--allow-stale`。
5. 全绿后才把 PR #71 转 Ready；仍需显式合并授权。

## 5. W-V02：下一支可接续团队的输入

目标：**真实麦克风 → SpeechRail Realtime ASR → 唯一 FinalTranscript**。

首版必须保持：

- PTT/manual endpointing；
- ASR 与 TTS 独立连接；
- partial 只用于 UI；
- 多 rollover item 属于同一个 `input_turn_id`；
- 普通 ASR 使用已核验的 `append drain → commit → clear → cleared` 收口；
- `cleared` 只是排空栅栏，不是“识别成功”；
- 任意 append/commit error、failed/missing item、连接缺口都不得发布部分 Final；
- 当前 `previous_item_id` 不能作为普通 ASR item 链权威；
- unknown confidence 保持 unknown。

建议先交付显式 `media_demo`，在真实 Domain 尚未接线时不能把 fixture 回合包装为 `story_voice`。

参考：
- [首批开工规格](Voice_First_Kickoff_Spec_v1.0.md)
- [验收矩阵](Voice_First_Acceptance_v2.0.md)

## 6. W-V03：可并行准备的输入

目标：**COMMIT 后的 sealed text → SpeechRail TTS → PCM media stream → native playback**。

不可变边界：

- Narrative / Audio 必须在 Domain COMMIT 后；
- stop 先本机停声 / generation 失效，再异步 provider cancel；
- `MediaStop / Pause / Replay / Volume` 不等于 Domain `cancel_pending`；
- 迟到旧 generation PCM 一律丢弃；
- Provider 完成 ≠ 设备播放完成；DeliveryCursor 必须独立；
- 断流不得发布完整 AudioTake；
- 一个活跃 TTS response 起步，不在互动热路径做 VoiceDesign / 质量验证。

## 7. SpeechRail 接线触发条件

SpeechRail 团队维护 SR-V01..SR-V12。WorldofMysteries 不需要等待所有项目完成，但以下能力一旦上游真正合并，需要主动升级消费者：

| SpeechRail 能力 | WoM 接线动作 |
|---|---|
| SR-V01 EffectiveCapabilitySnapshot | 将 W-V00 的 `legacy_observed` 升级为一致 snapshot；不得按 Issue 文本预造字段 |
| SR-V02 ImmutableVoiceRevision | VoiceBinding / RenderKey 开始使用不可变 revision；强身份承诺此前只能是 legacy assurance |
| SR-V03 Verifiable TTS terminal/receipt | 完整 AudioTake / HTTP 流缓存使用实际 resolved identity 与终态证据 |
| SR-V08 ASR completion contract | W-V02 将当前已核验 EOF 规则切换为正式公共契约并补兼容测试 |
| SR-V09 Pronunciation | SpokenText / DisplayText / span mapping 接入 RenderKey |
| SR-V10 Structured Voice Catalog | W-V05 动态选角消费结构化 descriptor，不解析私有 `ref_text` |
| SR-V11 Prosody Planner | 长叙述的 planner version / chunk continuity 接入 |
| SR-V12 Timing Sidecar | 字幕/口型使用真实分级时间轴，不做平均语速伪造 |

接线时的硬规则：**先核对 SpeechRail 实际 merge commit、公开 contract、fixture 和兼容策略，再写消费者。Issue“已接单”不等于 API 已存在。**

## 8. 验收与证据层级

不得混淆以下四层：

1. `software_verified`：Schema / Python / Swift / CI。
2. `service_verified`：真实 SpeechRail 请求与终态。
3. `device_accepted`：真实麦克风、AEC、扬声器、USB/蓝牙设备。
4. `release_accepted`：最终签名/分发包和真实用户机器。

当前：

- W-V00 已达到 software_verified 并已合并；
- W-V01 仍在 software/package 收尾，尚未进入真实语音设备验收；
- 没有任何文档可以把候选 SLO 写成已测成绩。

## 9. 不要重复踩的坑

- 不要把设计文档固定基线中的旧源码事实当当前代码事实。
- 不要把 `media.open` primitive 当成真实语音产品路径已开启。
- 不要把 SpeechRail Issue 当成已发布 API。
- 不要把 ASR buffer commit 当 Domain COMMIT。
- 不要把 TTS `response.done` 当“用户已经听到”。
- 不要让 App / SwiftUI 直接读写 Domain DB。
- 不要为了让测试变绿关闭 Sandbox / Library Validation / ticket 校验 / strict JSON。
- 不要把 Engine 生命周期重新挂回某个 View 的 `.task`。
- 不要在同一个 macOS runtime 验收中启动多个同名 App 实例。

## 10. 交接检查清单

接手团队开始前：

- [ ] 读取最新 `AGENTS.md`。
- [ ] 固定最新 `main` SHA。
- [ ] 回读 PR #69/#70/#71 实际 state/head，而不是依赖本文快照。
- [ ] 查看 [语音工作包](../03_工程规范/voice/README.md)。
- [ ] 查看本任务对应 W-Vxx 与验收 ID。
- [ ] 若改代码，按 HACF 重新 pack，不复用 stale capsule。
- [ ] 若改跨语言协议，先改 contracts，再同步 Python/Swift fixture parity。
- [ ] 若依赖 SpeechRail 新能力，先读上游实际实现，不按 Issue 描述猜接口。
- [ ] 完成后分别声明“代码完成 / 服务验证 / 设备验收 / 发布验收”，缺哪层就明确保留缺口。

## 11. 推荐接续顺序

```text
Team A / macOS
  先关闭 PR #71 的正式生命周期测试与 Bundled gate

Team B / Voice
  在 W-V01 稳定协议上准备 W-V02 ASR client + turn assembler

Team C / Voice + macOS
  并行准备 W-V03 TTS stream + playback generation / stop

SpeechRail Team
  独立推进 SR-V01..SR-V12
  → 真正 merge 后通知 WoM 消费者做契约升级
```

W-V01 未合并前，W-V02/W-V03 可以写隔离实现和 fake fixture，但不应把尚未稳定的媒体协议复制成第二套本地协议。
