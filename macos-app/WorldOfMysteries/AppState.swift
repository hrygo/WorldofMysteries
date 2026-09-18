import Foundation
import Observation

/// Root Observable state for macOS SwiftUI App.
@Observable
@MainActor
public final class AppState {
    /// 界面唯一允许消费的连接事实。
    public private(set) var connectionState: EngineConnectionState = .idle
    public var connectionError: String?
    public private(set) var activeArtifactContext: ArtifactContext?
    public let ipcClient: EngineIPCClient
    public let processManager: EngineProcessManager

    /// 兼容别名：仅在真实握手成功后为 `true`。
    public var isEngineReady: Bool { connectionState.isReady }

    /// 当前界面展示的是否仍为示例数据（未接入真实 Engine）。
    public var isShowingDemoData: Bool {
        switch connectionState {
        case .scaffoldPreview, .idle: true
        case .connecting, .ready, .failed: false
        }
    }

    public init(
        ipcClient: EngineIPCClient = EngineIPCClient(),
        processManager: EngineProcessManager = EngineProcessManager()
    ) {
        self.ipcClient = ipcClient
        self.processManager = processManager
    }

    /// Coordinate helper process startup and initial IPC handshake.
    public func startAndConnect() async {
        connectionState = .connecting
        do {
            connectionError = nil
            try await processManager.startEngine()
            let defaultSocketPath = "/tmp/world_of_mysteries_engine.sock"
            try await ipcClient.connect(socketPath: defaultSocketPath)
            let handshakeSuccess = try await ipcClient.performHandshake()
            let isScaffold = processManager.isScaffoldOnly || ipcClient.isScaffoldOnly
            if isScaffold {
                // 骨架通道永远不能升级为 ready：此时的握手只是本地回显。
                connectionState = .scaffoldPreview
            } else {
                connectionState = handshakeSuccess ? .ready : .failed(message: "handshake rejected")
            }
        } catch {
            self.connectionError = error.localizedDescription
            connectionState = .failed(message: error.localizedDescription)
        }
    }

    /// Bind the active World / Story snapshot used by world-affecting Artifact actions.
    /// This value is presentation context only; the Local Engine remains authoritative.
    public func updateActiveArtifactContext(_ context: ArtifactContext?) {
        activeArtifactContext = context
    }

    /// Coordinate graceful teardown of IPC connection and engine process.
    public func shutdown() async {
        await ipcClient.disconnect()
        await processManager.terminateEngine()
        self.connectionState = .idle
        self.activeArtifactContext = nil
    }
}
