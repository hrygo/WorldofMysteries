import Foundation
import Observation

/// Root UI state. The Engine owns facts; a transport handshake is not world readiness.
@Observable
@MainActor
public final class AppState {
    public private(set) var connectionState: EngineConnectionState = .idle
    public var connectionError: String?
    public private(set) var activeArtifactContext: ArtifactContext?
    public private(set) var engineHealth: EngineHealth?
    public private(set) var engineHandshake: EngineHandshake?
    public let ipcClient: EngineIPCClient
    public let processManager: EngineProcessManager

    @ObservationIgnored private var connectionTask: Task<Void, Never>?
    @ObservationIgnored private var stopTask: Task<Void, Never>?
    @ObservationIgnored private var monitorTask: Task<Void, Never>?
    @ObservationIgnored private var reconnectTask: Task<Void, Never>?
    private var generation: UInt64 = 0
    private var stopIdentity = UUID()

    /// Existing world-affecting adapters remain unavailable on a system-only Engine.
    public var isEngineReady: Bool { connectionState.isReady }

    /// All current world surfaces still use DemoWorldSnapshot. Never relabel them
    /// as live just because transport works, a connection fails, or a retry begins.
    public var isShowingDemoData: Bool { true }

    public var serviceStatusText: String? {
        guard let engineHealth else { return nil }
        return "模型" + (engineHealth.modelReady ? "可用" : "未连接") + " · 语音" + (engineHealth.voiceReady ? "可用" : "未连接")
    }

    public init(ipcClient: EngineIPCClient = EngineIPCClient(), processManager: EngineProcessManager = EngineProcessManager()) {
        self.ipcClient = ipcClient
        self.processManager = processManager
    }

    public func startAndConnect() async {
        reconnectTask?.cancel()
        reconnectTask = nil
        await connect(remainingRetries: 2)
    }

    private func connect(remainingRetries: Int) async {
        if let stopTask { await stopTask.value }
        if let connectionTask { await connectionTask.value; return }
        guard !Task.isCancelled else { return }
        generation &+= 1
        let attempt = generation
        monitorTask?.cancel()
        monitorTask = nil
        clearRuntime()
        connectionError = nil
        connectionState = .connecting
        let task = Task { await connectOnce(attempt: attempt, remainingRetries: remainingRetries) }
        connectionTask = task
        await withTaskCancellationHandler { await task.value } onCancel: { task.cancel() }
        if generation == attempt { connectionTask = nil }
    }

    private func connectOnce(attempt: UInt64, remainingRetries: Int) async {
        do {
            await ipcClient.disconnect()
            await processManager.terminateEngine()
            try Task.checkCancellation()
            let launch = try await processManager.startEngine()
            try Task.checkCancellation()
            try await ipcClient.connect(socketPath: launch.socketPath)
            let welcome = try await ipcClient.performHandshake(sessionToken: launch.token)
            let health = try await ipcClient.health()
            try Task.checkCancellation()
            guard generation == attempt, health.transportReady, await ipcClient.isConnected else {
                throw EngineConnectionError.disconnected
            }
            let failures = try await ipcClient.connectionFailures()
            engineHandshake = welcome
            engineHealth = health
            connectionState = health.worldReady && welcome.capabilities.contains("world.home") ? .ready : .transportReady
            monitorTask = Task { [weak self] in
                for await failure in failures {
                    guard !Task.isCancelled else { return }
                    self?.connectionLost(failure, attempt: attempt, remainingRetries: remainingRetries)
                    return
                }
            }
        } catch {
            await ipcClient.disconnect()
            await processManager.terminateEngine()
            guard generation == attempt else { return }
            clearRuntime()
            let failure = (error as? EngineConnectionError) ?? .connectionFailed
            connectionError = failure.errorDescription
            connectionState = failure == .runtimeUnavailable ? .unavailable : .failed(message: failure.errorDescription ?? "本地引擎连接失败。")
        }
    }

    private func connectionLost(_ failure: EngineConnectionError, attempt: UInt64, remainingRetries: Int) {
        guard generation == attempt else { return }
        clearRuntime()
        connectionError = failure.errorDescription
        connectionState = .failed(message: failure.errorDescription ?? "本地引擎连接已断开。")
        // Bounded recovery of transport only. Never resubmit advice, world commands,
        // or pending mutations. A crash loop exhausts this budget instead of spinning.
        guard remainingRetries > 0 else { return }
        reconnectTask = Task { [weak self] in
            do { try await Task.sleep(for: .milliseconds(250)) } catch { return }
            guard let self, self.generation == attempt, !Task.isCancelled else { return }
            await self.connect(remainingRetries: remainingRetries - 1)
        }
    }

    public func updateActiveArtifactContext(_ context: ArtifactContext?) { activeArtifactContext = context }

    private func clearRuntime() {
        engineHealth = nil
        engineHandshake = nil
        activeArtifactContext = nil
    }

    /// Idempotent stop barrier: a new start waits until cancelled startup and teardown
    /// finish, so an old completion cannot overwrite or terminate the next session.
    public func shutdown() async {
        if let stopTask { await stopTask.value; return }
        generation &+= 1
        let identity = UUID()
        stopIdentity = identity
        reconnectTask?.cancel(); reconnectTask = nil
        monitorTask?.cancel(); monitorTask = nil
        let startup = connectionTask
        startup?.cancel()
        connectionTask = nil
        clearRuntime()
        connectionState = .idle
        connectionError = nil
        let task = Task {
            await startup?.value
            await ipcClient.disconnect()
            await processManager.terminateEngine()
        }
        stopTask = task
        await task.value
        if stopIdentity == identity { stopTask = nil }
    }
}
