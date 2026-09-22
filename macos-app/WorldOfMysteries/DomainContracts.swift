import Foundation

// MARK: - Character DTO
public nonisolated struct CharacterIdentityDTO: Codable, Sendable, Equatable {
    public let displayName: String
    public let age: Int?
    public let occupation: String?
    public let pathwayId: String?
    public let sequence: Int?

    enum CodingKeys: String, CodingKey {
        case displayName = "display_name"
        case age
        case occupation
        case pathwayId = "pathway_id"
        case sequence
    }
}

public nonisolated struct CharacterCoreDTO: Codable, Sendable, Equatable {
    public let traits: [String: String]
    public let decisionStyle: [String]
    public let values: [String: String]
    public let hardBoundaries: [String]

    enum CodingKeys: String, CodingKey {
        case traits
        case decisionStyle = "decision_style"
        case values
        case hardBoundaries = "hard_boundaries"
    }
}

public nonisolated struct CharacterGoalsDTO: Codable, Sendable, Equatable {
    public let long: String?
    public let medium: String?
    public let immediate: String?
}

public nonisolated struct CharacterEmotionDTO: Codable, Sendable, Equatable {
    public let primary: String?
    public let intensity: Double?
}

public nonisolated struct CharacterConditionDTO: Codable, Sendable, Equatable {
    public let injury: String?
    public let fatigue: Double?
    public let spirituality: Double?
    public let corruption: Double?
}

public nonisolated struct CharacterStateDTO: Codable, Sendable, Equatable {
    public let locationId: String?
    public let goals: CharacterGoalsDTO
    public let emotion: CharacterEmotionDTO?
    public let condition: CharacterConditionDTO?

    enum CodingKeys: String, CodingKey {
        case locationId = "location_id"
        case goals
        case emotion
        case condition
    }
}

public nonisolated struct CharacterDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let id: String
    public let kind: String
    public let identity: CharacterIdentityDTO
    public let core: CharacterCoreDTO
    public let state: CharacterStateDTO
    public let revision: Int

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case id
        case kind
        case identity
        case core
        case state
        case revision
    }
}

// MARK: - World Snapshot DTO
public nonisolated struct WorldLocationDTO: Codable, Sendable, Equatable {
    public let id: String
    public let city: String?
    public let district: String?
    public let open: Bool?
    public let closesAt: String?
    public let rooms: [String]?
    public let discoveredRooms: [String]?

    enum CodingKeys: String, CodingKey {
        case id
        case city
        case district
        case open
        case closesAt = "closes_at"
        case rooms
        case discoveredRooms = "discovered_rooms"
    }
}

public nonisolated struct WorldSnapshotDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let worldId: String
    public let worldlineId: String
    public let worldTime: String?
    public let revision: Int
    public let location: WorldLocationDTO?
    public let weather: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case worldId = "world_id"
        case worldlineId = "worldline_id"
        case worldTime = "world_time"
        case revision
        case location
        case weather
    }
}

// MARK: - Player Advice DTO
public nonisolated struct PlayerAdviceDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let id: String
    public let turnId: String?
    public let rawInput: String
    public let inputMode: String
    public let primaryIntent: String
    public let secondaryIntents: [String]?
    public let proposedActions: [String]?
    public let riskPreference: String?
    public let confidence: Double?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case id
        case turnId = "turn_id"
        case rawInput = "raw_input"
        case inputMode = "input_mode"
        case primaryIntent = "primary_intent"
        case secondaryIntents = "secondary_intents"
        case proposedActions = "proposed_actions"
        case riskPreference = "risk_preference"
        case confidence
    }
}

// MARK: - Episode DTO
public nonisolated struct EpisodeEndingDTO: Codable, Sendable, Equatable {
    public let type: String
    public let mainProblem: String?

    enum CodingKeys: String, CodingKey {
        case type
        case mainProblem = "main_problem"
    }
}

public nonisolated struct EpisodeDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let id: String
    public let worldId: String
    public let worldlineId: String
    public let storySeedId: String
    public let protagonistIds: [String]
    public let title: String
    public let startWorldTime: String?
    public let endWorldTime: String?
    public let ending: EpisodeEndingDTO
    public let secretStates: [String: String]?
    public let discoveredClueIds: [String]?
    public let unresolvedThreads: [String]?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case id
        case worldId = "world_id"
        case worldlineId = "worldline_id"
        case storySeedId = "story_seed_id"
        case protagonistIds = "protagonist_ids"
        case title
        case startWorldTime = "start_world_time"
        case endWorldTime = "end_world_time"
        case ending
        case secretStates = "secret_states"
        case discoveredClueIds = "discovered_clue_ids"
        case unresolvedThreads = "unresolved_threads"
    }
}

// MARK: - Knowledge DTO
public nonisolated struct KnowledgeSourceDTO: Codable, Sendable, Equatable {
    public let type: String
    public let ref: String
    public let reliability: Double?
}

public nonisolated struct CharacterKnowledgeDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let id: String
    public let characterId: String
    public let worldlineId: String
    public let propositionId: String
    public let certainty: Double
    public let source: KnowledgeSourceDTO
    public let acquiredWorldTime: String?
    public let status: String
    public let revision: Int

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case id
        case characterId = "character_id"
        case worldlineId = "worldline_id"
        case propositionId = "proposition_id"
        case certainty
        case source
        case acquiredWorldTime = "acquired_world_time"
        case status
        case revision
    }
}


// MARK: - Sealed Voice Render Control DTO
public nonisolated struct VoiceRenderControlRequestDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let speechUnitId: String
    public let turnId: String
    public let storyRevision: Int
    public let narrativeBlockId: String
    public let segmentIndex: Int
    public let performancePlanId: String
    public let spokenText: String
    public let voiceId: String
    public let expectedVoiceRevision: String
    public let expectedModelRevision: String?
    public let mediaStreamId: String
    public let generation: Int
    public let speed: Double
    public let language: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case speechUnitId = "speech_unit_id"
        case turnId = "turn_id"
        case storyRevision = "story_revision"
        case narrativeBlockId = "narrative_block_id"
        case segmentIndex = "segment_index"
        case performancePlanId = "performance_plan_id"
        case spokenText = "spoken_text"
        case voiceId = "voice_id"
        case expectedVoiceRevision = "expected_voice_revision"
        case expectedModelRevision = "expected_model_revision"
        case mediaStreamId = "media_stream_id"
        case generation
        case speed
        case language
    }
}

public nonisolated struct VoiceRenderAcceptedDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let renderId: String
    public let speechUnitId: String
    public let mediaStreamId: String
    public let generation: Int
    public let state: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case renderId = "render_id"
        case speechUnitId = "speech_unit_id"
        case mediaStreamId = "media_stream_id"
        case generation
        case state
    }
}
