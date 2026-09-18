import Foundation

/// Authenticated, framed Local Engine client. A connection is not a world session.
public actor EngineIPCClient {
    private var transport: EngineSocketTransport?
    private var generation: UInt64 = 0
    private var handshaking = false
    public private(set) var handshake: EngineHandshake?
    private let requestTimeout: TimeInterval
    public var isConnected: Bool { transport?.isConnected == true && handshake != nil }
    public nonisolated var isScaffoldOnly: Bool { false }

    public init(requestTimeout: TimeInterval = 5) {
        self.requestTimeout = requestTimeout.isFinite && requestTimeout > 0 ? requestTimeout : 5
    }

    public func connect(socketPath: String) async throws {
        generation &+= 1
        let attempt = generation
        handshake = nil
        handshaking = false
        let previous = transport
        let next = EngineSocketTransport()
        transport = next
        await previous?.close()
        do {
            try await next.connect(path: socketPath, timeout: requestTimeout)
            guard generation == attempt else { throw CancellationError() }
        } catch {
            await next.close()
            if generation == attempt { transport = nil }
            throw error
        }
    }

    @discardableResult
    public func performHandshake(sessionToken: String, traceId: String = UUID().uuidString) async throws -> EngineHandshake {
        guard let connection = transport, handshake == nil, !handshaking else { throw EngineConnectionError.notConnected }
        let attempt = generation
        handshaking = true
        defer { if generation == attempt { handshaking = false } }
        let request = IPCEnvelope(kind: "request", traceId: traceId, requestId: UUID().uuidString,
            method: "system.handshake", payload: [
                "app_version": .string("0.1.0"), "app_build": .string("100"),
                "supported_protocols": .array([.string("1.0")]), "session_token": .string(sessionToken)
            ])
        do {
            let response = try await connection.request(request, timeout: requestTimeout)
            guard response.status == "ok", let payload = response.payload else { throw EngineConnectionError.authenticationFailed }
            let welcome = try EngineHandshake(payload: payload)
            guard generation == attempt, connection.isConnected else { throw EngineConnectionError.disconnected }
            handshake = welcome
            return welcome
        } catch {
            await connection.close()
            if generation == attempt { handshake = nil; transport = nil }
            throw error
        }
    }

    public func send(envelope: IPCEnvelope) async throws -> IPCEnvelope {
        guard let connection = transport, let handshake, connection.isConnected else {
            throw EngineConnectionError.notConnected
        }
        guard let method = envelope.method, handshake.capabilities.contains(method) else {
            throw EngineConnectionError.methodUnavailable
        }
        // No retries here: losing a response never authorizes another mutation.
        return try await connection.request(envelope, timeout: requestTimeout)
    }

    public func health() async throws -> EngineHealth {
        let response = try await send(envelope: IPCEnvelope(kind: "request", traceId: UUID().uuidString,
            requestId: UUID().uuidString, method: "system.health"))
        guard response.status == "ok", let payload = response.payload else { throw EngineConnectionError.invalidFrame }
        return try EngineHealth(payload: payload)
    }

    public func eventStream() throws -> AsyncThrowingStream<IPCEnvelope, any Error> {
        guard let transport, isConnected else { throw EngineConnectionError.notConnected }
        return transport.events
    }

    public func connectionFailures() throws -> AsyncStream<EngineConnectionError> {
        guard let transport, isConnected else { throw EngineConnectionError.notConnected }
        return transport.failures
    }

    public func disconnect() async {
        generation &+= 1
        handshake = nil
        handshaking = false
        let previous = transport
        transport = nil
        await previous?.close()
    }
}
