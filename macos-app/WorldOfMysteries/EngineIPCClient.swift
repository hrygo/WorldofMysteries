import Foundation

/// Actor managing IPC connection and life cycle with Local Python Engine.
public actor EngineIPCClient {
    public private(set) var isConnected: Bool = false

    public init() {}

    public func connect(socketPath: String) async throws {
        // Scaffolding: connection logic to be implemented
        isConnected = true
    }

    public func disconnect() async {
        isConnected = false
    }
}
