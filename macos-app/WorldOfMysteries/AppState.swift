import Foundation
import Observation

/// Root Observable state for macOS SwiftUI App.
@Observable
@MainActor
public final class AppState {
    public var isEngineReady: Bool = false
    public let ipcClient: EngineIPCClient

    public init(ipcClient: EngineIPCClient = EngineIPCClient()) {
        self.ipcClient = ipcClient
    }
}
