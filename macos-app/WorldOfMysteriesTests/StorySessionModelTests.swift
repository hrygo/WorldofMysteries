import Foundation
import Testing
@testable import WorldOfMysteriesCore

/// Thread-safe call log shared by the model doubles.
final class StoryCallLog: @unchecked Sendable {
    private let lock = NSLock()
    private var entries: [String] = []

    func append(_ value: String) {
        lock.lock(); entries.append(value); lock.unlock()
    }

    var values: [String] {
        lock.lock(); defer { lock.unlock() }
        return entries
    }
}

final class MemoryStoryJournal: StoryJournalWriting, @unchecked Sendable {
    private let lock = NSLock()
    private var stored: StoryRequestRecord?
    private var failWrites = false

    func failNextWrites(_ failing: Bool) {
        lock.withLock { failWrites = failing }
    }

    func load() throws -> StoryRequestRecord? {
        lock.withLock { stored }
    }

    func save(_ record: StoryRequestRecord) throws {
        let failing = lock.withLock { failWrites }
        if failing { throw StoryControlError.invalidPayload }
        lock.withLock { stored = record }
    }

    func clear() throws {
        lock.withLock { stored = nil }
    }
}

final class FakeStoryClient: StoryEngineClient, @unchecked Sendable {
    private let lock = NSLock()
    private let log: StoryCallLog
    private let journal: MemoryStoryJournal
    private let entryView: StoryEntryViewDTO
    private let openView: StoryOpenViewDTO

    private var submitView: StoryAdviceSubmitViewDTO?
    private var adviceView: StoryAdviceGetViewDTO
    private var submitError: (any Error)?
    private var openError: (any Error)?
    private var gateStream: AsyncStream<Void>?
    private var gateContinuation: AsyncStream<Void>.Continuation?

    init(log: StoryCallLog, journal: MemoryStoryJournal,
         entryView: StoryEntryViewDTO, openView: StoryOpenViewDTO,
         submitView: StoryAdviceSubmitViewDTO?, adviceView: StoryAdviceGetViewDTO) {
        self.log = log
        self.journal = journal
        self.entryView = entryView
        self.openView = openView
        self.submitView = submitView
        self.adviceView = adviceView
    }

    func setSubmitError(_ error: (any Error)?) { lock.withLock { submitError = error } }
    func setOpenError(_ error: (any Error)?) { lock.withLock { openError = error } }
    func setAdvice(_ view: StoryAdviceGetViewDTO) { lock.withLock { adviceView = view } }

    func holdSubmit() {
        let pair = AsyncStream<Void>.makeStream()
        lock.withLock {
            gateStream = pair.stream
            gateContinuation = pair.continuation
        }
    }

    func releaseSubmit() {
        let continuation = lock.withLock { () -> AsyncStream<Void>.Continuation? in
            let value = gateContinuation
            gateContinuation = nil
            gateStream = nil
            return value
        }
        continuation?.finish()
    }

    var submittedCount: Int { log.values.filter { $0 == "client.submit" }.count }

    func storyEntry(scenarioId: String) async throws -> StoryEntryViewDTO {
        log.append("client.entry")
        return entryView
    }

    func storyOpen(openRequestId: String, expectedStoreRevision: Int) async throws -> StoryOpenViewDTO {
        // A mutation must never be sent before the frozen intent is durable locally.
        let frozen = try? journal.load()
        #expect(frozen?.openRequestId == openRequestId)
        #expect(frozen?.openStoreRevision == expectedStoreRevision)
        log.append("client.open")
        if let error = lock.withLock({ openError }) { throw error }
        return openView
    }

    func storySession(sessionId: String) async throws -> StorySessionGetViewDTO {
        log.append("client.session")
        return StorySessionGetViewDTO(session: openView.session)
    }

    func storySubmit(_ request: StoryAdviceSubmitRequestDTO) async throws -> StoryAdviceSubmitViewDTO {
        log.append("client.submit")
        let state = lock.withLock { (gateStream, submitError, submitView) }
        if let gate = state.0 { for await _ in gate { break } }
        if let error = state.1 { throw error }
        guard let view = state.2 else { throw EngineConnectionError.invalidFrame }
        return view
    }

    func storyAdvice(sessionId: String, inputTurnId: String) async throws -> StoryAdviceGetViewDTO {
        log.append("client.advice")
        return lock.withLock { adviceView }
    }
}

@MainActor
@Suite("Trusted first-turn story model")
struct StorySessionModelTests {
    static func view(
        sessionId: String = "session_1", turn: Int = 0, storyRevision: Int = 0,
        storeRevision: Int = 1, canSubmit: Bool = true
    ) throws -> StoryPublicViewDTO {
        let clues = turn > 0
            ? #"[{"id": "clue_doctor_pause", "display_name": "医生的停顿"}]"#
            : "[]"
        let lastTurn = turn > 0 ? #", "last_committed_turn_id": "turn_first_001""# : ""
        let json = """
        {
          "schema_version": "1.0",
          "scenario_id": "golden_001",
          "session_id": "\(sessionId)",
          "mode": "golden_deterministic",
          "status": "active",
          "story_revision": \(storyRevision),
          "turn": \(turn),
          "observed_store_revision": \(storeRevision),
          "world_time": "1899-03-01T08:00:00Z",
          "protagonist": {"id": "char_evelyn_gray", "display_name": "伊芙琳·格雷"},
          "scene": {"id": "consultation_room", "location_id": "harvey_clinic",
                    "display_name": "哈维诊所 · 诊室"},
          "discovered_clues": \(clues),
          "can_submit": \(canSubmit)
          \(lastTurn)
        }
        """
        return try JSONDecoder().decode(StoryPublicViewDTO.self, from: Data(json.utf8))
    }

    static func entry(session: StoryPublicViewDTO? = nil,
                      pendingInputTurnId: String? = nil,
                      storeRevision: Int = 0) throws -> StoryEntryViewDTO {
        let sessionJSON = session.map { view -> String in
            let data = try? JSONEncoder().encode(view)
            return data.flatMap { String(data: $0, encoding: .utf8) } ?? "null"
        } ?? "null"
        let pending = pendingInputTurnId.map { #", "pending_input_turn_id": "\#($0)""# } ?? ""
        let json = """
        {
          "schema_version": "1.0",
          "scenario_id": "golden_001",
          "mode": "golden_deterministic",
          "supported_advice": ["先别问医生病人的事，我想看看他的反应。"],
          "observed_store_revision": \(storeRevision)
          \(session == nil ? "" : #", "session": \#(sessionJSON)"#)
          \(pending)
        }
        """
        return try JSONDecoder().decode(StoryEntryViewDTO.self, from: Data(json.utf8))
    }

    static func submitResult() throws -> StoryAdviceSubmitViewDTO {
        let json = """
        {
          "schema_version": "1.0",
          "receipt": {
            "input_turn_id": "input_turn_1",
            "session_id": "session_1",
            "turn_id": "turn_first_001",
            "status": "committed",
            "committed_store_revision": 2,
            "committed_story_revision": 1
          },
          "session": {
            "schema_version": "1.0",
            "scenario_id": "golden_001",
            "session_id": "session_1",
            "mode": "golden_deterministic",
            "status": "active",
            "story_revision": 1,
            "turn": 1,
            "observed_store_revision": 2,
            "world_time": "1899-03-01T08:00:00Z",
            "protagonist": {"id": "char_evelyn_gray", "display_name": "伊芙琳·格雷"},
            "scene": {"id": "consultation_room", "location_id": "harvey_clinic",
                      "display_name": "哈维诊所 · 诊室"},
            "discovered_clues": [{"id": "clue_doctor_pause", "display_name": "医生的停顿"}],
            "can_submit": false,
            "last_committed_turn_id": "turn_first_001"
          },
          "replayed": false
        }
        """
        return try JSONDecoder().decode(StoryAdviceSubmitViewDTO.self, from: Data(json.utf8))
    }

    static func adviceFound(committed: Bool = true) throws -> StoryAdviceGetViewDTO {
        let status = committed ? "committed" : "received"
        let committedFields = committed
            ? #", "committed_store_revision": 2, "committed_story_revision": 1"#
            : ""
        let json = """
        {
          "schema_version": "1.0",
          "found": true,
          "receipt": {
            "input_turn_id": "input_turn_1",
            "session_id": "session_1",
            "turn_id": "turn_first_001",
            "status": "\(status)"
            \(committedFields)
          },
          "replayed": true
        }
        """
        return try JSONDecoder().decode(StoryAdviceGetViewDTO.self, from: Data(json.utf8))
    }

    static func makeModel(
        log: StoryCallLog, journal: MemoryStoryJournal,
        entryView: StoryEntryViewDTO, openView: StoryOpenViewDTO,
        submitView: StoryAdviceSubmitViewDTO?, adviceView: StoryAdviceGetViewDTO,
        ids: [String] = ["open_1", "input_turn_1"]
    ) -> (StorySessionModel, FakeStoryClient) {
        let client = FakeStoryClient(log: log, journal: journal, entryView: entryView,
                                     openView: openView, submitView: submitView,
                                     adviceView: adviceView)
        let box = IDBox(values: ids)
        let model = StorySessionModel(client: client, journal: journal,
                                      idFactory: { box.next() })
        return (model, client)
    }

    @Test("Opening writes the frozen intent before sending the mutation")
    func journalPrecedesOpenMutation() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let (model, _) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(), openView: try StoryOpenViewDTO(
                session: Self.view(), openedStoreRevision: 1, replayed: false),
            submitView: try Self.submitResult(), adviceView: try Self.adviceFound())
        await model.refreshEntry()
        #expect(model.state == .notStarted)
        await model.startStory()
        #expect(model.state == .ready)
        let record = try journal.load()
        #expect(record?.sessionId == "session_1")
        #expect(log.values.contains("client.open"))
        #expect(log.values.first == "client.entry")
    }

    @Test("Journal write failure never sends the mutation")
    func journalFailureBlocksMutation() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let (model, _) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(), openView: try StoryOpenViewDTO(
                session: Self.view(), openedStoreRevision: 1, replayed: false),
            submitView: try Self.submitResult(), adviceView: try Self.adviceFound())
        await model.refreshEntry()
        journal.failNextWrites(true)
        await model.startStory()
        #expect(model.state == .failed(code: "journal_unavailable"))
        #expect(!log.values.contains("client.open"))
    }

    @Test("First turn completes once and then refuses a second submission")
    func firstTurnIsSingleShot() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let (model, _) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(session: Self.view()),
            openView: try StoryOpenViewDTO(session: Self.view(), openedStoreRevision: 1,
                                           replayed: false),
            submitView: try Self.submitResult(), adviceView: try Self.adviceFound())
        await model.refreshEntry()
        #expect(model.state == .ready)
        model.fillSupportedAdvice()
        await model.submit()
        #expect(model.state == .completed)
        #expect(model.isFirstTurnSaved)
        #expect(model.draft.isEmpty)
        #expect(model.view?.discoveredClues.first?.displayName == "医生的停顿")
        #expect(!model.canSubmitStory)
        await model.submit()
        #expect(log.values.filter { $0 == "client.submit" }.count == 1)
    }

    @Test("Unsupported text keeps the draft and drops the frozen identity")
    func unsupportedTextKeepsDraft() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let (model, client) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(session: Self.view()),
            openView: try StoryOpenViewDTO(session: Self.view(), openedStoreRevision: 1,
                                           replayed: false),
            submitView: try Self.submitResult(), adviceView: try Self.adviceFound())
        await model.refreshEntry()
        client.setSubmitError(StoryControlServiceError(
            code: "deterministic_input_unsupported", retryable: false))
        model.draft = "换一句别的话"
        await model.submit()
        #expect(model.state == .failed(code: "deterministic_input_unsupported"))
        #expect(model.draft == "换一句别的话")
        #expect(try journal.load() == nil)
        #expect(!model.canRecover)
    }

    @Test("An unknown outcome is recovered by reading, never by resubmitting")
    func unknownOutcomeRecoversByReading() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let (model, client) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(session: Self.view()),
            openView: try StoryOpenViewDTO(session: Self.view(), openedStoreRevision: 1,
                                           replayed: false),
            submitView: try Self.submitResult(), adviceView: try Self.adviceFound())
        await model.refreshEntry()
        client.setSubmitError(EngineConnectionError.timedOut)
        model.draft = "先别问医生病人的事，我想看看他的反应。"
        await model.submit()
        #expect(model.state == .recovering)
        #expect(log.values.filter { $0 == "client.submit" }.count == 1)

        client.setAdvice(try Self.adviceFound(committed: true))
        await model.recover()
        #expect(model.state == .completed)
        #expect(log.values.filter { $0 == "client.submit" }.count == 1)
        #expect(log.values.contains("client.advice"))
    }

    @Test("A received request stays pending until the user continues explicitly")
    func receivedRequestStaysPending() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let (model, client) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(session: Self.view()),
            openView: try StoryOpenViewDTO(session: Self.view(), openedStoreRevision: 1,
                                           replayed: false),
            submitView: try Self.submitResult(), adviceView: try Self.adviceFound(committed: false))
        await model.refreshEntry()
        client.setSubmitError(EngineConnectionError.timedOut)
        model.draft = "先别问医生病人的事，我想看看他的反应。"
        await model.submit()
        await model.recover()
        #expect(model.state == .pending)
        #expect(!model.canRecover)
        #expect(model.statusText == "请求已记录，尚未提交")

        client.setSubmitError(nil)
        await model.continuePendingRequest()
        #expect(model.state == .completed)
        #expect(log.values.filter { $0 == "client.submit" }.count == 2)
    }

    @Test("Server-side pending without frozen text cannot be continued implicitly")
    func pendingWithoutFrozenTextIsReadOnly() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let (model, _) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(pendingInputTurnId: "input_turn_1"),
            openView: try StoryOpenViewDTO(session: Self.view(), openedStoreRevision: 1,
                                           replayed: false),
            submitView: try Self.submitResult(), adviceView: try Self.adviceFound())
        await model.refreshEntry()
        #expect(model.state == .pending)
        #expect(!model.canStartStory)
        #expect(!model.canSubmitStory)
        #expect(!model.canRecover)
    }

    @Test("A connection change discards in-flight results")
    func staleGenerationIsDiscarded() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let (model, client) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(session: Self.view()),
            openView: try StoryOpenViewDTO(session: Self.view(), openedStoreRevision: 1,
                                           replayed: false),
            submitView: try Self.submitResult(), adviceView: try Self.adviceFound())
        await model.refreshEntry()
        model.draft = "先别问医生病人的事，我想看看他的反应。"
        client.setSubmitError(EngineConnectionError.timedOut)
        await model.submit()
        #expect(model.state == .recovering)
        model.detachForConnectionChange()
        #expect(model.state == .unavailable)
        client.setAdvice(try Self.adviceFound(committed: true))
        await model.recover()
        #expect(model.state == .unavailable)
    }

    @Test("Recovery for an unknown input offers an explicit retry of the same identity")
    func unknownInputOffersExplicitRetry() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let (model, client) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(session: Self.view()),
            openView: try StoryOpenViewDTO(session: Self.view(), openedStoreRevision: 1,
                                           replayed: false),
            submitView: try Self.submitResult(), adviceView: try Self.adviceFound())
        await model.refreshEntry()
        client.setSubmitError(EngineConnectionError.timedOut)
        model.draft = "先别问医生病人的事，我想看看他的反应。"
        await model.submit()
        let notFound = """
        {"schema_version": "1.0", "found": false, "replayed": false}
        """
        client.setAdvice(try JSONDecoder().decode(
            StoryAdviceGetViewDTO.self, from: Data(notFound.utf8)))
        await model.recover()
        #expect(model.state == .failed(code: "input_not_found"))
        #expect(model.canRetrySameRequest)
        #expect(model.statusText == "未查到提交记录，可显式重试同一请求")

        client.setAdvice(try Self.adviceFound(committed: true))
        client.setSubmitError(nil)
        await model.retryFrozenSubmission()
        #expect(model.state == .completed)
    }
}

final class IDBox: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [String]

    init(values: [String]) { self.values = values }

    func next() -> String {
        lock.lock(); defer { lock.unlock() }
        return values.isEmpty ? UUID().uuidString : values.removeFirst()
    }
}
