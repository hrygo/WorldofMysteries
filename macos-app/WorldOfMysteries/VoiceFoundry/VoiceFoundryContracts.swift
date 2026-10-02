import Foundation

// Wire types for the Voice Foundry control surface. Every field here is
// declared by `contracts/protocol/voice_foundry_control.schema.json` or
// `contracts/schemas/voice_foundry_state.schema.json`; nothing in this file
// is a client-side convenience the engine does not also know about.

public nonisolated struct VoiceFoundryScopeDTO: Codable, Sendable, Equatable {
    public let ownerId: String
    public let worldId: String
    public let worldlineId: String
    public let presentationIdentity: String
    public let phase: String
    public let locale: String

    enum CodingKeys: String, CodingKey {
        case ownerId = "owner_id"
        case worldId = "world_id"
        case worldlineId = "worldline_id"
        case presentationIdentity = "presentation_identity"
        case phase
        case locale
    }
}

public nonisolated struct VoiceFoundryCandidateDTO: Codable, Sendable, Equatable {
    public let candidateId: String
    public let slot: Int
    public let seed: Int
    public let state: String
    public let previewAudioDigest: String
    public let providerCandidateId: String?
    public let providerCandidateRevision: String?

    enum CodingKeys: String, CodingKey {
        case candidateId = "candidate_id"
        case slot
        case seed
        case state
        case previewAudioDigest = "preview_audio_digest"
        case providerCandidateId = "provider_candidate_id"
        case providerCandidateRevision = "provider_candidate_revision"
    }
}

public nonisolated struct VoiceFoundryTaskDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let taskId: String
    public let requestId: String
    public let requestDigest: String
    public let scope: VoiceFoundryScopeDTO
    public let stage: String
    public let taskRevision: Int
    public let cancelRequested: Bool
    public let operationStatus: String
    public let requiredActions: [String]
    public let reasonCode: String?
    public let candidates: [VoiceFoundryCandidateDTO]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case taskId = "task_id"
        case requestId = "request_id"
        case requestDigest = "request_digest"
        case scope
        case stage
        case taskRevision = "task_revision"
        case cancelRequested = "cancel_requested"
        case operationStatus = "operation_status"
        case requiredActions = "required_actions"
        case reasonCode = "reason_code"
        case candidates
    }

    /// The one candidate a listener is being asked about, if the task has
    /// parked exactly one. A task with none, or with several, has nothing to
    /// audition — and guessing which one was meant is how a verdict ends up
    /// attached to the wrong voice.
    public var auditionedCandidate: VoiceFoundryCandidateDTO? {
        candidates.count == 1 ? candidates[0] : nil
    }
}

public nonisolated struct VoiceFoundryGetResponseDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let task: VoiceFoundryTaskDTO

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case task
    }
}

public nonisolated struct VoiceFoundryListResponseDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let tasks: [VoiceFoundryTaskDTO]
    public let nextPageToken: String?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case tasks
        case nextPageToken = "next_page_token"
    }
}

/// Which of a candidate's two audition assets is being asked for.
public nonisolated enum VoiceFoundryAssetKind: String, Codable, Sendable, CaseIterable {
    case reference
    case validation
}

public nonisolated struct VoiceFoundryAssetResponseDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let taskId: String
    public let candidateId: String
    public let kind: VoiceFoundryAssetKind
    public let candidateRevision: String
    /// Present for the cross-text asset, null for the reference: the reference
    /// belongs to no validation, and `voice.foundry.review` requires the id of
    /// the validation the listener actually judged.
    public let validationId: String?
    public let audioDigest: String
    public let audioBytes: Int
    public let audioBase64: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case taskId = "task_id"
        case candidateId = "candidate_id"
        case kind
        case candidateRevision = "candidate_revision"
        case validationId = "validation_id"
        case audioDigest = "audio_digest"
        case audioBytes = "audio_bytes"
        case audioBase64 = "audio_base64"
    }

    /// The audio the engine actually hashed. `audioBytes` is what the engine
    /// claims; this is what arrived. A mismatch means the answer is not the
    /// asset it describes, and nothing downstream may treat it as one.
    public func decodedAudio() throws -> Data {
        guard let data = Data(base64Encoded: audioBase64), data.count == audioBytes else {
            throw VoiceFoundryClientError.assetPayloadMismatch
        }
        return data
    }
}

public nonisolated enum VoiceFoundryClientError: Error, Equatable {
    /// The engine answered, but not with audio matching what it reported.
    case assetPayloadMismatch
    /// The audio is not a WAV this client knows how to play.
    case audioNotPlayable
}

public nonisolated struct VoiceFoundryHumanReviewDTO: Codable, Sendable, Equatable {
    public let validationId: String
    public let referenceAudioDigest: String
    public let validationAudioDigest: String
    /// `pass` or `reject`. There is deliberately no third value: `warn` has no
    /// representation in the evidence contract, and a client that could send
    /// one would be able to describe a verdict the engine cannot record.
    public let identity: String
    public let naturalness: String

    enum CodingKeys: String, CodingKey {
        case validationId = "validation_id"
        case referenceAudioDigest = "reference_audio_digest"
        case validationAudioDigest = "validation_audio_digest"
        case identity
        case naturalness
    }
}

public nonisolated struct VoiceFoundrySelectPayloadDTO: Codable, Sendable, Equatable {
    public let candidateId: String
    public let previewAudioDigest: String

    enum CodingKeys: String, CodingKey {
        case candidateId = "candidate_id"
        case previewAudioDigest = "preview_audio_digest"
    }
}

public nonisolated struct VoiceFoundryConfirmReferencePayloadDTO: Codable, Sendable, Equatable {
    public let providerCandidateRevision: String
    public let referenceText: String
    public let referenceAudioDigest: String

    enum CodingKeys: String, CodingKey {
        case providerCandidateRevision = "provider_candidate_revision"
        case referenceText = "reference_text"
        case referenceAudioDigest = "reference_audio_digest"
    }
}

public nonisolated struct VoiceFoundryValidatePayloadDTO: Codable, Sendable, Equatable {
    public let testText: String
    public let capabilityKey: String

    enum CodingKeys: String, CodingKey {
        case testText = "test_text"
        case capabilityKey = "capability_key"
    }
}

public nonisolated struct VoiceFoundryReviewPayloadDTO: Codable, Sendable, Equatable {
    public let humanReview: VoiceFoundryHumanReviewDTO

    enum CodingKeys: String, CodingKey {
        case humanReview = "human_review"
    }
}

public nonisolated struct VoiceFoundryPublishPayloadDTO: Codable, Sendable, Equatable {
    public let providerCandidateRevision: String

    enum CodingKeys: String, CodingKey {
        case providerCandidateRevision = "provider_candidate_revision"
    }
}

public nonisolated struct VoiceFoundryRetryPayloadDTO: Codable, Sendable, Equatable {
    public init() {}
}

public nonisolated struct VoiceFoundryCancelPayloadDTO: Codable, Sendable, Equatable {
    public let reasonCode: String?

    enum CodingKeys: String, CodingKey {
        case reasonCode = "reason_code"
    }
}

/// The idempotent command envelope every Voice Foundry write shares.
public nonisolated struct VoiceFoundryCommandDTO<Payload: Codable & Sendable>: Codable, Sendable {
    public let schemaVersion: String
    public let commandId: String
    public let payloadDigest: String
    public let taskId: String
    public let expectedTaskRevision: Int
    public let action: String
    public let payload: Payload

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case commandId = "command_id"
        case payloadDigest = "payload_digest"
        case taskId = "task_id"
        case expectedTaskRevision = "expected_task_revision"
        case action
        case payload
    }

    /// Build the envelope, quoting a digest of the payload as the engine will
    /// recompute it. Computing it anywhere else would make every command fail
    /// as `command_digest_mismatch`, which reads like a server fault rather
    /// than a serialization that never agreed in the first place.
    public init(
        commandId: String,
        taskId: String,
        expectedTaskRevision: Int,
        action: String,
        payload: Payload
    ) throws {
        self.schemaVersion = "1.0"
        self.commandId = commandId
        self.payloadDigest = try VoiceFoundryCommandDigest.digest(payload)
        self.taskId = taskId
        self.expectedTaskRevision = expectedTaskRevision
        self.action = action
        self.payload = payload
    }
}

public nonisolated struct VoiceFoundryCommandResponseDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let taskId: String
    public let commandId: String
    public let accepted: Bool
    public let replayed: Bool
    public let task: VoiceFoundryTaskDTO

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case taskId = "task_id"
        case commandId = "command_id"
        case accepted
        case replayed
        case task
    }
}

// MARK: - Casting catalog

/// One identity's public casting brief, exactly as
/// `contracts/schemas/voice_design.schema.json` states it.
///
/// The App renders this so a person can choose whom to cast. The brief itself
/// stays engine-side: casting sends a design id and lets the engine look up
/// the words, so the picker and the cast can never be describing two different
/// voices for one character.
public nonisolated struct VoiceDesignDTO: Codable, Sendable, Equatable, Identifiable {
    public let schemaVersion: String
    public let designId: String
    public let displayName: String
    public let presentationIdentity: String
    public let usage: String
    public let locale: String
    public let designRevision: Int
    public let publicTraits: [String]
    public let voiceDescription: String
    public let referenceText: String
    public let validationText: String

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case designId = "design_id"
        case displayName = "display_name"
        case presentationIdentity = "presentation_identity"
        case usage
        case locale
        case designRevision = "design_revision"
        case publicTraits = "public_traits"
        case voiceDescription = "voice_description"
        case referenceText = "reference_text"
        case validationText = "validation_text"
    }

    public var id: String { designId }

    /// The one-line form a picker shows. The full brief is deliberately not the
    /// label: a wall of prose in a menu is how a cast gets chosen by accident.
    public var pickerSummary: String {
        publicTraits.isEmpty
            ? displayName
            : "\(displayName) · \(publicTraits.joined(separator: "、"))"
    }
}

public nonisolated struct VoiceFoundryDesignsResponseDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let catalogVersion: String
    public let designs: [VoiceDesignDTO]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case catalogVersion = "catalog_version"
        case designs
    }
}

/// The answer to a cast: the task that was opened, or nothing because the
/// identity already had a voice. An existing voice is an answer, not an empty
/// casting — the button pressing it again must not read as a failure.
public nonisolated struct VoiceFoundryCastResponseDTO: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let task: VoiceFoundryTaskDTO?

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case task
    }
}
