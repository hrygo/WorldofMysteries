import Foundation

/// Strict Swift mirror of
/// `contracts/protocol/story_expression_control.schema.json`.
public nonisolated enum StoryExpressionControlError: Error, Equatable {
    case invalidPayload
}

public nonisolated enum StoryExpressionNarrativeState: String, Codable, Sendable, Equatable {
    case pending
    case ready
    case unavailable
}

public nonisolated enum StoryExpressionSegmentType: String, Codable, Sendable, Equatable {
    case narration
    case character
}

private nonisolated enum StoryExpressionControl {
    static let schemaVersion = "1.0"
    static let maxIdentifier = 256
    static let maxSegmentText = 4096
    static let maxSegments = 256
    static let maxReason = 128

    static func boundedText(_ value: String, maximumLength: Int) throws -> String {
        guard !value.isEmpty,
              value.unicodeScalars.count <= maximumLength,
              value.unicodeScalars.contains(where: { !$0.properties.isWhitespace }),
              !value.unicodeScalars.contains("\u{0}") else {
            throw StoryExpressionControlError.invalidPayload
        }
        return value
    }

    static func identifier(_ value: String, maximumLength: Int = maxIdentifier) throws -> String {
        try boundedText(value, maximumLength: maximumLength)
    }
}

public nonisolated struct StoryExpressionGetRequestDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let sessionId: String
    public let turnId: String

    public init(sessionId: String, turnId: String) throws {
        schemaVersion = StoryExpressionControl.schemaVersion
        self.sessionId = try StoryExpressionControl.identifier(sessionId)
        self.turnId = try StoryExpressionControl.identifier(turnId)
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
            == StoryExpressionControl.schemaVersion else {
            throw StoryExpressionControlError.invalidPayload
        }
        schemaVersion = StoryExpressionControl.schemaVersion
        sessionId = try StoryExpressionControl.identifier(
            container.decode(String.self, forKey: .sessionId)
        )
        turnId = try StoryExpressionControl.identifier(
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

public nonisolated struct StoryExpressionSegmentDTO: Codable, Sendable, Equatable {
    public let type: StoryExpressionSegmentType
    public let speakerDisplayName: String?
    public let text: String

    enum CodingKeys: String, CodingKey {
        case type
        case speakerDisplayName = "speaker_display_name"
        case text
    }

    public init(
        type: StoryExpressionSegmentType,
        speakerDisplayName: String? = nil,
        text: String
    ) throws {
        self.type = type
        if let speakerDisplayName {
            self.speakerDisplayName = try StoryExpressionControl.identifier(speakerDisplayName)
        } else {
            self.speakerDisplayName = nil
        }
        self.text = try StoryExpressionControl.boundedText(
            text,
            maximumLength: StoryExpressionControl.maxSegmentText
        )
        guard type != .narration || speakerDisplayName == nil else {
            throw StoryExpressionControlError.invalidPayload
        }
    }

    public init(from decoder: any Decoder) throws {
        try checkWireKeys(
            decoder,
            allowed: ["type", "speaker_display_name", "text"],
            required: ["type", "text"]
        )
        let container = try decoder.container(keyedBy: CodingKeys.self)
        try self.init(
            type: container.decode(StoryExpressionSegmentType.self, forKey: .type),
            speakerDisplayName: container.decodeIfPresent(String.self, forKey: .speakerDisplayName),
            text: container.decode(String.self, forKey: .text)
        )
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(type, forKey: .type)
        try container.encodeIfPresent(speakerDisplayName, forKey: .speakerDisplayName)
        try container.encode(text, forKey: .text)
    }
}

public nonisolated struct StoryExpressionGetResponseDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let sessionId: String
    public let turnId: String
    public let narrativeState: StoryExpressionNarrativeState
    public let segments: [StoryExpressionSegmentDTO]
    public let reason: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case sessionId = "session_id"
        case turnId = "turn_id"
        case narrativeState = "narrative_state"
        case segments
        case reason
    }

    public init(
        sessionId: String,
        turnId: String,
        narrativeState: StoryExpressionNarrativeState,
        segments: [StoryExpressionSegmentDTO],
        reason: String? = nil
    ) throws {
        schemaVersion = StoryExpressionControl.schemaVersion
        self.sessionId = try StoryExpressionControl.identifier(sessionId)
        self.turnId = try StoryExpressionControl.identifier(turnId)
        self.narrativeState = narrativeState
        self.segments = segments
        self.reason = try reason.map {
            try StoryExpressionControl.identifier(
                $0,
                maximumLength: StoryExpressionControl.maxReason
            )
        }
        try Self.validate(
            narrativeState: narrativeState,
            segments: segments,
            reason: self.reason
        )
    }

    public init(from decoder: any Decoder) throws {
        let required: Set<String> = [
            "schema_version", "session_id", "turn_id", "narrative_state", "segments",
        ]
        try checkWireKeys(
            decoder,
            allowed: required.union(["reason"]),
            required: required
        )
        let container = try decoder.container(keyedBy: CodingKeys.self)
        guard try container.decode(String.self, forKey: .schemaVersion)
            == StoryExpressionControl.schemaVersion else {
            throw StoryExpressionControlError.invalidPayload
        }
        try self.init(
            sessionId: container.decode(String.self, forKey: .sessionId),
            turnId: container.decode(String.self, forKey: .turnId),
            narrativeState: container.decode(
                StoryExpressionNarrativeState.self,
                forKey: .narrativeState
            ),
            segments: container.decode([StoryExpressionSegmentDTO].self, forKey: .segments),
            reason: container.decodeIfPresent(String.self, forKey: .reason)
        )
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(schemaVersion, forKey: .schemaVersion)
        try container.encode(sessionId, forKey: .sessionId)
        try container.encode(turnId, forKey: .turnId)
        try container.encode(narrativeState, forKey: .narrativeState)
        try container.encode(segments, forKey: .segments)
        try container.encodeIfPresent(reason, forKey: .reason)
    }

    private static func validate(
        narrativeState: StoryExpressionNarrativeState,
        segments: [StoryExpressionSegmentDTO],
        reason: String?
    ) throws {
        guard segments.count <= StoryExpressionControl.maxSegments else {
            throw StoryExpressionControlError.invalidPayload
        }
        switch narrativeState {
        case .ready:
            guard !segments.isEmpty, reason == nil else {
                throw StoryExpressionControlError.invalidPayload
            }
        case .pending:
            guard segments.isEmpty, reason == nil else {
                throw StoryExpressionControlError.invalidPayload
            }
        case .unavailable:
            guard segments.isEmpty, reason != nil else {
                throw StoryExpressionControlError.invalidPayload
            }
        }
    }
}
