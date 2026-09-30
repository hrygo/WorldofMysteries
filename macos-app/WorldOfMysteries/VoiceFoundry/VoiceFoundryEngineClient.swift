import Foundation

/// A refusal from the Voice Foundry control surface, in the engine's own words.
///
/// The code is carried through rather than flattened into "something failed",
/// because the codes are the only thing that distinguishes "this voice has not
/// been cast yet" from "the audio drifted and must be re-read" from "a person
/// has to choose a candidate" — and a UI that cannot tell those apart can only
/// show the user a shrug.
public nonisolated struct VoiceFoundryServiceError: Error, Equatable, Sendable {
    public let code: String
    public let retryable: Bool
}

/// The narrow surface the audition UI depends on.
public protocol VoiceFoundryEngineClient: Sendable {
    func voiceFoundryTask(_ taskId: String) async throws -> VoiceFoundryGetResponseDTO
    func voiceFoundryList(
        pageSize: Int,
        stage: String?,
        pageToken: String?
    ) async throws -> VoiceFoundryListResponseDTO
    func voiceFoundryAsset(
        taskId: String,
        candidateId: String,
        kind: VoiceFoundryAssetKind
    ) async throws -> VoiceFoundryAssetResponseDTO
    func voiceFoundryCommand<Payload: Codable & Sendable>(
        _ command: VoiceFoundryCommandDTO<Payload>
    ) async throws -> VoiceFoundryCommandResponseDTO
}

extension EngineIPCClient {
    /// Voice Foundry methods are optional handshake capabilities. Asking before
    /// the handshake has landed would report every method as unsupported and
    /// send a user hunting for a setting that does not exist.
    public func supportsVoiceFoundryMethod(_ method: String) async -> Bool {
        handshake?.capabilities.contains(method) ?? false
    }

    public func voiceFoundryTask(
        _ taskId: String,
        traceId: String = UUID().uuidString
    ) async throws -> VoiceFoundryGetResponseDTO {
        let payload: [String: AnyCodableValue] = [
            "schema_version": .string("1.0"),
            "task_id": .string(taskId),
        ]
        return try await voiceFoundryRequest(
            method: "voice.foundry.get",
            payload: payload,
            traceId: traceId
        )
    }

    public func voiceFoundryList(
        pageSize: Int = 50,
        stage: String? = nil,
        pageToken: String? = nil,
        traceId: String = UUID().uuidString
    ) async throws -> VoiceFoundryListResponseDTO {
        var payload: [String: AnyCodableValue] = [
            "schema_version": .string("1.0"),
            "page_size": .int(pageSize),
        ]
        if let stage { payload["stage"] = .string(stage) }
        if let pageToken { payload["page_token"] = .string(pageToken) }
        return try await voiceFoundryRequest(
            method: "voice.foundry.list",
            payload: payload,
            traceId: traceId
        )
    }

    public func voiceFoundryAsset(
        taskId: String,
        candidateId: String,
        kind: VoiceFoundryAssetKind,
        traceId: String = UUID().uuidString
    ) async throws -> VoiceFoundryAssetResponseDTO {
        let payload: [String: AnyCodableValue] = [
            "schema_version": .string("1.0"),
            "task_id": .string(taskId),
            "candidate_id": .string(candidateId),
            "kind": .string(kind.rawValue),
        ]
        return try await voiceFoundryRequest(
            method: "voice.foundry.asset.get",
            payload: payload,
            traceId: traceId
        )
    }

    public func voiceFoundryCommand<Payload: Codable & Sendable>(
        _ command: VoiceFoundryCommandDTO<Payload>,
        traceId: String = UUID().uuidString
    ) async throws -> VoiceFoundryCommandResponseDTO {
        let encoded = try JSONEncoder().encode(command)
        let wire = try JSONDecoder().decode([String: AnyCodableValue].self, from: encoded)
        return try await voiceFoundryRequest(
            method: "voice.foundry.\(command.action)",
            payload: wire,
            traceId: traceId,
            // The command id is the idempotency key the engine replays on, so a
            // retry after a dropped connection must present the same one. The
            // envelope key is the business identity, not a fresh UUID.
            idempotencyKey: command.commandId
        )
    }

    private func voiceFoundryRequest<View: Decodable>(
        method: String,
        payload: [String: AnyCodableValue],
        traceId: String,
        idempotencyKey: String? = nil
    ) async throws -> View {
        let response = try await send(
            envelope: IPCEnvelope(
                kind: "request",
                traceId: traceId,
                requestId: UUID().uuidString,
                idempotencyKey: idempotencyKey,
                method: method,
                payload: payload
            )
        )
        guard response.status == "ok" else {
            if response.error?.code == "method_not_supported" {
                throw EngineConnectionError.methodUnavailable
            }
            if let error = response.error {
                throw VoiceFoundryServiceError(
                    code: error.code,
                    retryable: error.retryable
                )
            }
            throw EngineConnectionError.invalidFrame
        }
        guard let view = try response.decodePayload(as: View.self) else {
            throw EngineConnectionError.invalidFrame
        }
        return view
    }
}

extension EngineIPCClient: VoiceFoundryEngineClient {
    public func voiceFoundryTask(_ taskId: String) async throws -> VoiceFoundryGetResponseDTO {
        try await voiceFoundryTask(taskId, traceId: UUID().uuidString)
    }

    public func voiceFoundryList(
        pageSize: Int,
        stage: String?,
        pageToken: String?
    ) async throws -> VoiceFoundryListResponseDTO {
        try await voiceFoundryList(
            pageSize: pageSize,
            stage: stage,
            pageToken: pageToken,
            traceId: UUID().uuidString
        )
    }

    public func voiceFoundryAsset(
        taskId: String,
        candidateId: String,
        kind: VoiceFoundryAssetKind
    ) async throws -> VoiceFoundryAssetResponseDTO {
        try await voiceFoundryAsset(
            taskId: taskId,
            candidateId: candidateId,
            kind: kind,
            traceId: UUID().uuidString
        )
    }

    public func voiceFoundryCommand<Payload: Codable & Sendable>(
        _ command: VoiceFoundryCommandDTO<Payload>
    ) async throws -> VoiceFoundryCommandResponseDTO {
        try await voiceFoundryCommand(command, traceId: UUID().uuidString)
    }
}
