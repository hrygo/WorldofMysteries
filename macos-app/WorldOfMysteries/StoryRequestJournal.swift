import Foundation

public nonisolated enum StorySubmissionMethod: String, Codable, Sendable, Equatable {
    case storyAdviceSubmit = "story.advice.submit"
    case storyTurnSubmit = "story.turn.submit"
}

public nonisolated enum StoryRequestJournalError: Error, Equatable, Sendable {
    case unsupportedRecordVersion(Int)
    case invalidVersionedFields
    case invalidInputModeAndMethod
}

/// Local retry intent for the trusted first turn.
///
/// The journal is a client-side aid, never a fact source: it carries only request
/// identity, the frozen raw text and the revisions the client must reuse. It never
/// stores tokens, hidden state, database contents or narrative payloads.
public nonisolated struct StoryRequestRecord: Codable, Sendable, Equatable {
    public static let currentRecordVersion = 2

    public enum Phase: String, Codable, Sendable {
        case opening
        case opened
        case submitting
        case committed
    }

    public var recordVersion: Int
    public var inputMode: StoryInputMode
    public var submissionMethod: StorySubmissionMethod
    public var phase: Phase
    public var scenarioId: String
    public var openRequestId: String?
    public var openStoreRevision: Int?
    public var sessionId: String?
    public var inputTurnId: String?
    public var rawInput: String?
    public var storyRevision: Int?
    public var storeRevision: Int?

    public init(
        phase: Phase,
        scenarioId: String = StoryControl.scenarioId,
        recordVersion: Int = Self.currentRecordVersion,
        inputMode: StoryInputMode = .text,
        submissionMethod: StorySubmissionMethod = .storyAdviceSubmit,
        openRequestId: String? = nil,
        openStoreRevision: Int? = nil,
        sessionId: String? = nil,
        inputTurnId: String? = nil,
        rawInput: String? = nil,
        storyRevision: Int? = nil,
        storeRevision: Int? = nil
    ) {
        self.recordVersion = recordVersion
        self.inputMode = inputMode
        self.submissionMethod = submissionMethod
        self.phase = phase
        self.scenarioId = scenarioId
        self.openRequestId = openRequestId
        self.openStoreRevision = openStoreRevision
        self.sessionId = sessionId
        self.inputTurnId = inputTurnId
        self.rawInput = rawInput
        self.storyRevision = storyRevision
        self.storeRevision = storeRevision
    }

    private enum CodingKeys: String, CodingKey {
        case recordVersion
        case inputMode
        case submissionMethod
        case phase
        case scenarioId
        case openRequestId
        case openStoreRevision
        case sessionId
        case inputTurnId
        case rawInput
        case storyRevision
        case storeRevision
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        phase = try container.decode(Phase.self, forKey: .phase)
        scenarioId = try container.decode(String.self, forKey: .scenarioId)
        openRequestId = try container.decodeIfPresent(String.self, forKey: .openRequestId)
        openStoreRevision = try container.decodeIfPresent(Int.self, forKey: .openStoreRevision)
        sessionId = try container.decodeIfPresent(String.self, forKey: .sessionId)
        inputTurnId = try container.decodeIfPresent(String.self, forKey: .inputTurnId)
        rawInput = try container.decodeIfPresent(String.self, forKey: .rawInput)
        storyRevision = try container.decodeIfPresent(Int.self, forKey: .storyRevision)
        storeRevision = try container.decodeIfPresent(Int.self, forKey: .storeRevision)

        let hasVersion = container.contains(.recordVersion)
        let hasInputMode = container.contains(.inputMode)
        let hasMethod = container.contains(.submissionMethod)
        if !hasVersion && !hasInputMode && !hasMethod {
            // Historical journals recorded only the fixed text advice method.
            recordVersion = 1
            inputMode = .text
            submissionMethod = .storyAdviceSubmit
        } else {
            guard hasVersion, hasInputMode, hasMethod else {
                throw StoryRequestJournalError.invalidVersionedFields
            }
            let version = try container.decode(Int.self, forKey: .recordVersion)
            guard version == Self.currentRecordVersion else {
                throw StoryRequestJournalError.unsupportedRecordVersion(version)
            }
            recordVersion = version
            inputMode = try container.decode(StoryInputMode.self, forKey: .inputMode)
            submissionMethod = try container.decode(
                StorySubmissionMethod.self,
                forKey: .submissionMethod
            )
            guard Self.isValid(inputMode: inputMode, method: submissionMethod) else {
                throw StoryRequestJournalError.invalidInputModeAndMethod
            }
        }
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(recordVersion, forKey: .recordVersion)
        try container.encode(inputMode, forKey: .inputMode)
        try container.encode(submissionMethod, forKey: .submissionMethod)
        try container.encode(phase, forKey: .phase)
        try container.encode(scenarioId, forKey: .scenarioId)
        try container.encodeIfPresent(openRequestId, forKey: .openRequestId)
        try container.encodeIfPresent(openStoreRevision, forKey: .openStoreRevision)
        try container.encodeIfPresent(sessionId, forKey: .sessionId)
        try container.encodeIfPresent(inputTurnId, forKey: .inputTurnId)
        try container.encodeIfPresent(rawInput, forKey: .rawInput)
        try container.encodeIfPresent(storyRevision, forKey: .storyRevision)
        try container.encodeIfPresent(storeRevision, forKey: .storeRevision)
    }

    private static func isValid(
        inputMode: StoryInputMode,
        method: StorySubmissionMethod
    ) -> Bool {
        switch (inputMode, method) {
        case (.text, .storyAdviceSubmit), (.voice, .storyTurnSubmit):
            return true
        case (.text, .storyTurnSubmit), (.voice, .storyAdviceSubmit):
            return false
        }
    }

    func upgradedForNextSave() -> StoryRequestRecord {
        var upgraded = self
        upgraded.recordVersion = Self.currentRecordVersion
        return upgraded
    }

    /// A frozen submit intent that can be replayed with byte-identical identity.
    public var frozenSubmission: StoryFrozenSubmission? {
        guard let sessionId, let inputTurnId, let rawInput,
              let storyRevision, let storeRevision else { return nil }
        return StoryFrozenSubmission(
            sessionId: sessionId, inputTurnId: inputTurnId, rawInput: rawInput,
            expectedStoryRevision: storyRevision, expectedStoreRevision: storeRevision,
            inputMode: inputMode, submissionMethod: submissionMethod)
    }

    public var isOpenPending: Bool {
        phase == .opening && sessionId == nil && openRequestId != nil
    }
}

public nonisolated struct StoryFrozenSubmission: Sendable, Equatable {
    public let sessionId: String
    public let inputTurnId: String
    public let rawInput: String
    public let expectedStoryRevision: Int
    public let expectedStoreRevision: Int
    public let inputMode: StoryInputMode
    public let submissionMethod: StorySubmissionMethod

    public init(
        sessionId: String, inputTurnId: String, rawInput: String,
        expectedStoryRevision: Int, expectedStoreRevision: Int,
        inputMode: StoryInputMode = .text,
        submissionMethod: StorySubmissionMethod = .storyAdviceSubmit
    ) {
        self.sessionId = sessionId
        self.inputTurnId = inputTurnId
        self.rawInput = rawInput
        self.expectedStoryRevision = expectedStoryRevision
        self.expectedStoreRevision = expectedStoreRevision
        self.inputMode = inputMode
        self.submissionMethod = submissionMethod
    }
}

public nonisolated protocol StoryJournalWriting: Sendable {
    func load() throws -> StoryRequestRecord?
    func save(_ record: StoryRequestRecord) throws
    func clear() throws
}

/// Owner-only JSON journal written atomically next to the engineering data root.
public nonisolated struct StoryRequestJournal: StoryJournalWriting {
    public static let fileName = "first-turn-request.json"

    private let directory: URL
    private let fileURL: URL

    public init(root: URL? = nil) {
        let resolved = root ?? StoryRequestJournal.defaultRoot()
        directory = resolved
        fileURL = resolved.appendingPathComponent(Self.fileName, isDirectory: false)
    }

    public static func defaultRoot(
        _ fileManager: FileManager = .default
    ) -> URL {
        let support = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? fileManager.temporaryDirectory
        return support
            .appendingPathComponent("WorldofMysteries", isDirectory: true)
            .appendingPathComponent("Engineering/Golden001/Journal", isDirectory: true)
    }

    public func load() throws -> StoryRequestRecord? {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return nil }
        let data = try Data(contentsOf: fileURL)
        // Corrupt or unknown data is retained and reported. The App must not
        // treat it as an absent journal and create a replacement identity.
        return try JSONDecoder().decode(StoryRequestRecord.self, from: data)
    }

    public func save(_ record: StoryRequestRecord) throws {
        let fileManager = FileManager.default
        try fileManager.createDirectory(
            at: directory, withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700])
        try? fileManager.setAttributes([.posixPermissions: 0o700], ofItemAtPath: directory.path)
        let data = try JSONEncoder().encode(record.upgradedForNextSave())
        try data.write(to: fileURL, options: [.atomic])
        try? fileManager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: fileURL.path)
    }

    public func clear() throws {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return }
        try FileManager.default.removeItem(at: fileURL)
    }
}
