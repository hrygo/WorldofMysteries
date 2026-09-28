import Foundation
import Testing
@testable import WorldOfMysteriesCore

private final class CoordinatorJournal: StoryJournalWriting, @unchecked Sendable {
    private let lock = NSLock()
    private var storedRecord: StoryRequestRecord?
    private var shouldFailWrites = false

    func failWrites(_ value: Bool) {
        lock.withLock { shouldFailWrites = value }
    }

    func load() throws -> StoryRequestRecord? {
        lock.withLock { storedRecord }
    }

    func save(_ record: StoryRequestRecord) throws {
        try lock.withLock {
            if shouldFailWrites { throw JournalWriteFailure.failed }
            storedRecord = record
        }
    }

    func clear() throws {
        lock.withLock { storedRecord = nil }
    }
}

private enum JournalWriteFailure: Error {
    case failed
}

private final class CoordinatorSubmissionClient: StorySubmissionClient, @unchecked Sendable {
    private let lock = NSLock()
    private let journal: any StoryJournalWriting
    private var textRequests: [StoryAdviceSubmitRequestDTO] = []
    private var voiceRequests: [StoryTurnSubmitRequestDTO] = []
    private var queries: [(String, String)] = []
    private var submitFailure: (any Error)?
    private var queryFailure: (any Error)?
    private var response: StoryAdviceSubmitViewDTO?
    private var advice: StoryAdviceGetViewDTO?
    private var recordObservedBeforeSend: StoryRequestRecord?
    private var startContinuation: AsyncStream<Void>.Continuation?
    private var submissionGate: AsyncStream<Void>?
    private var gateContinuation: AsyncStream<Void>.Continuation?

    init(journal: any StoryJournalWriting) {
        self.journal = journal
    }

    var textSubmissionRequests: [StoryAdviceSubmitRequestDTO] {
        lock.withLock { textRequests }
    }

    var voiceSubmissionRequests: [StoryTurnSubmitRequestDTO] {
        lock.withLock { voiceRequests }
    }

    var adviceQueries: [(String, String)] {
        lock.withLock { queries }
    }

    var savedRecordAtSend: StoryRequestRecord? {
        lock.withLock { recordObservedBeforeSend }
    }

    func setSubmitFailure(_ error: (any Error)?) {
        lock.withLock { submitFailure = error }
    }

    func setQueryFailure(_ error: (any Error)?) {
        lock.withLock { queryFailure = error }
    }

    func setResponse(_ value: StoryAdviceSubmitViewDTO?) {
        lock.withLock { response = value }
    }

    func setAdvice(_ value: StoryAdviceGetViewDTO?) {
        lock.withLock { advice = value }
    }

    func holdNextSubmission() -> AsyncStream<Void> {
        let started = AsyncStream<Void>.makeStream()
        let gate = AsyncStream<Void>.makeStream()
        lock.withLock {
            startContinuation = started.continuation
            submissionGate = gate.stream
            gateContinuation = gate.continuation
        }
        return started.stream
    }

    func releaseSubmission() {
        let continuation = lock.withLock { () -> AsyncStream<Void>.Continuation? in
            let value = gateContinuation
            gateContinuation = nil
            submissionGate = nil
            return value
        }
        continuation?.finish()
    }

    func storySubmit(
        _ request: StoryAdviceSubmitRequestDTO
    ) async throws -> StoryAdviceSubmitViewDTO {
        let state = lock.withLock { () -> ((any Error)?, StoryAdviceSubmitViewDTO?,
                                           AsyncStream<Void>?, AsyncStream<Void>?,
                                           AsyncStream<Void>.Continuation?) in
            textRequests.append(request)
            recordObservedBeforeSend = try? journal.load()
            let started = startContinuation
            startContinuation = nil
            return (submitFailure, response, submissionGate, nil, started)
        }
        state.4?.yield(())
        if let gate = state.2 {
            for await _ in gate { break }
        }
        if let error = state.0 { throw error }
        guard let response = state.1 else { throw EngineConnectionError.invalidFrame }
        return response
    }

    func storyTurnSubmit(
        _ request: StoryTurnSubmitRequestDTO
    ) async throws -> StoryAdviceSubmitViewDTO {
        let state = lock.withLock { () -> ((any Error)?, StoryAdviceSubmitViewDTO?,
                                           AsyncStream<Void>?, AsyncStream<Void>.Continuation?) in
            voiceRequests.append(request)
            recordObservedBeforeSend = try? journal.load()
            let started = startContinuation
            startContinuation = nil
            return (submitFailure, response, submissionGate, started)
        }
        state.3?.yield(())
        if let gate = state.2 {
            for await _ in gate { break }
        }
        if let error = state.0 { throw error }
        guard let response = state.1 else { throw EngineConnectionError.invalidFrame }
        return response
    }

    func storyAdvice(
        sessionId: String,
        inputTurnId: String
    ) async throws -> StoryAdviceGetViewDTO {
        let state = lock.withLock { () -> ((any Error)?, StoryAdviceGetViewDTO?) in
            queries.append((sessionId, inputTurnId))
            return (queryFailure, advice)
        }
        if let error = state.0 { throw error }
        guard let advice = state.1 else { throw EngineConnectionError.invalidFrame }
        return advice
    }
}

@MainActor
@Suite("Unified story submission coordinator")
struct StorySubmissionCoordinatorTests {
    private func notFound() throws -> StoryAdviceGetViewDTO {
        try JSONDecoder().decode(
            StoryAdviceGetViewDTO.self,
            from: Data(#"{"schema_version":"1.0","found":false,"replayed":false}"#.utf8)
        )
    }

    private func makeCoordinator(
        mode: StoryInputMode,
        journal: CoordinatorJournal,
        client: CoordinatorSubmissionClient
    ) -> StorySubmissionCoordinator {
        StorySubmissionCoordinator(
            client: client,
            journal: journal,
            idFactory: { "input_turn_1" }
        )
    }

    private func submit(
        _ coordinator: StorySubmissionCoordinator,
        mode: StoryInputMode,
        rawInput: String = "先看看医生的反应。"
    ) async {
        _ = await coordinator.submit(
            rawInput: rawInput,
            inputMode: mode,
            sessionId: "session_1",
            expectedStoryRevision: 0,
            expectedStoreRevision: 1
        )
    }

    @Test("Text and voice recover a lost ACK by querying the frozen identity", arguments: [
        StoryInputMode.text, StoryInputMode.voice,
    ])
    func lostAckQueriesSameFrozenIdentity(mode: StoryInputMode) async throws {
        let journal = CoordinatorJournal()
        let client = CoordinatorSubmissionClient(journal: journal)
        client.setSubmitFailure(EngineConnectionError.timedOut)
        client.setAdvice(try StorySessionModelTests.adviceFound(committed: true))
        client.setResponse(try StorySessionModelTests.submitResult())
        let coordinator = makeCoordinator(mode: mode, journal: journal, client: client)

        await submit(coordinator, mode: mode)

        #expect(coordinator.state == .committed)
        #expect(client.textSubmissionRequests.count + client.voiceSubmissionRequests.count == 1)
        #expect(client.adviceQueries.count == 1)
        #expect(client.adviceQueries.first?.1 == "input_turn_1")
        #expect(client.savedRecordAtSend?.inputTurnId == "input_turn_1")
        #expect(client.savedRecordAtSend?.inputMode == mode)
        #expect(client.savedRecordAtSend?.submissionMethod == (
            mode == .voice ? .storyTurnSubmit : .storyAdviceSubmit
        ))
    }

    @Test("A missing receipt only retries after explicit continuation", arguments: [
        StoryInputMode.text, StoryInputMode.voice,
    ])
    func notFoundRequiresExplicitRetryOfSameRequest(mode: StoryInputMode) async throws {
        let journal = CoordinatorJournal()
        let client = CoordinatorSubmissionClient(journal: journal)
        client.setSubmitFailure(EngineConnectionError.timedOut)
        client.setAdvice(try notFound())
        client.setResponse(try StorySessionModelTests.submitResult())
        let coordinator = makeCoordinator(mode: mode, journal: journal, client: client)

        await submit(coordinator, mode: mode)
        #expect(coordinator.state == .notFound)
        #expect(client.textSubmissionRequests.count + client.voiceSubmissionRequests.count == 1)

        client.setSubmitFailure(nil)
        await coordinator.continuePendingRequest()

        #expect(coordinator.state == .committed)
        #expect(client.textSubmissionRequests.count + client.voiceSubmissionRequests.count == 2)
        #expect(client.textSubmissionRequests.first?.inputTurnId
            ?? client.voiceSubmissionRequests.first?.inputTurnId == "input_turn_1")
        #expect(client.textSubmissionRequests.last?.rawInput
            ?? client.voiceSubmissionRequests.last?.rawInput == "先看看医生的反应。")
    }

    @Test("A received receipt waits for explicit continuation", arguments: [
        StoryInputMode.text, StoryInputMode.voice,
    ])
    func receivedWaitsForExplicitContinuation(mode: StoryInputMode) async throws {
        let journal = CoordinatorJournal()
        let client = CoordinatorSubmissionClient(journal: journal)
        client.setSubmitFailure(EngineConnectionError.timedOut)
        client.setAdvice(try StorySessionModelTests.adviceFound(committed: false))
        client.setResponse(try StorySessionModelTests.submitResult())
        let coordinator = makeCoordinator(mode: mode, journal: journal, client: client)

        await submit(coordinator, mode: mode)
        #expect(coordinator.state == .received)
        #expect(client.textSubmissionRequests.count + client.voiceSubmissionRequests.count == 1)

        client.setSubmitFailure(nil)
        await coordinator.continuePendingRequest()

        #expect(coordinator.state == .committed)
        #expect(client.textSubmissionRequests.count + client.voiceSubmissionRequests.count == 2)
    }

    @Test("A journal write failure performs no submit or recovery IPC")
    func journalWriteFailureSendsNothing() async {
        let journal = CoordinatorJournal()
        journal.failWrites(true)
        let client = CoordinatorSubmissionClient(journal: journal)
        let coordinator = makeCoordinator(mode: .voice, journal: journal, client: client)

        await submit(coordinator, mode: .voice)

        #expect(coordinator.state == .blocked(code: "journal_unavailable"))
        #expect(client.textSubmissionRequests.isEmpty)
        #expect(client.voiceSubmissionRequests.isEmpty)
        #expect(client.adviceQueries.isEmpty)
    }

    @Test("Only one text or voice mutation can be in flight")
    func duplicateClickCannotStartASecondMutation() async throws {
        let journal = CoordinatorJournal()
        let client = CoordinatorSubmissionClient(journal: journal)
        client.setResponse(try StorySessionModelTests.submitResult())
        let coordinator = makeCoordinator(mode: .text, journal: journal, client: client)
        let started = client.holdNextSubmission()

        let first = Task { @MainActor in
            await submit(coordinator, mode: .text)
        }
        for await _ in started { break }
        await submit(coordinator, mode: .voice)
        client.releaseSubmission()
        await first.value

        #expect(client.textSubmissionRequests.count == 1)
        #expect(client.voiceSubmissionRequests.isEmpty)
        #expect(coordinator.state == .committed)
    }

    @Test("A connection change preserves the frozen request for recovery")
    func detachPreservesFrozenRequest() async throws {
        let journal = CoordinatorJournal()
        let client = CoordinatorSubmissionClient(journal: journal)
        client.setSubmitFailure(EngineConnectionError.timedOut)
        client.setQueryFailure(EngineConnectionError.timedOut)
        let coordinator = makeCoordinator(mode: .voice, journal: journal, client: client)

        await submit(coordinator, mode: .voice, rawInput: "  不改写的 ASR 原文  ")
        let frozen = try #require(try journal.load()?.frozenSubmission)
        #expect(coordinator.state == .outcomeUnknown)

        coordinator.detachForConnectionChange()
        client.setQueryFailure(nil)
        client.setAdvice(try StorySessionModelTests.adviceFound(committed: true))
        await coordinator.recover()

        #expect(coordinator.state == .committed)
        #expect(try journal.load()?.frozenSubmission == frozen)
        #expect(frozen.inputMode == .voice)
        #expect(frozen.rawInput == "  不改写的 ASR 原文  ")
        #expect(client.voiceSubmissionRequests.count == 1)
    }
}
