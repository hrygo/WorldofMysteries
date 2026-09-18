import Foundation

/// Actor managing IPC connection and life cycle with Local Python Engine.
///
/// - Warning: 当前实现是**骨架通道**：`connect` 不会真的打开 UDS，`send` 返回本地回显。
///   任何界面都不得据此宣称「本地引擎已就绪」，必须读取 `isScaffoldOnly` 并降级表达。
public actor EngineIPCClient {
    public private(set) var isConnected: Bool = false

    public init() {}

    /// 传输层是否仍是骨架实现（不会真正连接 Local Engine）。
    public nonisolated var isScaffoldOnly: Bool { true }

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
