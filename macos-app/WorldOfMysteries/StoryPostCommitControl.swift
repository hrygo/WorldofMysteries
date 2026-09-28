import Foundation

/// Strict Swift mirror of
/// `contracts/protocol/story_post_commit_control.schema.json`.
public nonisolated enum StoryPostCommitControlError: Error, Equatable {
    case invalidPayload
}

public nonisolated enum StoryTurnSettlementState: String, Codable, Sendable, Equatable, CaseIterable {
    case notRequired = "not_required"
    case pending
    case running
    case blocked
    case succeeded
}

public nonisolated enum StoryTurnNarrativeState: String, Codable, Sendable, Equatable, CaseIterable {
    case pending
    case running
    case blocked
    case ready
}

public nonisolated enum StoryTurnAudioState: String, Codable, Sendable, Equatable, CaseIterable {
    case pending
    case running
    case unavailable
    case ready
}

public nonisolated enum StoryTurnWorkKind: String, Codable, Sendable, Equatable, CaseIterable {
    case episodeFinalize = "episode_finalize"
    case narrativePublish = "narrative_publish"
    case audioPrepare = "audio_prepare"
}

/// Story methods advertised by the Engine's `story_post_commit_method_capability`.
public nonisolated enum StoryPostCommitMethodCapability: String, Sendable, Equatable, CaseIterable {
    case adviceSubmitV2 = "story.advice.submit.v2"
    case turnSubmitV2 = "story.turn.submit.v2"
    case turnWorkGet = "story.turn.work.get"
    case turnWorkRetry = "story.turn.work.retry"
}

private nonisolated enum StoryPostCommitControl {
    static let schemaVersion = "1.0"
    static let maxIdentifier = 256
    static let maxReason = 128
    static let maxSegments = 256

    static func identifier(_ value: String) throws -> String {
        guard !value.isEmpty,
              value.unicodeScalars.count <= maxIdentifier,
              value.unicodeScalars.contains(where: { !$0.properties.isWhitespace }),
              !value.unicodeScalars.contains("\u{0}") else {
            throw StoryPostCommitControlError.invalidPayload
        }
        return value
    }

    /// Public reasons are stable lowercase tokens, never provider or runtime diagnostics.
    /// This validates the schema's stable-code semantic without freezing its code set.
    static func reason(_ value: String) throws -> String {
        guard !value.isEmpty,
              value.unicodeScalars.count <= maxReason,
              let first = value.unicodeScalars.first,
              isLowercaseASCII(first.value),
              value.unicodeScalars.allSatisfy({
                  isLowercaseASCII($0.value) || isDigitASCII($0.value) || $0.value == 0x5F
              }),
              !value.hasSuffix("_"),
              !value.contains("__") else {
            throw StoryPostCommitControlError.invalidPayload
        }
        return value
    }

    private static func isLowercaseASCII(_ scalar: UInt32) -> Bool {
        (0x61...0x7A).contains(scalar)
    }

    private static func isDigitASCII(_ scalar: UInt32) -> Bool {
        (0x30...0x39).contains(scalar)
    }
}

public nonisolated struct StoryTurnWorkGetRequestDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let sessionId: String
    public let turnId: String

    public init(sessionId: String, turnId: String) throws {
        schemaVersion = StoryPostCommitControl.schemaVersion
        self.sessionId = try StoryPostCommitControl.identifier(sessionId)
        self.turnId = try StoryPostCommitControl.identifier(turnId)
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case sessionId = "session_id"
        case turnId = "turn_id"
    }

    public init(from decoder: any Decoder) throws {
        try checkWireKeys(
            decoder,
            allowed: ["schema_version", "session_id", "turn_id"],
            required: ["schema_version", "session_id", "turn_id"]
        )
        let container = try decoder.container(keyedBy: CodingKeys.self)
        guard try container.decode(String.self, forKey: .schemaVersion)
            == StoryPostCommitControl.schemaVersion else {
            throw StoryPostCommitControlError.invalidPayload
        }
        schemaVersion = StoryPostCommitControl.schemaVersion
        sessionId = try StoryPostCommitControl.identifier(
            container.decode(String.self, forKey: .sessionId)
        )
        turnId = try StoryPostCommitControl.identifier(
            container.decode(String.self, forKey: .turnId)
        )
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(schemaVersion, forKey: .schemaVersion)
        try container.encode(sessionId, forKey: .sessionId)
        try container.encode(turnId, forKey: .turnId)
    }
}

public nonisolated struct StoryTurnWorkRetryRequestDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let sessionId: String
    public let turnId: String
    public let kind: StoryTurnWorkKind
    public let retryRequestId: String

    public init(
        sessionId: String,
        turnId: String,
        kind: StoryTurnWorkKind,
        retryRequestId: String
    ) throws {
        schemaVersion = StoryPostCommitControl.schemaVersion
        self.sessionId = try StoryPostCommitControl.identifier(sessionId)
        self.turnId = try StoryPostCommitControl.identifier(turnId)
        self.kind = kind
        self.retryRequestId = try StoryPostCommitControl.identifier(retryRequestId)
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case sessionId = "session_id"
        case turnId = "turn_id"
        case kind
        case retryRequestId = "retry_request_id"
    }

    public init(from decoder: any Decoder) throws {
        try checkWireKeys(
            decoder,
            allowed: ["schema_version", "session_id", "turn_id", "kind", "retry_request_id"],
            required: ["schema_version", "session_id", "turn_id", "kind", "retry_request_id"]
        )
        let container = try decoder.container(keyedBy: CodingKeys.self)
        guard try container.decode(String.self, forKey: .schemaVersion)
            == StoryPostCommitControl.schemaVersion else {
            throw StoryPostCommitControlError.invalidPayload
        }
        try self.init(
            sessionId: container.decode(String.self, forKey: .sessionId),
            turnId: container.decode(String.self, forKey: .turnId),
            kind: container.decode(StoryTurnWorkKind.self, forKey: .kind),
            retryRequestId: container.decode(String.self, forKey: .retryRequestId)
        )
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(schemaVersion, forKey: .schemaVersion)
        try container.encode(sessionId, forKey: .sessionId)
        try container.encode(turnId, forKey: .turnId)
        try container.encode(kind, forKey: .kind)
        try container.encode(retryRequestId, forKey: .retryRequestId)
    }
}

public nonisolated struct StoryTurnWorkGetResponseDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let sessionId: String
    public let turnId: String
    public let settlementState: StoryTurnSettlementState
    public let settlementReason: String?
    public let narrativeState: StoryTurnNarrativeState
    public let narrativeSegments: [StoryExpressionSegmentDTO]
    public let narrativeReason: String?
    public let audioState: StoryTurnAudioState
    public let audioReason: String?
    public let delivery: StoryTurnDeliveryDTO?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case sessionId = "session_id"
        case turnId = "turn_id"
        case settlementState = "settlement_state"
        case settlementReason = "settlement_reason"
        case narrativeState = "narrative_state"
        case narrativeSegments = "narrative_segments"
        case narrativeReason = "narrative_reason"
        case audioState = "audio_state"
        case audioReason = "audio_reason"
        case delivery
    }

    public init(
        sessionId: String,
        turnId: String,
        settlementState: StoryTurnSettlementState,
        settlementReason: String? = nil,
        narrativeState: StoryTurnNarrativeState,
        narrativeSegments: [StoryExpressionSegmentDTO],
        narrativeReason: String? = nil,
        audioState: StoryTurnAudioState,
        audioReason: String? = nil,
        delivery: StoryTurnDeliveryDTO? = nil
    ) throws {
        schemaVersion = StoryPostCommitControl.schemaVersion
        self.sessionId = try StoryPostCommitControl.identifier(sessionId)
        self.turnId = try StoryPostCommitControl.identifier(turnId)
        self.settlementState = settlementState
        self.settlementReason = try settlementReason.map(StoryPostCommitControl.reason)
        self.narrativeState = narrativeState
        guard narrativeSegments.count <= StoryPostCommitControl.maxSegments else {
            throw StoryPostCommitControlError.invalidPayload
        }
        self.narrativeSegments = narrativeSegments
        self.narrativeReason = try narrativeReason.map(StoryPostCommitControl.reason)
        self.audioState = audioState
        self.audioReason = try audioReason.map(StoryPostCommitControl.reason)
        self.delivery = delivery
        try Self.validate(
            settlementState: settlementState,
            settlementReason: self.settlementReason,
            narrativeState: narrativeState,
            narrativeSegments: narrativeSegments,
            narrativeReason: self.narrativeReason,
            audioState: audioState,
            audioReason: self.audioReason,
            delivery: delivery
        )
    }

    public init(from decoder: any Decoder) throws {
        let required: Set<String> = [
            "schema_version", "session_id", "turn_id", "settlement_state",
            "narrative_state", "narrative_segments", "audio_state",
        ]
        try checkWireKeys(
            decoder,
            allowed: required.union([
                "settlement_reason", "narrative_reason", "audio_reason", "delivery",
            ]),
            required: required
        )
        let container = try decoder.container(keyedBy: CodingKeys.self)
        guard try container.decode(String.self, forKey: .schemaVersion)
            == StoryPostCommitControl.schemaVersion else {
            throw StoryPostCommitControlError.invalidPayload
        }
        try self.init(
            sessionId: container.decode(String.self, forKey: .sessionId),
            turnId: container.decode(String.self, forKey: .turnId),
            settlementState: container.decode(
                StoryTurnSettlementState.self,
                forKey: .settlementState
            ),
            settlementReason: container.decodeIfPresent(String.self, forKey: .settlementReason),
            narrativeState: container.decode(
                StoryTurnNarrativeState.self,
                forKey: .narrativeState
            ),
            narrativeSegments: container.decode(
                [StoryExpressionSegmentDTO].self,
                forKey: .narrativeSegments
            ),
            narrativeReason: container.decodeIfPresent(String.self, forKey: .narrativeReason),
            audioState: container.decode(StoryTurnAudioState.self, forKey: .audioState),
            audioReason: container.decodeIfPresent(String.self, forKey: .audioReason),
            delivery: container.decodeIfPresent(StoryTurnDeliveryDTO.self, forKey: .delivery)
        )
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(schemaVersion, forKey: .schemaVersion)
        try container.encode(sessionId, forKey: .sessionId)
        try container.encode(turnId, forKey: .turnId)
        try container.encode(settlementState, forKey: .settlementState)
        try container.encodeIfPresent(settlementReason, forKey: .settlementReason)
        try container.encode(narrativeState, forKey: .narrativeState)
        try container.encode(narrativeSegments, forKey: .narrativeSegments)
        try container.encodeIfPresent(narrativeReason, forKey: .narrativeReason)
        try container.encode(audioState, forKey: .audioState)
        try container.encodeIfPresent(audioReason, forKey: .audioReason)
        try container.encodeIfPresent(delivery, forKey: .delivery)
    }

    private static func validate(
        settlementState: StoryTurnSettlementState,
        settlementReason: String?,
        narrativeState: StoryTurnNarrativeState,
        narrativeSegments: [StoryExpressionSegmentDTO],
        narrativeReason: String?,
        audioState: StoryTurnAudioState,
        audioReason: String?,
        delivery: StoryTurnDeliveryDTO?
    ) throws {
        switch settlementState {
        case .blocked:
            guard settlementReason != nil else {
                throw StoryPostCommitControlError.invalidPayload
            }
        case .notRequired, .pending, .running, .succeeded:
            guard settlementReason == nil else {
                throw StoryPostCommitControlError.invalidPayload
            }
        }

        switch narrativeState {
        case .ready:
            guard !narrativeSegments.isEmpty, narrativeReason == nil else {
                throw StoryPostCommitControlError.invalidPayload
            }
        case .blocked:
            guard narrativeSegments.isEmpty, narrativeReason != nil else {
                throw StoryPostCommitControlError.invalidPayload
            }
        case .pending, .running:
            guard narrativeSegments.isEmpty, narrativeReason == nil else {
                throw StoryPostCommitControlError.invalidPayload
            }
        }

        switch audioState {
        case .pending, .running:
            guard audioReason == nil, delivery == nil else {
                throw StoryPostCommitControlError.invalidPayload
            }
        case .unavailable:
            guard audioReason != nil, delivery == nil else {
                throw StoryPostCommitControlError.invalidPayload
            }
        case .ready:
            guard audioReason == nil, delivery?.state == .ready else {
                throw StoryPostCommitControlError.invalidPayload
            }
            if let deliveryReason = delivery?.reason {
                _ = try StoryPostCommitControl.reason(deliveryReason)
            }
        }
    }
}

public nonisolated struct StoryTurnWorkRetryResponseDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let sessionId: String
    public let turnId: String
    public let kind: StoryTurnWorkKind
    public let retryRequestId: String
    public let accepted: Bool
    public let replayed: Bool

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case sessionId = "session_id"
        case turnId = "turn_id"
        case kind
        case retryRequestId = "retry_request_id"
        case accepted
        case replayed
    }

    public init(
        sessionId: String,
        turnId: String,
        kind: StoryTurnWorkKind,
        retryRequestId: String,
        replayed: Bool
    ) throws {
        schemaVersion = StoryPostCommitControl.schemaVersion
        self.sessionId = try StoryPostCommitControl.identifier(sessionId)
        self.turnId = try StoryPostCommitControl.identifier(turnId)
        self.kind = kind
        self.retryRequestId = try StoryPostCommitControl.identifier(retryRequestId)
        accepted = true
        self.replayed = replayed
    }

    public init(from decoder: any Decoder) throws {
        try checkWireKeys(
            decoder,
            allowed: [
                "schema_version", "session_id", "turn_id", "kind",
                "retry_request_id", "accepted", "replayed",
            ],
            required: [
                "schema_version", "session_id", "turn_id", "kind",
                "retry_request_id", "accepted", "replayed",
            ]
        )
        let container = try decoder.container(keyedBy: CodingKeys.self)
        guard try container.decode(String.self, forKey: .schemaVersion)
                == StoryPostCommitControl.schemaVersion,
              try container.decode(Bool.self, forKey: .accepted) else {
            throw StoryPostCommitControlError.invalidPayload
        }
        try self.init(
            sessionId: container.decode(String.self, forKey: .sessionId),
            turnId: container.decode(String.self, forKey: .turnId),
            kind: container.decode(StoryTurnWorkKind.self, forKey: .kind),
            retryRequestId: container.decode(String.self, forKey: .retryRequestId),
            replayed: container.decode(Bool.self, forKey: .replayed)
        )
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(schemaVersion, forKey: .schemaVersion)
        try container.encode(sessionId, forKey: .sessionId)
        try container.encode(turnId, forKey: .turnId)
        try container.encode(kind, forKey: .kind)
        try container.encode(retryRequestId, forKey: .retryRequestId)
        try container.encode(accepted, forKey: .accepted)
        try container.encode(replayed, forKey: .replayed)
    }
}
