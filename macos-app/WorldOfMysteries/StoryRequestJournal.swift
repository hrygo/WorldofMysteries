import Foundation

/// Local retry intent for the trusted first turn.
///
/// The journal is a client-side aid, never a fact source: it carries only request
/// identity, the frozen raw text and the revisions the client must reuse. It never
/// stores tokens, hidden state, database contents or narrative payloads.
public nonisolated struct StoryRequestRecord: Codable, Sendable, Equatable {
    public enum Phase: String, Codable, Sendable {
        case opening
        case opened
        case submitting
        case committed
    }

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
        openRequestId: String? = nil,
        openStoreRevision: Int? = nil,
        sessionId: String? = nil,
        inputTurnId: String? = nil,
        rawInput: String? = nil,
        storyRevision: Int? = nil,
        storeRevision: Int? = nil
    ) {
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

    /// A frozen submit intent that can be replayed with byte-identical identity.
    public var frozenSubmission: StoryFrozenSubmission? {
        guard let sessionId, let inputTurnId, let rawInput,
              let storyRevision, let storeRevision else { return nil }
        return StoryFrozenSubmission(
            sessionId: sessionId, inputTurnId: inputTurnId, rawInput: rawInput,
            expectedStoryRevision: storyRevision, expectedStoreRevision: storeRevision)
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

    public init(
        sessionId: String, inputTurnId: String, rawInput: String,
        expectedStoryRevision: Int, expectedStoreRevision: Int
    ) {
        self.sessionId = sessionId
        self.inputTurnId = inputTurnId
        self.rawInput = rawInput
        self.expectedStoryRevision = expectedStoryRevision
        self.expectedStoreRevision = expectedStoreRevision
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
        guard let data = try? Data(contentsOf: fileURL) else { return nil }
        // A corrupt journal never fabricates a request: the server remains the only
        // source of truth and the UI degrades to a read-only pending state.
        return try? JSONDecoder().decode(StoryRequestRecord.self, from: data)
    }

    public func save(_ record: StoryRequestRecord) throws {
        let fileManager = FileManager.default
        try fileManager.createDirectory(
            at: directory, withIntermediateDirectories: true,
            attributes: [.posixPermissions: 0o700])
        try? fileManager.setAttributes([.posixPermissions: 0o700], ofItemAtPath: directory.path)
        let data = try JSONEncoder().encode(record)
        try data.write(to: fileURL, options: [.atomic])
        try? fileManager.setAttributes([.posixPermissions: 0o600], ofItemAtPath: fileURL.path)
    }

    public func clear() throws {
        guard FileManager.default.fileExists(atPath: fileURL.path) else { return }
        try FileManager.default.removeItem(at: fileURL)
    }
}
