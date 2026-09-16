import Foundation

/// Actor managing IPC connection and life cycle with Local Python Engine.
public actor EngineIPCClient {
    public private(set) var isConnected: Bool = false

    public init() {}

    public func connect(socketPath: String) async throws {
        // Scaffolding: socket connection logic
        isConnected = true
    }

    public func performHandshake(traceId: String = UUID().uuidString) async throws -> Bool {
        guard isConnected else { return false }
        let handshakeReq = IPCEnvelope(
            kind: "request",
            protocolVersion: "1.0",
            traceId: traceId,
            requestId: UUID().uuidString,
            method: "system.handshake"
        )
        let response = try await send(envelope: handshakeReq)
        return response.status == "ok"
    }

    public func send(envelope: IPCEnvelope) async throws -> IPCEnvelope {
        guard isConnected else {
            throw NSError(domain: "EngineIPCClient", code: -1, userInfo: [NSLocalizedDescriptionKey: "Engine IPC not connected"])
        }
        // Echo mock response for baseline handshake
        if envelope.method == "system.handshake" {
            return IPCEnvelope(
                kind: "response",
                protocolVersion: "1.0",
                traceId: envelope.traceId,
                requestId: envelope.requestId,
                status: "ok"
            )
        }
        return IPCEnvelope(
            kind: "response",
            protocolVersion: "1.0",
            traceId: envelope.traceId,
            requestId: envelope.requestId,
            status: "ok"
        )
    }

    public func disconnect() async {
        isConnected = false
    }
}
