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


    /// True only when the Engine advertised the whole sealed-render path.
    ///
    /// Checking all three together matters: `media.open` without `voice.render`
    /// would hand out a grant nothing can serve, and `voice.render` without
    /// `media.open` has nowhere to stream. Reporting "unavailable" is honest
    /// about a voice-less Engine instead of failing mid-turn.
    public var voiceRenderAvailable: Bool {
        guard let capabilities = handshake?.capabilities else { return false }
        return capabilities.isSuperset(of: ["media.open", "voice.render"])
    }

    /// True when the Engine can commit an arbitrary player turn, typed or spoken.
    public var liveTurnAvailable: Bool {
        handshake?.liveTurnAvailable ?? false
    }

    public func supportsStoryPostCommitMethod(
        _ capability: StoryPostCommitMethodCapability
    ) async -> Bool {
        handshake?.capabilities.contains(capability.rawValue) ?? false
    }

    /// Capabilities are negotiated by `system.handshake`; health only reports
    /// readiness and does not advertise methods.
    public func supportsStoryExpression() async -> Bool {
        handshake?.capabilities.contains("story.expression.get") ?? false
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

    // MARK: - Trusted first-turn story surface

    public func storyEntry(
        scenarioId: String = StoryControl.scenarioId,
        traceId: String = UUID().uuidString
    ) async throws -> StoryEntryViewDTO {
        try await storyRequest(
            method: "story.entry.get",
            payload: StoryEntryRequestDTO(scenarioId: scenarioId),
            traceId: traceId
        )
    }

    public func storyOpen(
        openRequestId: String,
        expectedStoreRevision: Int,
        traceId: String = UUID().uuidString
    ) async throws -> StoryOpenViewDTO {
        // The envelope idempotency key must equal the business identity.
        try await storyRequest(
            method: "story.session.open",
            payload: try StorySessionOpenRequestDTO(
                openRequestId: openRequestId,
                expectedStoreRevision: expectedStoreRevision),
            traceId: traceId,
            idempotencyKey: openRequestId
        )
    }

    public func storySession(
        sessionId: String,
        traceId: String = UUID().uuidString
    ) async throws -> StorySessionGetViewDTO {
        try await storyRequest(
            method: "story.session.get",
            payload: try StorySessionGetRequestDTO(sessionId: sessionId),
            traceId: traceId
        )
    }

    public func storySubmit(
        _ request: StoryAdviceSubmitRequestDTO,
        traceId: String = UUID().uuidString
    ) async throws -> StoryAdviceSubmitViewDTO {
        try await storyRequest(
            method: "story.advice.submit",
            payload: request,
            traceId: traceId,
            idempotencyKey: request.inputTurnId
        )
    }

    /// Commit one live player turn. `inputMode` must describe how the text was
    /// produced: a SpeechRail transcript is `.voice`, never `.text`.
    public func storyTurnSubmit(
        _ request: StoryTurnSubmitRequestDTO,
        traceId: String = UUID().uuidString
    ) async throws -> StoryAdviceSubmitViewDTO {
        try await storyRequest(
            method: "story.turn.submit",
            payload: request,
            traceId: traceId,
            idempotencyKey: request.inputTurnId
        )
    }

    public func storyAdviceSubmitV2(
        _ request: StoryAdviceSubmitRequestDTO,
        traceId: String = UUID().uuidString
    ) async throws -> StoryAdviceSubmitViewDTO {
        let method = StoryPostCommitMethodCapability.adviceSubmitV2.rawValue
        guard handshake?.capabilities.contains(method) == true else {
            throw EngineConnectionError.methodUnavailable
        }
        return try await storyRequest(
            method: method,
            payload: request,
            traceId: traceId,
            idempotencyKey: request.inputTurnId
        )
    }

    public func storyTurnSubmitV2(
        _ request: StoryTurnSubmitRequestDTO,
        traceId: String = UUID().uuidString
    ) async throws -> StoryAdviceSubmitViewDTO {
        let method = StoryPostCommitMethodCapability.turnSubmitV2.rawValue
        guard handshake?.capabilities.contains(method) == true else {
            throw EngineConnectionError.methodUnavailable
        }
        return try await storyRequest(
            method: method,
            payload: request,
            traceId: traceId,
            idempotencyKey: request.inputTurnId
        )
    }

    public func storyAdvice(
        sessionId: String,
        inputTurnId: String,
        traceId: String = UUID().uuidString
    ) async throws -> StoryAdviceGetViewDTO {
        try await storyRequest(
            method: "story.advice.get",
            payload: try StoryAdviceGetRequestDTO(
                sessionId: sessionId, inputTurnId: inputTurnId),
            traceId: traceId
        )
    }

    /// Read the persisted, player-disclosed text projection for a committed turn.
    /// The capability check precedes encoding or sending so older Engines are safe.
    public func storyExpressionGet(
        sessionId: String,
        turnId: String,
        traceId: String = UUID().uuidString
    ) async throws -> StoryExpressionGetResponseDTO {
        guard handshake?.capabilities.contains("story.expression.get") == true else {
            throw EngineConnectionError.methodUnavailable
        }
        let request = try StoryExpressionGetRequestDTO(sessionId: sessionId, turnId: turnId)
        let response: StoryExpressionGetResponseDTO = try await storyRequest(
            method: "story.expression.get",
            payload: request,
            traceId: traceId
        )
        guard response.sessionId == sessionId, response.turnId == turnId else {
            throw EngineConnectionError.correlationMismatch
        }
        return response
    }

    /// Read the independent public projections for a committed turn's post-COMMIT work.
    /// Older Engines are checked before the request is encoded or sent.
    public func storyTurnWorkGet(
        sessionId: String,
        turnId: String,
        traceId: String = UUID().uuidString
    ) async throws -> StoryTurnWorkGetResponseDTO {
        let method = StoryPostCommitMethodCapability.turnWorkGet.rawValue
        guard handshake?.capabilities.contains(method) == true else {
            throw EngineConnectionError.methodUnavailable
        }
        let request = try StoryTurnWorkGetRequestDTO(sessionId: sessionId, turnId: turnId)
        let response: StoryTurnWorkGetResponseDTO = try await storyRequest(
            method: method,
            payload: request,
            traceId: traceId
        )
        guard response.sessionId == sessionId, response.turnId == turnId else {
            throw EngineConnectionError.correlationMismatch
        }
        return response
    }

    /// Explicitly retry one eligible post-COMMIT work item using its idempotency identity.
    public func storyTurnWorkRetry(
        sessionId: String,
        turnId: String,
        kind: StoryTurnWorkKind,
        retryRequestId: String,
        traceId: String = UUID().uuidString
    ) async throws -> StoryTurnWorkRetryResponseDTO {
        let method = StoryPostCommitMethodCapability.turnWorkRetry.rawValue
        guard handshake?.capabilities.contains(method) == true else {
            throw EngineConnectionError.methodUnavailable
        }
        let request = try StoryTurnWorkRetryRequestDTO(
            sessionId: sessionId,
            turnId: turnId,
            kind: kind,
            retryRequestId: retryRequestId
        )
        let response: StoryTurnWorkRetryResponseDTO = try await storyRequest(
            method: method,
            payload: request,
            traceId: traceId,
            idempotencyKey: request.retryRequestId
        )
        guard response.sessionId == sessionId,
              response.turnId == turnId,
              response.kind == kind,
              response.retryRequestId == retryRequestId else {
            throw EngineConnectionError.correlationMismatch
        }
        return response
    }

    private func storyRequest<Payload: Encodable, View: Decodable>(
        method: String,
        payload: Payload,
        traceId: String,
        idempotencyKey: String? = nil
    ) async throws -> View {
        let encoded = try JSONEncoder().encode(payload)
        let wire = try JSONDecoder().decode([String: AnyCodableValue].self, from: encoded)
        let response = try await send(
            envelope: IPCEnvelope(
                kind: "request",
                traceId: traceId,
                requestId: UUID().uuidString,
                idempotencyKey: idempotencyKey,
                method: method,
                payload: wire
            )
        )
        guard response.status == "ok" else {
            if response.error?.code == "method_not_supported" {
                throw EngineConnectionError.methodUnavailable
            }
            if let error = response.error {
                throw StoryControlServiceError(code: error.code, retryable: error.retryable)
            }
            throw EngineConnectionError.invalidFrame
        }
        guard let view = try response.decodePayload(as: View.self) else {
            throw EngineConnectionError.invalidFrame
        }
        return view
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

/// `StorySessionModel` depends on this narrow surface; the actor keeps its richer
/// trace-id variants for diagnostics.
extension EngineIPCClient: StoryEngineClient {
    public func storyEntry(scenarioId: String) async throws -> StoryEntryViewDTO {
        try await storyEntry(scenarioId: scenarioId, traceId: UUID().uuidString)
    }

    public func storyOpen(
        openRequestId: String,
        expectedStoreRevision: Int
    ) async throws -> StoryOpenViewDTO {
        try await storyOpen(
            openRequestId: openRequestId,
            expectedStoreRevision: expectedStoreRevision,
            traceId: UUID().uuidString
        )
    }

    public func storySession(sessionId: String) async throws -> StorySessionGetViewDTO {
        try await storySession(sessionId: sessionId, traceId: UUID().uuidString)
    }

    public func storySubmit(
        _ request: StoryAdviceSubmitRequestDTO
    ) async throws -> StoryAdviceSubmitViewDTO {
        try await storySubmit(request, traceId: UUID().uuidString)
    }

    public func storyTurnSubmit(
        _ request: StoryTurnSubmitRequestDTO
    ) async throws -> StoryAdviceSubmitViewDTO {
        try await storyTurnSubmit(request, traceId: UUID().uuidString)
    }

    public func storyAdviceSubmitV2(
        _ request: StoryAdviceSubmitRequestDTO
    ) async throws -> StoryAdviceSubmitViewDTO {
        try await storyAdviceSubmitV2(request, traceId: UUID().uuidString)
    }

    public func storyTurnSubmitV2(
        _ request: StoryTurnSubmitRequestDTO
    ) async throws -> StoryAdviceSubmitViewDTO {
        try await storyTurnSubmitV2(request, traceId: UUID().uuidString)
    }

    public func storyAdvice(
        sessionId: String,
        inputTurnId: String
    ) async throws -> StoryAdviceGetViewDTO {
        try await storyAdvice(
            sessionId: sessionId,
            inputTurnId: inputTurnId,
            traceId: UUID().uuidString
        )
    }

    public func storyTurnWorkGet(
        sessionId: String,
        turnId: String
    ) async throws -> StoryTurnWorkGetResponseDTO {
        try await storyTurnWorkGet(
            sessionId: sessionId,
            turnId: turnId,
            traceId: UUID().uuidString
        )
    }

    public func storyTurnWorkRetry(
        sessionId: String,
        turnId: String,
        kind: StoryTurnWorkKind,
        retryRequestId: String
    ) async throws -> StoryTurnWorkRetryResponseDTO {
        try await storyTurnWorkRetry(
            sessionId: sessionId,
            turnId: turnId,
            kind: kind,
            retryRequestId: retryRequestId,
            traceId: UUID().uuidString
        )
    }
}
