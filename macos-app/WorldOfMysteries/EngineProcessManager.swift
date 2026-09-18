import Foundation

/// Protocol and skeleton managing Local Python Engine helper process lifecycle (Subprocess Watchdog).
///
/// - Warning: 当前为骨架实现，不会启动任何子进程。`isScaffoldOnly` 为 `true` 时，
///   `AppState` 必须把连接状态降级为 `scaffoldPreview`，不得对外宣称引擎可用。
public actor EngineProcessManager {
    public private(set) var isRunning: Bool = false

    public init() {}

    /// 进程管理是否仍是骨架实现（不会真正拉起 Local Engine 子进程）。
    public nonisolated var isScaffoldOnly: Bool { true }

    public func startEngine() async throws {
        // Scaffolding: process launch and UDS socket bind verification
        isRunning = true
    }

    public func terminateEngine() async {
        // Scaffolding: graceful SIGTERM followed by SIGKILL fallback
        isRunning = false
    }
}
