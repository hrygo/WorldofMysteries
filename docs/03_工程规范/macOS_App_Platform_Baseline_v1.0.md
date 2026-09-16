# 《诡秘世界》macOS 26+ App 平台与媒体运行时规范 v1.0

> **状态**：工程基线规范（约束 App / Swift / 平台层）  
> **适用范围**：`macos-app/`、平台交互、音频媒体运行时、IPC 客户端  
> **基线目标**：macOS 26+ / Apple Silicon (arm64) / Swift 6.4+ (Xcode 27+)

---

## 1. 核心目标与跨机分发定位

《诡秘世界》不仅为开发者本机编译运行，更面向所有运行在 **macOS 26+ (Apple Silicon arm64)** 上的用户分发。
本规范确立 macOS 26+ 平台的硬性技术选型与新特性约束，防止后续 Agent 引入低效的过时兼容包、废弃 API 或破坏多进程架构。

---

## 2. macOS 26+ 关键新能力与采纳约束

通过对 macOS 26.0+ SDK 与 Swift 6.4 真实头文件的深度探查，本工程对以下能力做出明确规范：

### 2.1 语音采集与 ASR / Barge-in 架构（采纳并强制）

1. **统一音频输入流（`AVFAudio.AVAudioPCMBuffer` → `Speech.AnalyzerInput`）**：
   - **规范约束**：App 端语音采集必须基于 `AVAudioEngine` 的 Input Node 抓取 PCM Buffer，配合 `Speech.framework`（macOS 26+ 原生支持的 `Speech.AnalyzerInput(buffer:)` 与 `Speech.AssetInventory`）。
   - **离线与权限优先**：通过 `Speech.AssetInventory.status(forModules:)` 与 `reserve(locale:)` 保证端侧离线语音识别资产完备，不强制依赖云端网络。
2. **硬件级回声消除与毫秒级打断（Barge-in）**：
   - 启用 `AVAudioEngine` 的 `VoiceProcessingIO` 单元，实现全双工声学回声消除（AEC）。
   - **打断行为准则**：
     - 当麦克风检测到用户输入时（VAD 触发），Swift 端立即静音/暂停正在播放的 `AVAudioPlayerNode`。
     - 向 Local Engine IPC 发送 `TurnInterruptRequest`。
     - 严格遵循**不变量 9（提交即命运）与 5（Barge-in 边界）**：若状态处于 `PRE_COMMIT`，可取消 pending turn；若处于 `POST_COMMIT`，仅切断声音和字幕播放，已写入 `world.db` 的领域事实严禁篡改或回滚。

### 2.2 语言模型与端侧 AI 边界（FoundationModels 框架使用禁令）

macOS 26+ SDK 新增了 `FoundationModels.framework`（`LanguageModelSession`，支持端侧与 Private Cloud Compute）：
- ❌ **绝对禁止违背架构边界**：
  - **严禁**在 `macos-app` 中直接调用 `FoundationModels` 来做角色决策、推演或改变故事。
  - **原因**：根据**不变量 5（AI 仅产出 Proposal，Domain Engine 负责 Commit）**与**不变量 6（零知识越界）**，所有认知与推演必须由 Python Local Engine 内部经过 `Context Compiler` 裁决和 AgentScope 编排，App 进程绝不拥有自主生成剧情状态的权力。
- 允许的边缘用途（需显式审批）：
  - 仅可作为客户端本地纯文本润色、拼写纠错或输入法辅助展示，不得产出任何 Domain State。

### 2.3 跨进程 IPC 与安全沙箱生命周期（Subprocess Lifecycle）

App 进程与同机独立的 Local Engine（Python 3.14.7 + AgentScope）分进程运行：
1. **进程绑定与看门狗（Death-Pact / Subprocess Watchdog）**：
   - App 启动时通过 `Foundation.Process` 拉起随包分发的 Local Engine。
   - 建立双向标准输入输出（stdin/stdout）或 Unix Domain Socket (NDJSON 格式)。
   - App 必须捕获 `NSApplication.willTerminateNotification`，向 Local Engine 发送优雅退出信号（`SIGTERM`），超时 2 秒后强制杀死（`SIGKILL`），保证系统无孤儿进程残留。
2. **凭据安全（Keychain Services）**：
   - 云端 LLM API Keys（如 OpenAI / Anthropic / DashScope 等）严格保存在 macOS Keychain 中，通过 IPC 在需要时受控注入，严禁明文落地到 `.json` 或 `.env`。

### 2.4 Swift 6.4 严格并发规范（Complete Concurrency）

- **全面启用默认数据竞争安全（Data-Race Safety）**：
  - IPC 客户端（`EngineIPCClient`）与音频引擎管理器（`AudioStreamCoordinator`）必须声明为 `actor`。
  - 跨进程传输的 Payload 模型必须声明为 `Sendable`（或由 `contracts/` 生成 Codable Struct）。
  - UI 状态统一采用 `@Observable` 标注并在 `@MainActor` 下执行，杜绝跨线程修改 UI 状态。

### 2.5 现代 UI/UX 规范（Liquid Glassmorphism & 流式排版）

1. **自适应液态毛玻璃材质**：
   - 顶层源堡/灰雾采用自适应系统材质背景，辅以微妙的动态粒度噪点（Noise Shader），保持神秘学灰暗压迫感与现代通透感的平衡。
2. **零抖动流式排版（Smooth Streaming Layout）**：
   - 叙事文本以 NDJSON 流式推送时，使用增量 `AttributedString` 与淡入滑动微动画，避免整段 Text 重新计算高度导致的视窗抖动。
   - 字幕高亮严格根据音频时间戳（Word/Phoneme Timestamps）逐字推进。

---

## 3. Agent 编码与评审门禁清单（Gate Checklist）

为后续 Agent 在此仓库编写 `macos-app` 代码提供机器与自动化评审检查项：

- [ ] **SDK 约束**：Xcode Deployment Target 设为 `macOS 26.0`，无低于 26.0 的废弃 API。
- [ ] **架构不变量**：Swift 代码中没有任何直接操作 SQLite 或生成剧情决策的代码，通信全部走 typed IPC。
- [ ] **并发安全**：无任何 `@unchecked Sendable` 逃逸；所有多线程代码编译期通过 Swift 6.4 严格检查。
- [ ] **音频生命周期**：麦克风会话与播放节点严格绑定用户生命周期，打断响应延时 <= 100ms。
- [ ] **进程看门狗**：测试用例覆盖 App 正常退出、Force Quit 和崩溃时，Local Engine 能 100% 自动安全退出。
