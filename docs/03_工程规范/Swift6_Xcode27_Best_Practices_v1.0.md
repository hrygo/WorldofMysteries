# 《诡秘世界》Swift 6.4 与 Xcode 27 最佳实践基线 v1.0

> **状态**：工程实现与编译门禁基线  
> **适用范围**：`macos-app/` 下的所有 Swift 源码、SPM 依赖、测试用例与 Xcode 构建配置  
> **基准环境**：Xcode 27.0 (Build 27A266a) / Apple Swift 6.4 / macOS 26.0+ SDK (MacOSX27.0.sdk)

---

## 1. 工具链与工程构建基线 (Toolchain & Build Settings)

在 `macos-app` Xcode 工程或 `Package.swift` 中，必须遵循以下编译器与平台参数锁定：

```text
MACOSX_DEPLOYMENT_TARGET = 26.0
SWIFT_VERSION = 6.0 (Language Mode 6)
SWIFT_STRICT_CONCURRENCY = complete
ENABLE_USER_SCRIPT_SANDBOXING = YES
CLANG_ENABLE_MODULES = YES
```

### 1.1 核心构建要求
1. **纯 arm64 架构**：剔除 `x86_64` 历史遗留交叉编译负担，专注 Apple Silicon（M 系列，针对 M5 等硬件全面支持 NEON 与 AMX/Neural Engine 硬件对齐）。
2. **零编译告警策略（Warnings as Errors）**：在 CI 与 Release 构建中开启 `SWIFT_TREAT_WARNINGS_AS_ERRORS = YES`，尤其是数据竞争、并发隔离和 Sendable 检查相关的警告，绝不允许漏入主干。
3. **SPM (Swift Package Manager) 依赖最小化**：
   - 优先使用 SDK 原生 Frameworks（`Observation`, `AVFAudio`, `Speech`, `AppIntents`）；
   - 第三方依赖必须具备完整的 Swift 6 Mode 兼容声明，严禁引入未做并发安全标注的旧版包。

---

## 2. Swift 6.4 现代并发架构模式 (Concurrency Architecture)

本项目采用多进程双轨运行架构（SwiftUI UI/Media Runtime + Python Local Engine）。为保障在万级 NDJSON 吞吐与实时高频音频流下的系统绝对稳定，必须全面遵循 Swift 6.4 并发范式：

### 2.1 角色与隔离边界 (Isolation Boundaries)

```text
┌────────────────────────────────────────────────────────────┐
│                    @MainActor (UI 渲染层)                   │
│  - SwiftUI Views (WorldHomeView, CardGalleryView...)       │
│  - @Observable UI ViewModels (SessionViewModel)            │
└─────────────────────────────▲──────────────────────────────┘
                              │ AsyncStream / Events
┌─────────────────────────────┴──────────────────────────────┐
│                   Background Actors (业务服务层)             │
│  - actor EngineIPCClient: 负责 UDS/stdin 通信与协议编解码   │
│  - actor AudioStreamCoordinator: 负责 AVAudioEngine 与打断  │
│  - actor EventSubscriptionRegistry: 负责 Outbox 事件分发    │
└────────────────────────────────────────────────────────────┘
```

1. **禁止逃逸原则（No `@unchecked Sendable` Leak）**：
   - 所有跨 Actor 传递的数据模型（来自 `contracts/schemas/*.schema.json` 生成的 Swift 结构体）必须是天然不可变的 `Sendable` `struct`。
   - 严禁滥用 `@unchecked Sendable` 绕过编译器检查；对系统级非 Sendable 句柄（如 `FileHandle`, `Process`），必须封装在特定专用 `actor` 内部，外部仅暴露纯数据异步方法。
2. **异步流式通信模式（`AsyncStream` & `AsyncThrowingStream`）**：
   - IPC 客户端接收 Python Engine 的 NDJSON 事件流时，一律通过 `AsyncStream<EngineEvent>` 暴露给 ViewModel。
   - ViewModel 使用 `.task` 驱动生命周期，视图销毁时利用 Swift 结构化并发（Structured Concurrency）的自动协同取消（Cooperative Cancellation）切断事件监听，杜绝内存泄漏与悬挂监听。

---

## 3. UI 状态管理与数据流最佳实践 (SwiftUI + Observation)

1. **淘汰 `Combine`，全面转向 `@Observable`**：
   - 废弃 `ObservableObject`、`@Published` 与 Combine 订阅链路；
   - 状态模型统一采用 `@Observable final class`，利用 Swift 6.4 的细粒度属性级跟踪（Per-property Tracking），避免全量 View 脏重绘。
2. **流式文本逐字音画对齐（Streaming Phoneme Rendering）**：
   - 故事叙事（Narrative Stream）文字流由 `AttributedString` 增量构建，利用 `.animation(.smooth, value: ...)` 实现平滑淡入滑出；
   - 结合音频播放的毫秒级时间戳驱动字幕高亮，消除任何布局尺寸抖动（Jitter）。

---

## 4. 音频与语音管线实践 (AVFAudio + Speech.framework)

1. **全双工 VoiceProcessingIO 管道**：
   - 使用 `AVAudioEngine` 搭建专用双向节点：
     - **Input**: 接入 `AVAudioInputNode` 并开启 VoiceProcessing，实现硬件级回声消除（AEC）与降噪；
     - **Output**: 接入 `AVAudioPlayerNode` 播放 Character TTS 渲染结果。
2. **毫秒级 Barge-in 打断实施规范**：
   - 采集到的 PCM Buffer 在后台流式送入端侧 `Speech.framework`（`AnalyzerInput`）；
   - 当 VAD 判定为有效语音输入时，Swift 端在 **100ms** 内触发：
     1. `audioPlayerNode.pause()` / 渐隐淡出音量；
     2. 向 IPC Client 调用 `await ipcClient.sendInterrupt(turnId: currentTurnId)`；
     3. 遵循不变量 9：处于 `PRE_COMMIT` 可放弃当前 Turn，若已 `POST_COMMIT` 则维持领域事实不变，仅切断声音播放。

---

## 5. 跨进程 IPC 进程守护实践 (Subprocess Lifecycle & Watchdog)

1. **生命周期绑定契约（Parent-Child Death Pact）**：
   - Swift 客户端使用 `Foundation.Process` 启动 Local Engine Python 进程；
   - 监听标准错误输出（stderr）捕获 Engine 的 Python traceback 与 panic；
   - 监听 `NSApplication.willTerminateNotification` 与系统信号：
     ```swift
     // 退出时优雅回收
     process.terminate() // SIGTERM
     Task {
         try? await Task.sleep(nanoseconds: 2_000_000_000)
         if process.isRunning {
             kill(process.processIdentifier, SIGKILL)
         }
     }
     ```
2. **标准 NDJSON IPC 协议对齐**：
   - 通信严格遵循 `contracts/protocol/engine_ipc.schema.json`；
   - 消息每行一条完整 JSON，以 `\n` 分隔；解析层使用 Swift `JSONDecoder`，字段校验失败直接上报 Protocol Violation 诊断日志，不尝试做宽容容错。

---

## 6. Xcode 27 单元测试与测试覆盖要求

1. **Swift Testing 框架优先（`import Testing`）**：
   - 推荐全面使用 Swift 现代 `@Test` 与 `@Suite` 宏替代繁琐的 `XCTestCase`；
   - 测试异步方法使用原生 `async/await`，支持参数化测试（Parameterized Testing）批量覆盖 Golden Scenario 事件序列。
2. **模拟 IPC 回环测试（Mock IPC Loopback）**：
   - 针对 `EngineIPCClient` 构建内存级双向虚拟流，验证在断网、子进程闪退、乱序报文注入时的状态恢复与重连逻辑。

---

## 7. 约束检查清单（Agent Code Review Checklist）

后续 Agent 在修改或新增 `macos-app/` 代码时必须逐项通过：

- [ ] 是否在 Xcode / SPM 中锁定了 `SWIFT_STRICT_CONCURRENCY = complete`？
- [ ] 是否有未隔离的全局可变状态（`global var`）？
- [ ] 是否使用了 `@unchecked Sendable`？如果是，必须附带内存线程安全审计注释。
- [ ] UI 状态是否基于 `@Observable` 并由 `@MainActor` 严格保护？
- [ ] 音频管线是否有内存泄漏风险（循环引用闭包、未停止的引擎节点）？
- [ ] App 进程是否杜绝了直接引用 SQLite 驱动或私自执行剧情推演的越权行为？
