import Foundation

/// Fixed, user-safe failures. Never include socket paths, payloads or launch credentials.
public nonisolated enum EngineConnectionError: Error, LocalizedError, Sendable, Equatable {
    case runtimeUnavailable, invalidConfiguration, launchFailed, notConnected
    case authenticationFailed, connectionFailed, timedOut, disconnected
    case invalidFrame, correlationMismatch, capacityExceeded, methodUnavailable

    public var errorDescription: String? {
        switch self {
        case .runtimeUnavailable: "此构建尚未包含本地引擎，当前展示示例数据。"
        case .invalidConfiguration: "本地引擎运行环境无效。"
        case .launchFailed: "本地引擎未能启动。"
        case .authenticationFailed: "本地引擎连接验证失败。"
        case .timedOut: "本地引擎响应超时，尚未确认的操作不会自动重发。"
        case .invalidFrame, .correlationMismatch: "本地引擎响应无效，已断开连接。"
        case .capacityExceeded: "本地引擎连接已达到安全容量限制。"
        case .methodUnavailable: "本地引擎尚未提供此功能。"
        case .connectionFailed, .notConnected, .disconnected: "本地引擎连接已断开。"
        }
    }
}

/// Derived from the canonical handshake payload, not a status=ok shortcut.
public nonisolated struct EngineHandshake: Sendable, Equatable {
    public let engineVersion: String
    public let pythonVersion: String
    public let capabilities: Set<String>
    public var liveTurnAvailable: Bool {
        capabilities.contains("story.turn.submit")
            || capabilities.contains(StoryPostCommitMethodCapability.turnSubmitV2.rawValue)
    }

    init(payload: [String: AnyCodableValue]) throws {
        let names: Set<String> = ["engine_version", "engine_build", "python_version", "protocol_version", "capabilities"]
        guard Set(payload.keys) == names,
              case .string(let version) = payload["engine_version"], !version.isEmpty,
              case .string(let build) = payload["engine_build"], !build.isEmpty,
              case .string(let python) = payload["python_version"], !python.isEmpty,
              payload["protocol_version"] == .string("1.0"),
              case .array(let items) = payload["capabilities"] else {
            throw EngineConnectionError.authenticationFailed
        }
        var methods = Set<String>()
        for item in items {
            guard case .string(let name) = item, !name.isEmpty, methods.insert(name).inserted else {
                throw EngineConnectionError.authenticationFailed
            }
        }
        engineVersion = version
        pythonVersion = python
        capabilities = methods
    }
}

public nonisolated struct EngineHealth: Sendable, Equatable {
    public let transportReady: Bool
    public let worldReady: Bool
    public let modelReady: Bool
    public let voiceReady: Bool

    init(payload: [String: AnyCodableValue]) throws {
        guard Set(payload.keys) == ["transport_ready", "world_ready", "model_ready", "voice_ready"],
              case .bool(let transport) = payload["transport_ready"],
              case .bool(let world) = payload["world_ready"],
              case .bool(let model) = payload["model_ready"],
              case .bool(let voice) = payload["voice_ready"] else {
            throw EngineConnectionError.invalidFrame
        }
        transportReady = transport
        worldReady = world
        modelReady = model
        voiceReady = voice
    }
}

// MARK: - Sealed Voice Render Control DTO

/// The exact sealed render recipe the Engine produced for a committed turn.
///
/// The App replays it verbatim; only `mediaStreamId` and `generation` are the
/// App's to supply, and only after `media.open` mints them. A client therefore
/// cannot choose the voice, its revision or the speed for a committed turn.
public nonisolated struct VoiceRenderRecipeDTO: Codable, Sendable, Equatable {
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
    public let speed: Double
    public let language: String?

    enum CodingKeys: String, CodingKey {
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
        case speed
        case language
    }

    public init(from decoder: any Decoder) throws {
        let keys: Set<String> = [
            "speech_unit_id", "turn_id", "story_revision", "narrative_block_id",
            "segment_index", "performance_plan_id", "spoken_text", "voice_id",
            "expected_voice_revision", "expected_model_revision", "speed", "language",
        ]
        // The canonical schema types these two as ["string","null"] and lists
        // them as required, so the key must be present but its value may be
        // null. Every other key in this DTO rejects null.
        try checkWireKeys(
            decoder,
            allowed: keys,
            required: keys,
            allowNull: ["expected_model_revision", "language"]
        )
        let container = try decoder.container(keyedBy: CodingKeys.self)
        speechUnitId = try VoiceRenderRecipeDTO.identifier(container.decode(String.self, forKey: .speechUnitId))
        turnId = try VoiceRenderRecipeDTO.identifier(container.decode(String.self, forKey: .turnId))
        storyRevision = try VoiceRenderRecipeDTO.revision(container.decode(Int.self, forKey: .storyRevision))
        narrativeBlockId = try VoiceRenderRecipeDTO.identifier(container.decode(String.self, forKey: .narrativeBlockId))
        segmentIndex = try VoiceRenderRecipeDTO.segmentIndex(container.decode(Int.self, forKey: .segmentIndex))
        performancePlanId = try VoiceRenderRecipeDTO.identifier(container.decode(String.self, forKey: .performancePlanId))
        spokenText = try VoiceRenderRecipeDTO.spokenText(container.decode(String.self, forKey: .spokenText))
        voiceId = try VoiceRenderRecipeDTO.identifier(container.decode(String.self, forKey: .voiceId))
        expectedVoiceRevision = try VoiceRenderRecipeDTO.identifier(
            container.decode(String.self, forKey: .expectedVoiceRevision))
        expectedModelRevision = try container.decodeIfPresent(String.self, forKey: .expectedModelRevision)
        if let expectedModelRevision {
            _ = try VoiceRenderRecipeDTO.identifier(expectedModelRevision)
        }
        speed = try VoiceRenderRecipeDTO.speed(container.decode(Double.self, forKey: .speed))
        language = try container.decodeIfPresent(String.self, forKey: .language)
        if let language {
            _ = try VoiceRenderRecipeDTO.identifier(language)
        }
    }

    private static func identifier(_ value: String) throws -> String {
        guard !value.isEmpty, value.utf8.count <= 256, !value.unicodeScalars.contains("\u{0}") else {
            throw EngineConnectionError.invalidFrame
        }
        return value
    }

    private static func revision(_ value: Int) throws -> Int {
        guard value >= 0, value <= 9_223_372_036_854_775_807 else {
            throw EngineConnectionError.invalidFrame
        }
        return value
    }

    private static func segmentIndex(_ value: Int) throws -> Int {
        guard value >= 0, value <= 131_071 else { throw EngineConnectionError.invalidFrame }
        return value
    }

    private static func spokenText(_ value: String) throws -> String {
        guard !value.isEmpty, value.utf8.count <= 4096, !value.unicodeScalars.contains("\u{0}") else {
            throw EngineConnectionError.invalidFrame
        }
        return value
    }

    private static func speed(_ value: Double) throws -> Double {
        guard value.isFinite, value > 0, value <= 4 else { throw EngineConnectionError.invalidFrame }
        return value
    }
}

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


    public init(
        schemaVersion: String,
        speechUnitId: String,
        turnId: String,
        storyRevision: Int,
        narrativeBlockId: String,
        segmentIndex: Int,
        performancePlanId: String,
        spokenText: String,
        voiceId: String,
        expectedVoiceRevision: String,
        expectedModelRevision: String?,
        mediaStreamId: String,
        generation: Int,
        speed: Double,
        language: String?
    ) {
        self.schemaVersion = schemaVersion
        self.speechUnitId = speechUnitId
        self.turnId = turnId
        self.storyRevision = storyRevision
        self.narrativeBlockId = narrativeBlockId
        self.segmentIndex = segmentIndex
        self.performancePlanId = performancePlanId
        self.spokenText = spokenText
        self.voiceId = voiceId
        self.expectedVoiceRevision = expectedVoiceRevision
        self.expectedModelRevision = expectedModelRevision
        self.mediaStreamId = mediaStreamId
        self.generation = generation
        self.speed = speed
        self.language = language
    }

    /// Bind a sealed recipe to the one-time media identity `media.open` minted.
    ///
    /// The execution fields are copied verbatim: the Engine rejects any drift,
    /// so this initializer cannot be used to alter how a committed turn sounds.
    public init(
        recipe: VoiceRenderRecipeDTO,
        mediaStreamId: String,
        generation: Int
    ) {
        self.schemaVersion = "1.0"
        self.speechUnitId = recipe.speechUnitId
        self.turnId = recipe.turnId
        self.storyRevision = recipe.storyRevision
        self.narrativeBlockId = recipe.narrativeBlockId
        self.segmentIndex = recipe.segmentIndex
        self.performancePlanId = recipe.performancePlanId
        self.spokenText = recipe.spokenText
        self.voiceId = recipe.voiceId
        self.expectedVoiceRevision = recipe.expectedVoiceRevision
        self.expectedModelRevision = recipe.expectedModelRevision
        self.mediaStreamId = mediaStreamId
        self.generation = generation
        self.speed = recipe.speed
        self.language = recipe.language
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

// MARK: - Voice Delivery Cursor Control
public nonisolated enum VoiceDeliveryEvidence: String, Codable, Sendable, Equatable {
    case queued
    case scheduled
    case renderedEstimate = "rendered_estimate"
    case measuredLoopback = "measured_loopback"
}

public nonisolated enum VoiceDeliveryStopReason: String, Codable, Sendable, Equatable {
    case userStop = "user_stop"
    case superseded
    case deviceRouteChange = "device_route_change"
    case suspend
    case providerError = "provider_error"
    case mediaError = "media_error"
    case completed
}

public nonisolated struct VoiceDeliveryCursorDTO: Codable, Sendable, Equatable {
    public let trackId: String
    public let consumerId: String
    public let unitId: String
    public let generation: Int
    public let sourceOffsetFrames: Int
    public let totalSourceFrames: Int?
    public let evidence: VoiceDeliveryEvidence
    public let stopReason: VoiceDeliveryStopReason?
    public let cursorRevision: Int
    public let fullyOutput: Bool

    enum CodingKeys: String, CodingKey {
        case trackId = "track_id"
        case consumerId = "consumer_id"
        case unitId = "unit_id"
        case generation
        case sourceOffsetFrames = "source_offset_frames"
        case totalSourceFrames = "total_source_frames"
        case evidence
        case stopReason = "stop_reason"
        case cursorRevision = "cursor_revision"
        case fullyOutput = "fully_output"
    }
}

public nonisolated struct VoiceDeliveryCursorResponseDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let cursor: VoiceDeliveryCursorDTO?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case cursor
    }
}

public nonisolated struct VoiceDeliveryCursorUpdateDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let operation: String
    public let trackId: String
    public let consumerId: String
    public let unitId: String
    public let generation: Int
    public let sourceOffsetFrames: Int
    public let totalSourceFrames: Int?
    public let evidence: VoiceDeliveryEvidence
    public let stopReason: VoiceDeliveryStopReason?
    public let expectedCursorRevision: Int

    public init(
        trackId: String,
        consumerId: String,
        unitId: String,
        generation: Int,
        sourceOffsetFrames: Int,
        totalSourceFrames: Int?,
        evidence: VoiceDeliveryEvidence,
        stopReason: VoiceDeliveryStopReason?,
        expectedCursorRevision: Int
    ) {
        self.schemaVersion = "1.0"
        self.operation = "update"
        self.trackId = trackId
        self.consumerId = consumerId
        self.unitId = unitId
        self.generation = generation
        self.sourceOffsetFrames = sourceOffsetFrames
        self.totalSourceFrames = totalSourceFrames
        self.evidence = evidence
        self.stopReason = stopReason
        self.expectedCursorRevision = expectedCursorRevision
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case operation
        case trackId = "track_id"
        case consumerId = "consumer_id"
        case unitId = "unit_id"
        case generation
        case sourceOffsetFrames = "source_offset_frames"
        case totalSourceFrames = "total_source_frames"
        case evidence
        case stopReason = "stop_reason"
        case expectedCursorRevision = "expected_cursor_revision"
    }
}
