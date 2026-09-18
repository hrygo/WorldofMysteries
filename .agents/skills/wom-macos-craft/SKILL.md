---
name: wom-macos-craft
description: >-
  《诡秘世界》macOS 宿主应用极客技能。指导 SwiftUI 界面构建、Swift 6 严格并发检查 (@MainActor, Actor 隔离, Sendable)、
  WorldSession 响应式流式叙事接入、UDS IPC NDJSON 通信与 Swift Testing 宏单测。
---

# 《诡秘世界》macOS 客户端极客技能 (wom-macos-craft)

本技能用于指导 `AGT-MAC` (macOS Apprentice) 在 `macos-app/` 目录下开发原生、高效、符合 Apple 人机交互指南（HIG）的单人持久世界客户端。

---

## 1. 核心架构约束 (Invariant 12)

- **绝对严禁**：在 Swift 客户端直接 import `SQLite3` 或通过任何驱动读写底层领域数据库。
- **唯一信道**：所有与世界现实的交互，必须经由 Unix Domain Socket (`/tmp/world_of_mysteries_engine.sock`) 以强类型 NDJSON 信封 (`IPCEnvelope`) 形式与本地引擎通信。
- **深模块接入**：视图层不直接编排进程与 Socket 连接，统一经由 `WorldSession` 提供的响应式流消费叙事演出。

---

## 2. Swift 6 严格并发与 @Observable 数据流规范

### 2.1 状态管理分层
- **根状态模型**：全局状态由 `@Observable @MainActor public final class AppState` 管理。
- **IPC 客户端隔离**：`EngineIPCClient` 声明为独立 `actor`，保证多线程并发请求时的内部状态线程安全（Thread-safe Socket Streams）。
- **数据传输对象 (DTO)**：跨语言信封载荷全部继承 `Codable & Sendable`，与 `contracts/schemas/` 严格对齐。

### 2.2 响应式叙事流消费 (Streaming Narrative)
```swift
// 在 SwiftUI 视图层极简消费
Task {
    do {
        let stream = try await appState.worldSession.sendAdvice(inputText)
        for await turn in stream {
            self.currentNarrative = turn.narrativeText
            if let audio = turn.audioChunk {
                audioEngine.enqueue(audio)
            }
        }
    } catch {
        appState.handleError(error)
    }
}
```

---

## 3. 测试与验证工作流

测试严格基于 Swift 6 原生 **Swift Testing** 宏体系（`@Test`, `#expect`）：
```bash
# 运行 Swift 客户端全量单元测试与并发测试 (要求 0 warnings, 0 data races)
swift test --package-path macos-app

# 检查架构独立性 (验证 App 目录零直接 SQLite 依赖)
python3 scripts/check_architecture_fitness.py
```
