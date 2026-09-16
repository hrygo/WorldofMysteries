import Foundation

/// Protocol and skeleton managing Local Python Engine helper process lifecycle (Subprocess Watchdog).
public actor EngineProcessManager {
    public private(set) var isRunning: Bool = false

    public init() {}

    public func startEngine() async throws {
        // Scaffolding: process launch and UDS socket bind verification
        isRunning = true
    }

    public func terminateEngine() async {
        // Scaffolding: graceful SIGTERM followed by SIGKILL fallback
        isRunning = false
    }
}
