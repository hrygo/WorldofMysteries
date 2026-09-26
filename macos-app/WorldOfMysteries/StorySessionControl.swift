import Foundation

/// Trusted first-turn wire DTOs mirrored from
/// `contracts/protocol/story_session_control.schema.json`.
///
/// JSON Schema owns the wire shape; these types additionally reject unknown keys,
/// unexpected nulls and identity/revision mismatches before any service call.
public nonisolated enum StoryControlError: Error, Equatable {
    case invalidPayload
}

public nonisolated enum StoryControl {
    public static let schemaVersion = "1.0"
    public static let scenarioId = "golden_001"
    public static let mode = "golden_deterministic"
    public static let maxIdentifier = 256
    public static let maxRawInput = 16_384
    public static let maxRevision = 9_223_372_036_854_775_807
    public static let maxExpectedRevision = 9_223_372_036_854_775_806

    static func identifier(_ value: String, maxLength: Int = maxIdentifier) throws -> String {
        let scalars = value.unicodeScalars
        guard !value.isEmpty, value.utf8.count <= maxLength,
              scalars.contains(where: { !$0.properties.isWhitespace }),
              !value.unicodeScalars.contains("\u{0}") else {
            throw StoryControlError.invalidPayload
        }
        return value
    }

    static func rawInput(_ value: String) throws -> String {
        let scalars = value.unicodeScalars
        guard !value.isEmpty, value.utf8.count <= maxRawInput,
              scalars.contains(where: { !$0.properties.isWhitespace }),
              !value.unicodeScalars.contains("\u{0}") else {
            throw StoryControlError.invalidPayload
        }
        return value
    }

    static func revision(_ value: Int, expected: Bool = false) throws -> Int {
        guard value >= 0, value <= (expected ? maxExpectedRevision : maxRevision) else {
            throw StoryControlError.invalidPayload
        }
        return value
    }

    static func schema(_ value: String) throws -> String {
        guard value == schemaVersion else { throw StoryControlError.invalidPayload }
        return value
    }

    static func scenario(_ value: String) throws -> String {
        guard value == scenarioId else { throw StoryControlError.invalidPayload }
        return value
    }
}

// MARK: - Requests

public nonisolated struct StoryEntryRequestDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let scenarioId: String

    public init(scenarioId: String = StoryControl.scenarioId) {
        self.schemaVersion = StoryControl.schemaVersion
        self.scenarioId = scenarioId
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case scenarioId = "scenario_id"
    }

    public init(from decoder: any Decoder) throws {
        try checkWireKeys(decoder, allowed: ["schema_version", "scenario_id"],
                          required: ["schema_version", "scenario_id"])
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try StoryControl.schema(container.decode(String.self, forKey: .schemaVersion))
        scenarioId = try StoryControl.scenario(container.decode(String.self, forKey: .scenarioId))
    }
}

public nonisolated struct StorySessionOpenRequestDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let scenarioId: String
    public let openRequestId: String
    public let expectedStoreRevision: Int

    public init(openRequestId: String, expectedStoreRevision: Int) throws {
        self.schemaVersion = StoryControl.schemaVersion
        self.scenarioId = StoryControl.scenarioId
        self.openRequestId = try StoryControl.identifier(openRequestId)
        self.expectedStoreRevision = try StoryControl.revision(expectedStoreRevision, expected: true)
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case scenarioId = "scenario_id"
        case openRequestId = "open_request_id"
        case expectedStoreRevision = "expected_store_revision"
    }

    public init(from decoder: any Decoder) throws {
        try checkWireKeys(decoder, allowed: ["schema_version", "scenario_id", "open_request_id",
                                             "expected_store_revision"],
                          required: ["schema_version", "scenario_id", "open_request_id",
                                     "expected_store_revision"])
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try StoryControl.schema(container.decode(String.self, forKey: .schemaVersion))
        scenarioId = try StoryControl.scenario(container.decode(String.self, forKey: .scenarioId))
        openRequestId = try StoryControl.identifier(container.decode(String.self, forKey: .openRequestId))
        expectedStoreRevision = try StoryControl.revision(
            container.decode(Int.self, forKey: .expectedStoreRevision), expected: true)
    }
}

public nonisolated struct StorySessionGetRequestDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let sessionId: String

    public init(sessionId: String) throws {
        self.schemaVersion = StoryControl.schemaVersion
        self.sessionId = try StoryControl.identifier(sessionId)
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case sessionId = "session_id"
    }

    public init(from decoder: any Decoder) throws {
        try checkWireKeys(decoder, allowed: ["schema_version", "session_id"],
                          required: ["schema_version", "session_id"])
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try StoryControl.schema(container.decode(String.self, forKey: .schemaVersion))
        sessionId = try StoryControl.identifier(container.decode(String.self, forKey: .sessionId))
    }
}

public nonisolated struct StoryAdviceSubmitRequestDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let sessionId: String
    public let inputTurnId: String
    public let rawInput: String
    public let expectedStoryRevision: Int
    public let expectedStoreRevision: Int

    public init(
        sessionId: String,
        inputTurnId: String,
        rawInput: String,
        expectedStoryRevision: Int,
        expectedStoreRevision: Int
    ) throws {
        self.schemaVersion = StoryControl.schemaVersion
        self.sessionId = try StoryControl.identifier(sessionId)
        self.inputTurnId = try StoryControl.identifier(inputTurnId)
        self.rawInput = try StoryControl.rawInput(rawInput)
        self.expectedStoryRevision = try StoryControl.revision(expectedStoryRevision, expected: true)
        self.expectedStoreRevision = try StoryControl.revision(expectedStoreRevision, expected: true)
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case sessionId = "session_id"
        case inputTurnId = "input_turn_id"
        case rawInput = "raw_input"
        case expectedStoryRevision = "expected_story_revision"
        case expectedStoreRevision = "expected_store_revision"
    }

    public init(from decoder: any Decoder) throws {
        try checkWireKeys(decoder, allowed: ["schema_version", "session_id", "input_turn_id",
                                             "raw_input", "expected_story_revision",
                                             "expected_store_revision"],
                          required: ["schema_version", "session_id", "input_turn_id",
                                     "raw_input", "expected_story_revision",
                                     "expected_store_revision"])
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try StoryControl.schema(container.decode(String.self, forKey: .schemaVersion))
        sessionId = try StoryControl.identifier(container.decode(String.self, forKey: .sessionId))
        inputTurnId = try StoryControl.identifier(container.decode(String.self, forKey: .inputTurnId))
        rawInput = try StoryControl.rawInput(container.decode(String.self, forKey: .rawInput))
        expectedStoryRevision = try StoryControl.revision(
            container.decode(Int.self, forKey: .expectedStoryRevision), expected: true)
        expectedStoreRevision = try StoryControl.revision(
            container.decode(Int.self, forKey: .expectedStoreRevision), expected: true)
    }
}

public nonisolated struct StoryAdviceGetRequestDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let sessionId: String
    public let inputTurnId: String

    public init(sessionId: String, inputTurnId: String) throws {
        self.schemaVersion = StoryControl.schemaVersion
        self.sessionId = try StoryControl.identifier(sessionId)
        self.inputTurnId = try StoryControl.identifier(inputTurnId)
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case sessionId = "session_id"
        case inputTurnId = "input_turn_id"
    }

    public init(from decoder: any Decoder) throws {
        try checkWireKeys(decoder, allowed: ["schema_version", "session_id", "input_turn_id"],
                          required: ["schema_version", "session_id", "input_turn_id"])
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try StoryControl.schema(container.decode(String.self, forKey: .schemaVersion))
        sessionId = try StoryControl.identifier(container.decode(String.self, forKey: .sessionId))
        inputTurnId = try StoryControl.identifier(container.decode(String.self, forKey: .inputTurnId))
    }
}

// MARK: - Responses

public nonisolated struct StoryActorViewDTO: Codable, Sendable, Equatable {
    public let id: String
    public let displayName: String

    init(wire: (id: String, displayName: String)) throws {
        self.id = try StoryControl.identifier(wire.id)
        self.displayName = try StoryControl.identifier(wire.displayName)
    }

    enum CodingKeys: String, CodingKey {
        case id
        case displayName = "display_name"
    }

    public init(from decoder: any Decoder) throws {
        try checkWireKeys(decoder, allowed: ["id", "display_name"], required: ["id", "display_name"])
        let container = try decoder.container(keyedBy: CodingKeys.self)
        try self.init(wire: (container.decode(String.self, forKey: .id),
                             container.decode(String.self, forKey: .displayName)))
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(displayName, forKey: .displayName)
    }
}

public nonisolated struct StorySceneViewDTO: Codable, Sendable, Equatable {
    public let id: String
    public let locationId: String
    public let displayName: String

    enum CodingKeys: String, CodingKey {
        case id
        case locationId = "location_id"
        case displayName = "display_name"
    }

    public init(from decoder: any Decoder) throws {
        try checkWireKeys(decoder, allowed: ["id", "location_id", "display_name"],
                          required: ["id", "location_id", "display_name"])
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try StoryControl.identifier(container.decode(String.self, forKey: .id))
        locationId = try StoryControl.identifier(container.decode(String.self, forKey: .locationId))
        displayName = try StoryControl.identifier(container.decode(String.self, forKey: .displayName))
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(locationId, forKey: .locationId)
        try container.encode(displayName, forKey: .displayName)
    }
}

public nonisolated struct StoryClueViewDTO: Codable, Sendable, Equatable {
    public let id: String
    public let displayName: String

    enum CodingKeys: String, CodingKey {
        case id
        case displayName = "display_name"
    }

    public init(from decoder: any Decoder) throws {
        try checkWireKeys(decoder, allowed: ["id", "display_name"], required: ["id", "display_name"])
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try StoryControl.identifier(container.decode(String.self, forKey: .id))
        displayName = try StoryControl.identifier(container.decode(String.self, forKey: .displayName))
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(displayName, forKey: .displayName)
    }
}

public nonisolated struct StoryPublicViewDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let scenarioId: String
    public let sessionId: String
    public let mode: String
    public let status: String
    public let storyRevision: Int
    public let turn: Int
    public let observedStoreRevision: Int
    public let worldTime: String
    public let protagonist: StoryActorViewDTO
    public let scene: StorySceneViewDTO
    public let discoveredClues: [StoryClueViewDTO]
    public let canSubmit: Bool
    public let lastCommittedTurnId: String?

    public static let statuses: Set<String> = [
        "active", "suspended", "closing", "finalized", "cancelled", "recovery_required",
    ]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case scenarioId = "scenario_id"
        case sessionId = "session_id"
        case mode, status
        case storyRevision = "story_revision"
        case turn
        case observedStoreRevision = "observed_store_revision"
        case worldTime = "world_time"
        case protagonist, scene
        case discoveredClues = "discovered_clues"
        case canSubmit = "can_submit"
        case lastCommittedTurnId = "last_committed_turn_id"
    }

    public init(from decoder: any Decoder) throws {
        let required: Set<String> = [
            "schema_version", "scenario_id", "session_id", "mode", "status",
            "story_revision", "turn", "observed_store_revision", "world_time",
            "protagonist", "scene", "discovered_clues", "can_submit",
        ]
        try checkWireKeys(decoder, allowed: required.union(["last_committed_turn_id"]),
                          required: required)
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try StoryControl.schema(container.decode(String.self, forKey: .schemaVersion))
        scenarioId = try StoryControl.scenario(container.decode(String.self, forKey: .scenarioId))
        sessionId = try StoryControl.identifier(container.decode(String.self, forKey: .sessionId))
        mode = try container.decode(String.self, forKey: .mode)
        guard mode == StoryControl.mode else { throw StoryControlError.invalidPayload }
        status = try container.decode(String.self, forKey: .status)
        guard Self.statuses.contains(status) else { throw StoryControlError.invalidPayload }
        storyRevision = try StoryControl.revision(container.decode(Int.self, forKey: .storyRevision))
        turn = try StoryControl.revision(container.decode(Int.self, forKey: .turn))
        observedStoreRevision = try StoryControl.revision(
            container.decode(Int.self, forKey: .observedStoreRevision))
        worldTime = try StoryControl.identifier(container.decode(String.self, forKey: .worldTime), maxLength: 128)
        protagonist = try container.decode(StoryActorViewDTO.self, forKey: .protagonist)
        scene = try container.decode(StorySceneViewDTO.self, forKey: .scene)
        discoveredClues = try container.decode([StoryClueViewDTO].self, forKey: .discoveredClues)
        canSubmit = try container.decode(Bool.self, forKey: .canSubmit)
        if let raw = try container.decodeIfPresent(String.self, forKey: .lastCommittedTurnId) {
            lastCommittedTurnId = try StoryControl.identifier(raw)
        } else {
            lastCommittedTurnId = nil
        }
        guard discoveredClues.count <= 128 else { throw StoryControlError.invalidPayload }
        guard turn == storyRevision else { throw StoryControlError.invalidPayload }
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(schemaVersion, forKey: .schemaVersion)
        try container.encode(scenarioId, forKey: .scenarioId)
        try container.encode(sessionId, forKey: .sessionId)
        try container.encode(mode, forKey: .mode)
        try container.encode(status, forKey: .status)
        try container.encode(storyRevision, forKey: .storyRevision)
        try container.encode(turn, forKey: .turn)
        try container.encode(observedStoreRevision, forKey: .observedStoreRevision)
        try container.encode(worldTime, forKey: .worldTime)
        try container.encode(protagonist, forKey: .protagonist)
        try container.encode(scene, forKey: .scene)
        try container.encode(discoveredClues, forKey: .discoveredClues)
        try container.encode(canSubmit, forKey: .canSubmit)
        try container.encodeIfPresent(lastCommittedTurnId, forKey: .lastCommittedTurnId)
    }

    /// Only a committed turn advances the durable story revision.
    public var isFirstTurnCommitted: Bool { turn > 0 && status == "active" }
}

public nonisolated struct StoryEntryViewDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let scenarioId: String
    public let mode: String
    public let supportedAdvice: [String]
    public let observedStoreRevision: Int
    public let session: StoryPublicViewDTO?
    public let pendingInputTurnId: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case scenarioId = "scenario_id"
        case mode
        case supportedAdvice = "supported_advice"
        case observedStoreRevision = "observed_store_revision"
        case session
        case pendingInputTurnId = "pending_input_turn_id"
    }

    public init(from decoder: any Decoder) throws {
        let required: Set<String> = ["schema_version", "scenario_id", "mode", "supported_advice",
                                     "observed_store_revision"]
        try checkWireKeys(decoder, allowed: required.union(["session", "pending_input_turn_id"]),
                          required: required)
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try StoryControl.schema(container.decode(String.self, forKey: .schemaVersion))
        scenarioId = try StoryControl.scenario(container.decode(String.self, forKey: .scenarioId))
        mode = try container.decode(String.self, forKey: .mode)
        guard mode == StoryControl.mode else { throw StoryControlError.invalidPayload }
        supportedAdvice = try container.decode([String].self, forKey: .supportedAdvice)
        guard !supportedAdvice.isEmpty, supportedAdvice.count <= 8 else {
            throw StoryControlError.invalidPayload
        }
        for advice in supportedAdvice { _ = try StoryControl.rawInput(advice) }
        observedStoreRevision = try StoryControl.revision(
            container.decode(Int.self, forKey: .observedStoreRevision))
        session = try container.decodeIfPresent(StoryPublicViewDTO.self, forKey: .session)
        if let raw = try container.decodeIfPresent(String.self, forKey: .pendingInputTurnId) {
            pendingInputTurnId = try StoryControl.identifier(raw)
        } else {
            pendingInputTurnId = nil
        }
        if let session, session.scenarioId != scenarioId {
            throw StoryControlError.invalidPayload
        }
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(schemaVersion, forKey: .schemaVersion)
        try container.encode(scenarioId, forKey: .scenarioId)
        try container.encode(mode, forKey: .mode)
        try container.encode(supportedAdvice, forKey: .supportedAdvice)
        try container.encode(observedStoreRevision, forKey: .observedStoreRevision)
        try container.encodeIfPresent(session, forKey: .session)
        try container.encodeIfPresent(pendingInputTurnId, forKey: .pendingInputTurnId)
    }
}

public nonisolated struct StoryOpenViewDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let session: StoryPublicViewDTO
    public let openedStoreRevision: Int
    public let replayed: Bool

    init(session: StoryPublicViewDTO, openedStoreRevision: Int, replayed: Bool) {
        self.schemaVersion = StoryControl.schemaVersion
        self.session = session
        self.openedStoreRevision = openedStoreRevision
        self.replayed = replayed
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case session
        case openedStoreRevision = "opened_store_revision"
        case replayed
    }

    public init(from decoder: any Decoder) throws {
        let required: Set<String> = ["schema_version", "session", "opened_store_revision", "replayed"]
        try checkWireKeys(decoder, allowed: required, required: required)
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try StoryControl.schema(container.decode(String.self, forKey: .schemaVersion))
        session = try container.decode(StoryPublicViewDTO.self, forKey: .session)
        openedStoreRevision = try StoryControl.revision(
            container.decode(Int.self, forKey: .openedStoreRevision))
        replayed = try container.decode(Bool.self, forKey: .replayed)
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(schemaVersion, forKey: .schemaVersion)
        try container.encode(session, forKey: .session)
        try container.encode(openedStoreRevision, forKey: .openedStoreRevision)
        try container.encode(replayed, forKey: .replayed)
    }
}

public nonisolated struct StorySessionGetViewDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let session: StoryPublicViewDTO

    init(session: StoryPublicViewDTO) {
        self.schemaVersion = StoryControl.schemaVersion
        self.session = session
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case session
    }

    public init(from decoder: any Decoder) throws {
        try checkWireKeys(decoder, allowed: ["schema_version", "session"],
                          required: ["schema_version", "session"])
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try StoryControl.schema(container.decode(String.self, forKey: .schemaVersion))
        session = try container.decode(StoryPublicViewDTO.self, forKey: .session)
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(schemaVersion, forKey: .schemaVersion)
        try container.encode(session, forKey: .session)
    }
}

public nonisolated struct StoryReceiptViewDTO: Codable, Sendable, Equatable {
    public static let statuses: Set<String> = ["received", "cancelled", "committed"]

    public let inputTurnId: String
    public let sessionId: String
    public let turnId: String
    public let status: String
    public let committedStoreRevision: Int?
    public let committedStoryRevision: Int?

    enum CodingKeys: String, CodingKey {
        case inputTurnId = "input_turn_id"
        case sessionId = "session_id"
        case turnId = "turn_id"
        case status
        case committedStoreRevision = "committed_store_revision"
        case committedStoryRevision = "committed_story_revision"
    }

    public init(from decoder: any Decoder) throws {
        let required: Set<String> = ["input_turn_id", "session_id", "turn_id", "status"]
        try checkWireKeys(decoder,
                          allowed: required.union(["committed_store_revision",
                                                   "committed_story_revision"]),
                          required: required)
        let container = try decoder.container(keyedBy: CodingKeys.self)
        inputTurnId = try StoryControl.identifier(container.decode(String.self, forKey: .inputTurnId))
        sessionId = try StoryControl.identifier(container.decode(String.self, forKey: .sessionId))
        turnId = try StoryControl.identifier(container.decode(String.self, forKey: .turnId))
        status = try container.decode(String.self, forKey: .status)
        guard Self.statuses.contains(status) else { throw StoryControlError.invalidPayload }
        let storeRevision = try container.decodeIfPresent(Int.self, forKey: .committedStoreRevision)
        let storyRevision = try container.decodeIfPresent(Int.self, forKey: .committedStoryRevision)
        if status == "committed" {
            guard let storeRevision, let storyRevision else { throw StoryControlError.invalidPayload }
            committedStoreRevision = try StoryControl.revision(storeRevision)
            committedStoryRevision = try StoryControl.revision(storyRevision)
        } else {
            guard storeRevision == nil, storyRevision == nil else {
                throw StoryControlError.invalidPayload
            }
            committedStoreRevision = nil
            committedStoryRevision = nil
        }
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(inputTurnId, forKey: .inputTurnId)
        try container.encode(sessionId, forKey: .sessionId)
        try container.encode(turnId, forKey: .turnId)
        try container.encode(status, forKey: .status)
        try container.encodeIfPresent(committedStoreRevision, forKey: .committedStoreRevision)
        try container.encodeIfPresent(committedStoryRevision, forKey: .committedStoryRevision)
    }
}

public nonisolated struct StoryAdviceSubmitViewDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let receipt: StoryReceiptViewDTO
    public let session: StoryPublicViewDTO
    public let replayed: Bool

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case receipt, session, replayed
    }

    public init(from decoder: any Decoder) throws {
        let required: Set<String> = ["schema_version", "receipt", "session", "replayed"]
        try checkWireKeys(decoder, allowed: required, required: required)
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try StoryControl.schema(container.decode(String.self, forKey: .schemaVersion))
        receipt = try container.decode(StoryReceiptViewDTO.self, forKey: .receipt)
        session = try container.decode(StoryPublicViewDTO.self, forKey: .session)
        replayed = try container.decode(Bool.self, forKey: .replayed)
        guard receipt.status == "committed" else { throw StoryControlError.invalidPayload }
        guard receipt.sessionId == session.sessionId else { throw StoryControlError.invalidPayload }
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(schemaVersion, forKey: .schemaVersion)
        try container.encode(receipt, forKey: .receipt)
        try container.encode(session, forKey: .session)
        try container.encode(replayed, forKey: .replayed)
    }
}

public nonisolated struct StoryAdviceGetViewDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let found: Bool
    public let receipt: StoryReceiptViewDTO?
    public let session: StoryPublicViewDTO?
    public let replayed: Bool

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case found, receipt, session, replayed
    }

    public init(from decoder: any Decoder) throws {
        let required: Set<String> = ["schema_version", "found", "replayed"]
        try checkWireKeys(decoder, allowed: required.union(["receipt", "session"]), required: required)
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try StoryControl.schema(container.decode(String.self, forKey: .schemaVersion))
        found = try container.decode(Bool.self, forKey: .found)
        replayed = try container.decode(Bool.self, forKey: .replayed)
        receipt = try container.decodeIfPresent(StoryReceiptViewDTO.self, forKey: .receipt)
        session = try container.decodeIfPresent(StoryPublicViewDTO.self, forKey: .session)
        if found {
            guard let receipt else { throw StoryControlError.invalidPayload }
            if let session, session.sessionId != receipt.sessionId {
                throw StoryControlError.invalidPayload
            }
        } else {
            guard receipt == nil, session == nil, replayed == false else {
                throw StoryControlError.invalidPayload
            }
        }
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(schemaVersion, forKey: .schemaVersion)
        try container.encode(found, forKey: .found)
        try container.encodeIfPresent(receipt, forKey: .receipt)
        try container.encodeIfPresent(session, forKey: .session)
        try container.encode(replayed, forKey: .replayed)
    }
}
