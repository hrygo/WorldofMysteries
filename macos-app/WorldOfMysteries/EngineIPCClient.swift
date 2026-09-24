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


    public func openMedia(
        direction: MediaDirection,
        generation: Int64,
        format: MediaFormat,
        traceId: String = UUID().uuidString
    ) async throws -> MediaOpenGrant {
        guard generation >= 0, generation <= Int64(Int.max) else {
            throw EngineConnectionError.invalidConfiguration
        }
        let request = IPCEnvelope(
            kind: "request",
            traceId: traceId,
            requestId: UUID().uuidString,
            method: "media.open",
            payload: [
                "direction": .string(direction.rawValue),
                "generation": .int(Int(generation)),
                "format": .object([
                    "codec": .string(format.codec),
                    "sample_rate": .int(format.sampleRate),
                    "channels": .int(format.channels),
                ]),
            ]
        )
        let response = try await send(envelope: request)
        guard response.status == "ok", let payload = response.payload else {
            if response.error?.code == "method_not_supported" {
                throw EngineConnectionError.methodUnavailable
            }
            throw EngineConnectionError.invalidFrame
        }
        return try MediaOpenGrant(payload: payload)
    }

    public func renderVoice(
        _ request: VoiceRenderControlRequestDTO,
        traceId: String = UUID().uuidString
    ) async throws -> VoiceRenderAcceptedDTO {
        let encoded = try JSONEncoder().encode(request)
        let payload = try JSONDecoder().decode(
            [String: AnyCodableValue].self,
            from: encoded
        )
        let response = try await send(
            envelope: IPCEnvelope(
                kind: "request",
                traceId: traceId,
                requestId: UUID().uuidString,
                method: "voice.render",
                payload: payload
            )
        )
        guard response.status == "ok" else {
            if response.error?.code == "method_not_supported" {
                throw EngineConnectionError.methodUnavailable
            }
            throw EngineConnectionError.invalidFrame
        }
        guard let accepted = try response.decodePayload(
            as: VoiceRenderAcceptedDTO.self
        ),
        accepted.speechUnitId == request.speechUnitId,
        accepted.mediaStreamId == request.mediaStreamId,
        accepted.generation == request.generation,
        accepted.state == "accepted"
        else {
            throw EngineConnectionError.correlationMismatch
        }
        return accepted
    }



    public func loadVoiceDeliveryCursor(
        trackId: String,
        consumerId: String,
        traceId: String = UUID().uuidString
    ) async throws -> VoiceDeliveryCursorDTO? {
        let response = try await send(
            envelope: IPCEnvelope(
                kind: "request",
                traceId: traceId,
                requestId: UUID().uuidString,
                method: "voice.delivery.get",
                payload: [
                    "schema_version": .string("1.0"),
                    "operation": .string("get"),
                    "track_id": .string(trackId),
                    "consumer_id": .string(consumerId),
                ]
            )
        )
        guard response.status == "ok" else {
            if response.error?.code == "method_not_supported" {
                throw EngineConnectionError.methodUnavailable
            }
            throw EngineConnectionError.invalidFrame
        }
        guard let value = try response.decodePayload(
            as: VoiceDeliveryCursorResponseDTO.self
        ), value.schemaVersion == "1.0" else {
            throw EngineConnectionError.invalidFrame
        }
        return value.cursor
    }

    public func updateVoiceDeliveryCursor(
        _ request: VoiceDeliveryCursorUpdateDTO,
        traceId: String = UUID().uuidString
    ) async throws -> VoiceDeliveryCursorDTO {
        let encoded = try JSONEncoder().encode(request)
        let payload = try JSONDecoder().decode(
            [String: AnyCodableValue].self,
            from: encoded
        )
        let response = try await send(
            envelope: IPCEnvelope(
                kind: "request",
                traceId: traceId,
                requestId: UUID().uuidString,
                method: "voice.delivery.update",
                payload: payload
            )
        )
        guard response.status == "ok" else {
            if response.error?.code == "method_not_supported" {
                throw EngineConnectionError.methodUnavailable
            }
            throw EngineConnectionError.invalidFrame
        }
        guard let value = try response.decodePayload(
            as: VoiceDeliveryCursorResponseDTO.self
        ), value.schemaVersion == "1.0", let cursor = value.cursor else {
            throw EngineConnectionError.invalidFrame
        }
        return cursor
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
