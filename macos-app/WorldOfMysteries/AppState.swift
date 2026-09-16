import Foundation
import Observation

/// Root Observable state for macOS SwiftUI App.
@Observable
@MainActor
public final class AppState {
    public var isEngineReady: Bool = false
    public var connectionError: String?
    public let ipcClient: EngineIPCClient
    public let processManager: EngineProcessManager

    public init(
        ipcClient: EngineIPCClient = EngineIPCClient(),
        processManager: EngineProcessManager = EngineProcessManager()
    ) {
        self.ipcClient = ipcClient
        self.processManager = processManager
    }

    /// Coordinate helper process startup and initial IPC handshake.
    public func startAndConnect() async {
        do {
            connectionError = nil
            try await processManager.startEngine()
            let defaultSocketPath = "/tmp/world_of_mysteries_engine.sock"
            try await ipcClient.connect(socketPath: defaultSocketPath)
            let handshakeSuccess = try await ipcClient.performHandshake()
            self.isEngineReady = handshakeSuccess
        } catch {
            self.isEngineReady = false
            self.connectionError = error.localizedDescription
        }
    }

    /// Coordinate graceful teardown of IPC connection and engine process.
    public func shutdown() async {
        await ipcClient.disconnect()
        await processManager.terminateEngine()
        self.isEngineReady = false
    }
}
