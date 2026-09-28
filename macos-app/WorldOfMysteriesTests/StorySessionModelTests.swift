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
    private var entryView: StoryEntryViewDTO
    private let openView: StoryOpenViewDTO

    private var submitView: StoryAdviceSubmitViewDTO?
    private var submitQueue: [StoryAdviceSubmitViewDTO] = []
    private var adviceView: StoryAdviceGetViewDTO
    private var submitError: (any Error)?
    private var openError: (any Error)?
    private var expressionAvailable = false
    private var expressionResponse: StoryExpressionGetResponseDTO?
    private var expressionError: (any Error)?
    private var gateStream: AsyncStream<Void>?
    private var gateContinuation: AsyncStream<Void>.Continuation?
    private var expressionGateStream: AsyncStream<Void>?
    private var expressionGateContinuation: AsyncStream<Void>.Continuation?

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
    func setEntryView(_ view: StoryEntryViewDTO) { lock.withLock { entryView = view } }
    func setExpressionAvailable(_ available: Bool) {
        lock.withLock { expressionAvailable = available }
    }
    func setExpressionResponse(_ response: StoryExpressionGetResponseDTO?) {
        lock.withLock { expressionResponse = response }
    }
    func setExpressionError(_ error: (any Error)?) {
        lock.withLock { expressionError = error }
    }
    /// Queued results model the Engine's per-turn views: each fixed turn
    /// commits its own revision and advertises the next advice.
    func enqueueSubmitView(_ view: StoryAdviceSubmitViewDTO) { lock.withLock { submitQueue.append(view) } }
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

    func holdExpression() {
        let pair = AsyncStream<Void>.makeStream()
        lock.withLock {
            expressionGateStream = pair.stream
            expressionGateContinuation = pair.continuation
        }
    }

    func releaseExpression() {
        let continuation = lock.withLock { () -> AsyncStream<Void>.Continuation? in
            let value = expressionGateContinuation
            expressionGateContinuation = nil
            expressionGateStream = nil
            return value
        }
        continuation?.finish()
    }

    func supportsStoryExpression() async -> Bool {
        lock.withLock { expressionAvailable }
    }

    var submittedCount: Int { log.values.filter { $0 == "client.submit" }.count }

    func storyEntry(scenarioId: String) async throws -> StoryEntryViewDTO {
        log.append("client.entry")
        return lock.withLock { entryView }
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
        let state = lock.withLock { () -> (AsyncStream<Void>?, (any Error)?, StoryAdviceSubmitViewDTO?) in
            let next = submitQueue.isEmpty ? submitView : submitQueue.removeFirst()
            return (gateStream, submitError, next)
        }
        if let gate = state.0 { for await _ in gate { break } }
        if let error = state.1 { throw error }
        guard let view = state.2 else { throw EngineConnectionError.invalidFrame }
        return view
    }

    func storyAdvice(sessionId: String, inputTurnId: String) async throws -> StoryAdviceGetViewDTO {
        log.append("client.advice")
        return lock.withLock { adviceView }
    }

    func storyExpressionGet(
        sessionId: String,
        turnId: String
    ) async throws -> StoryExpressionGetResponseDTO {
        log.append("client.expression")
        let state = lock.withLock {
            (expressionGateStream, expressionError, expressionResponse)
        }
        if let gate = state.0 {
            for await _ in gate { break }
        }
        if let error = state.1 { throw error }
        guard let response = state.2 else { throw EngineConnectionError.invalidFrame }
        return response
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

    static let firstAdvice = "先别问医生病人的事，我想看看他的反应。"
    static let turnAdvice = [
        "先别问医生病人的事，我想看看他的反应。",
        "我注意到他的手一直插在口袋里。",
        "把话题引向诊所楼下的传闻。",
        "追问他刚才停顿时在想什么。",
        "直接告诉他我知道他隐瞒了什么。",
    ]

    static func advice(forTurn turn: Int) -> String { turnAdvice[turn - 1] }

    static func entry(session: StoryPublicViewDTO? = nil,
                      pendingInputTurnId: String? = nil,
                      storeRevision: Int = 0,
                      advice: [String]? = nil) throws -> StoryEntryViewDTO {
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
          "supported_advice": \(adviceJSON(advice ?? [firstAdvice])),
          "observed_store_revision": \(storeRevision)
          \(session == nil ? "" : #", "session": \#(sessionJSON)"#)
          \(pending)
        }
        """
        return try JSONDecoder().decode(StoryEntryViewDTO.self, from: Data(json.utf8))
    }

    static func adviceJSON(_ advice: [String]) -> String {
        "[" + advice.map { "\"\($0)\"" }.joined(separator: ", ") + "]"
    }

    /// Committed fixed turn `turn`: story revision equals the turn number, the
    /// store revision advances independently, and `can_submit` stays true until
    /// the fifth turn closes the run.
    static func submitResult(
        turn: Int = 1,
        canSubmit: Bool? = nil,
        delivery: StoryTurnDeliveryDTO? = nil
    ) throws -> StoryAdviceSubmitViewDTO {
        let open = canSubmit ?? (turn < 5)
        let json = """
        {
          "schema_version": "1.0",
          "receipt": {
            "input_turn_id": "input_turn_1",
            "session_id": "session_1",
            "turn_id": "turn_first_001",
            "status": "committed",
            "committed_store_revision": \(turn + 1),
            "committed_story_revision": \(turn)
          },
          "session": \(sessionJSON(turn: turn, storeRevision: turn + 1, canSubmit: open)),
          "replayed": false
        }
        """
        let decoded = try JSONDecoder().decode(StoryAdviceSubmitViewDTO.self, from: Data(json.utf8))
        guard let delivery else { return decoded }
        return StoryAdviceSubmitViewDTO(
            schemaVersion: decoded.schemaVersion,
            receipt: decoded.receipt,
            session: decoded.session,
            replayed: decoded.replayed,
            delivery: delivery
        )
    }

    static func expressionResult(
        sessionId: String = "session_1",
        turnId: String = "turn_first_001",
        state: String = "ready"
    ) throws -> StoryExpressionGetResponseDTO {
        let segments = state == "ready"
            ? #""segments":[{"type":"narration","text":"雨停了。"},{"type":"character","speaker_display_name":"伊芙琳·格雷","text":"我明白了。"}]"#
            : #""segments":[],"reason":"expression_unavailable""#
        let json = """
        {
          "schema_version": "1.0",
          "session_id": "\(sessionId)",
          "turn_id": "\(turnId)",
          "narrative_state": "\(state)",
          \(segments)
        }
        """
        return try JSONDecoder().decode(
            StoryExpressionGetResponseDTO.self,
            from: Data(json.utf8)
        )
    }

    static func sessionJSON(turn: Int, storeRevision: Int, canSubmit: Bool) -> String {
        let clues = turn > 0
            ? #"[{"id": "clue_doctor_pause", "display_name": "医生的停顿"}]"#
            : "[]"
        let lastTurn = turn > 0 ? #", "last_committed_turn_id": "turn_first_001""# : ""
        return """
        {
          "schema_version": "1.0",
          "scenario_id": "golden_001",
          "session_id": "session_1",
          "mode": "golden_deterministic",
          "status": "active",
          "story_revision": \(turn),
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
    }

    static func adviceFound(committed: Bool = true,
                            session: StoryPublicViewDTO? = nil) throws -> StoryAdviceGetViewDTO {
        let status = committed ? "committed" : "received"
        let committedFields = committed
            ? #", "committed_store_revision": 2, "committed_story_revision": 1"#
            : ""
        let sessionField = session.map { #", "session": \#(sessionJSON(turn: $0.turn, storeRevision: $0.observedStoreRevision, canSubmit: $0.canSubmit))"# } ?? ""
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
          }
          \(sessionField),
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

    @Test("A committed turn reopens the next fixed turn instead of closing the run")
    func committedTurnReopensNextFixedTurn() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let (model, client) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(session: Self.view()),
            openView: try StoryOpenViewDTO(session: Self.view(), openedStoreRevision: 1,
                                           replayed: false),
            submitView: try Self.submitResult(turn: 1), adviceView: try Self.adviceFound())
        await model.refreshEntry()
        #expect(model.state == .ready)
        #expect(!model.isFirstTurnSaved)
        model.fillSupportedAdvice()
        // The post-commit read observes the just-committed turn and advertises
        // exactly the next fixed advice.
        client.setEntryView(try Self.entry(
            session: Self.view(turn: 1, storyRevision: 1, storeRevision: 2),
            storeRevision: 2, advice: [Self.advice(forTurn: 2)]))
        await model.submit()
        #expect(model.state == .ready)
        #expect(model.isFirstTurnSaved)
        #expect(!model.isFixedRunComplete)
        #expect(model.draft.isEmpty)
        #expect(model.view?.turn == 1)
        #expect(model.view?.discoveredClues.first?.displayName == "医生的停顿")
        #expect(model.supportedAdvice == [Self.advice(forTurn: 2)])
        #expect(model.statusText == "填入第 2 轮建议后提交")
        #expect(!model.canSubmitStory)
    }

    /// Regression: the real `StorySessionPanel` composer wiring must still reach
    /// the Engine.
    ///
    /// `AdviceDraftSubmission` empties the binding *synchronously* as soon as the
    /// handler returns, and the panel's handler only *enqueues* an async
    /// submission. A handler that re-reads `model.draft` therefore always sees an
    /// empty string, fails the `canSubmitStory` guard and silently drops the
    /// advice — which is exactly what a human clicking 提交建议 did in the GUI.
    @Test("The real composer wiring still submits after it empties the binding")
    func composerDeliverySurvivesOptimisticDraftClear() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let (model, client) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(session: Self.view()),
            openView: try StoryOpenViewDTO(session: Self.view(), openedStoreRevision: 1,
                                           replayed: false),
            submitView: try Self.submitResult(turn: 1), adviceView: try Self.adviceFound())
        await model.refreshEntry()
        #expect(model.state == .ready)
        client.setEntryView(try Self.entry(
            session: Self.view(turn: 1, storyRevision: 1, storeRevision: 2),
            storeRevision: 2, advice: [Self.advice(forTurn: 2)]))

        model.fillSupportedAdvice()
        #expect(model.draft == Self.advice(forTurn: 1))

        // Exactly how StorySessionPanel drives AdviceInputField.
        let delivered = AdviceDraftSubmission.submit(
            readDraft: { model.draft },
            writeDraft: { model.draft = $0 },
            isEnabled: true,
            handler: { advice in
                Task { @MainActor in await model.submit(advice: advice) }
            })
        #expect(delivered)
        // The composer already cleared the binding before the Task body runs.
        #expect(model.draft.isEmpty)

        // Bounded wait for the *outcome*, not for the call: the client logs
        // `client.submit` before the Engine answers, so waiting on the call
        // would race the response under load. A handler that lost the advice
        // never commits, and must fail the assertions instead of hanging.
        for _ in 0..<200 {
            if model.view?.turn == 1 { break }
            try? await Task.sleep(for: .milliseconds(10))
        }
        #expect(log.values.contains("client.submit"))
        #expect(model.view?.turn == 1)
        #expect(model.statusText == "填入第 2 轮建议后提交")
    }

    @Test("Five fixed turns commit in order and close after the fifth")
    func fiveTurnsRunToCompletion() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let (model, client) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(session: Self.view()),
            openView: try StoryOpenViewDTO(session: Self.view(), openedStoreRevision: 1,
                                           replayed: false),
            submitView: nil,
            adviceView: try Self.adviceFound(session: Self.view(
                turn: 5, storyRevision: 5, storeRevision: 6, canSubmit: false)))
        client.setEntryView(try Self.entry(session: Self.view(), advice: [Self.advice(forTurn: 1)]))
        await model.refreshEntry()
        #expect(model.state == .ready)

        for turn in 1...5 {
            #expect(model.state == .ready)
            #expect(model.view?.turn == turn - 1)
            #expect(model.supportedAdvice == [Self.advice(forTurn: turn)])
            model.fillSupportedAdvice()
            #expect(model.draft == Self.advice(forTurn: turn))
            client.enqueueSubmitView(try Self.submitResult(turn: turn))
            // The post-commit read observes the just-committed turn.
            client.setEntryView(try Self.entry(
                session: Self.view(turn: turn, storyRevision: turn, storeRevision: turn + 1,
                                   canSubmit: turn < 5),
                storeRevision: turn + 1,
                advice: turn < 5 ? [Self.advice(forTurn: turn + 1)] : []))
            await model.submit()
            #expect(model.draft.isEmpty)
            #expect(model.view?.storyRevision == turn)
            if turn < 5 {
                #expect(model.state == .ready)
                #expect(!model.isFixedRunComplete)
            } else {
                #expect(model.state == .completed)
                #expect(model.isFixedRunComplete)
            }
        }
        #expect(model.supportedAdvice.isEmpty)
        #expect(!model.canSubmitStory)
        #expect(model.statusText == "第 5 轮已保存 · 固定五轮验证已完成")
        model.fillSupportedAdvice()
        #expect(model.draft.isEmpty)
        await model.submit()
        #expect(log.values.filter { $0 == "client.submit" }.count == 5)
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
        client.setExpressionAvailable(true)
        client.setExpressionResponse(try Self.expressionResult())
        await model.refreshEntry()
        client.setSubmitError(EngineConnectionError.timedOut)
        model.draft = "先别问医生病人的事，我想看看他的反应。"
        await model.submit()
        #expect(model.state == .recovering)
        #expect(log.values.filter { $0 == "client.submit" }.count == 1)

        // The read-only recovery adopts the committed view the Engine reports.
        client.setAdvice(try Self.adviceFound(
            committed: true,
            session: Self.view(turn: 1, storyRevision: 1, storeRevision: 2)))
        await model.recover()
        #expect(model.state == .ready)
        #expect(model.view?.turn == 1)
        #expect(log.values.filter { $0 == "client.submit" }.count == 1)
        #expect(log.values.contains("client.advice"))
        #expect(model.expression?.narrativeState == .ready)
        #expect(log.values.filter { $0 == "client.expression" }.count == 1)
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
        client.setEntryView(try Self.entry(
            session: Self.view(turn: 1, storyRevision: 1, storeRevision: 2),
            storeRevision: 2, advice: [Self.advice(forTurn: 2)]))
        await model.continuePendingRequest()
        #expect(model.state == .ready)
        #expect(model.view?.turn == 1)
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

    @Test("Audio unavailable after commit still displays the persisted text")
    func audioUnavailableDoesNotHidePersistedExpression() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let audioUnavailable = try StoryTurnDeliveryDTO(
            state: .unavailable,
            reason: "voice_unavailable"
        )
        let (model, client) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(session: Self.view()),
            openView: try StoryOpenViewDTO(session: Self.view(), openedStoreRevision: 1,
                                           replayed: false),
            submitView: try Self.submitResult(turn: 1, delivery: audioUnavailable),
            adviceView: try Self.adviceFound())
        client.setExpressionAvailable(true)
        client.setExpressionResponse(try Self.expressionResult())
        await model.refreshEntry()
        client.setEntryView(try Self.entry(
            session: Self.view(turn: 1, storyRevision: 1, storeRevision: 2),
            storeRevision: 2, advice: [Self.advice(forTurn: 2)]))
        model.draft = Self.advice(forTurn: 1)

        await model.submit()

        #expect(model.view?.turn == 1)
        #expect(model.expression?.narrativeState == .ready)
        #expect(model.expression?.segments.map(\.text) == ["雨停了。", "我明白了。"])
        #expect(model.audioUnavailableReason == "voice_unavailable")
        #expect(log.values.filter { $0 == "client.submit" }.count == 1)
        #expect(log.values.filter { $0 == "client.expression" }.count == 1)
    }

    @Test("Expression read failure never resubmits or labels a committed turn unsaved")
    func expressionReadFailureIsReadOnly() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let audioUnavailable = try StoryTurnDeliveryDTO(
            state: .unavailable,
            reason: "voice_unavailable"
        )
        let (model, client) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(session: Self.view()),
            openView: try StoryOpenViewDTO(session: Self.view(), openedStoreRevision: 1,
                                           replayed: false),
            submitView: try Self.submitResult(turn: 1, delivery: audioUnavailable),
            adviceView: try Self.adviceFound())
        client.setExpressionAvailable(true)
        client.setExpressionError(EngineConnectionError.timedOut)
        await model.refreshEntry()
        client.setEntryView(try Self.entry(
            session: Self.view(turn: 1, storyRevision: 1, storeRevision: 2),
            storeRevision: 2, advice: [Self.advice(forTurn: 2)]))
        model.draft = Self.advice(forTurn: 1)

        await model.submit()

        #expect(model.view?.turn == 1)
        #expect(model.expressionReadFailed)
        #expect(model.state == .ready)
        #expect(!model.statusText.contains("未保存"))
        #expect(log.values.filter { $0 == "client.submit" }.count == 1)
        #expect(log.values.filter { $0 == "client.expression" }.count == 1)
    }

    @Test("Restoring a committed session refreshes its expression without resubmitting")
    func restoredSessionRefreshesExpressionReadOnly() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let session = try Self.view(turn: 1, storyRevision: 1, storeRevision: 2)
        let (model, client) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(
                session: session, storeRevision: 2, advice: [Self.advice(forTurn: 2)]),
            openView: StoryOpenViewDTO(session: session, openedStoreRevision: 2,
                                       replayed: false),
            submitView: nil,
            adviceView: try Self.adviceFound())
        client.setExpressionAvailable(true)
        client.setExpressionResponse(try Self.expressionResult())

        await model.refreshEntry()

        #expect(model.view?.sessionId == "session_1")
        #expect(model.view?.turn == 1)
        #expect(model.expression?.narrativeState == .ready)
        #expect(log.values.filter { $0 == "client.submit" }.isEmpty)
        #expect(log.values.filter { $0 == "client.expression" }.count == 1)
    }

    @Test("Expression query is skipped when the Engine did not advertise its capability")
    func missingExpressionCapabilityDegradesWithoutCallingMethod() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let audioUnavailable = try StoryTurnDeliveryDTO(
            state: .unavailable,
            reason: "voice_unavailable"
        )
        let (model, client) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(session: Self.view()),
            openView: try StoryOpenViewDTO(session: Self.view(), openedStoreRevision: 1,
                                           replayed: false),
            submitView: try Self.submitResult(turn: 1, delivery: audioUnavailable),
            adviceView: try Self.adviceFound())
        client.setExpressionAvailable(false)
        await model.refreshEntry()
        client.setEntryView(try Self.entry(
            session: Self.view(turn: 1, storyRevision: 1, storeRevision: 2),
            storeRevision: 2, advice: [Self.advice(forTurn: 2)]))
        model.draft = Self.advice(forTurn: 1)

        await model.submit()

        #expect(model.view?.turn == 1)
        #expect(model.expression == nil)
        #expect(!model.expressionReadFailed)
        #expect(log.values.filter { $0 == "client.submit" }.count == 1)
        #expect(log.values.filter { $0 == "client.expression" }.isEmpty)
    }

    @Test("Expression replies for another session are discarded")
    func mismatchedExpressionSessionIsDiscarded() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let (model, client) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(
                session: Self.view(turn: 1, storyRevision: 1, storeRevision: 2),
                storeRevision: 2, advice: [Self.advice(forTurn: 2)]),
            openView: try StoryOpenViewDTO(session: Self.view(), openedStoreRevision: 1,
                                           replayed: false),
            submitView: nil,
            adviceView: try Self.adviceFound())
        client.setExpressionAvailable(true)
        client.setExpressionResponse(try Self.expressionResult(sessionId: "session_other"))

        await model.refreshEntry()

        #expect(model.view?.sessionId == "session_1")
        #expect(model.expression == nil)
        #expect(model.expressionReadFailed)
    }

    @Test("Expression replies from an earlier connection generation are discarded")
    func staleExpressionGenerationIsDiscarded() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let session = try Self.view(turn: 1, storyRevision: 1, storeRevision: 2)
        let (model, client) = Self.makeModel(
            log: log, journal: journal,
            entryView: try Self.entry(
                session: session, storeRevision: 2, advice: [Self.advice(forTurn: 2)]),
            openView: StoryOpenViewDTO(session: session, openedStoreRevision: 2,
                                       replayed: false),
            submitView: nil,
            adviceView: try Self.adviceFound())
        client.setExpressionAvailable(true)
        client.setExpressionResponse(try Self.expressionResult())
        client.holdExpression()

        let refresh = Task { await model.refreshEntry() }
        for _ in 0..<200 {
            if log.values.contains("client.expression") { break }
            try? await Task.sleep(for: .milliseconds(10))
        }
        #expect(log.values.contains("client.expression"))

        model.detachForConnectionChange()
        client.releaseExpression()
        await refresh.value

        #expect(model.state == .unavailable)
        #expect(model.expression == nil)
        #expect(!model.expressionReadFailed)
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

        client.setAdvice(try Self.adviceFound(
            committed: true,
            session: Self.view(turn: 1, storyRevision: 1, storeRevision: 2)))
        client.setSubmitError(nil)
        client.setEntryView(try Self.entry(
            session: Self.view(turn: 1, storyRevision: 1, storeRevision: 2),
            storeRevision: 2, advice: [Self.advice(forTurn: 2)]))
        await model.retryFrozenSubmission()
        #expect(model.state == .ready)
        #expect(model.view?.turn == 1)
        #expect(log.values.filter { $0 == "client.submit" }.count == 2)
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
