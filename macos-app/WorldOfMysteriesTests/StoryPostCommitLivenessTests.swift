import Foundation
import Testing
@testable import WorldOfMysteriesCore

/// A committed turn's narrative and audio are produced by a background worker,
/// so the first read after COMMIT is normally still in flight. These tests pin
/// the client behaviour that makes that transition observable at all: bounded
/// re-read of a pure projection, never a retry and never a re-submit.
@MainActor
@Suite("Post-COMMIT work liveness")
struct StoryPostCommitLivenessTests {
    private static func work(
        settlement: String = "succeeded",
        settlementReason: String? = nil,
        narrative: String,
        segments: [[String: Any]] = [],
        narrativeReason: String? = nil,
        audio: String,
        audioReason: String? = nil
    ) throws -> StoryTurnWorkGetResponseDTO {
        var object: [String: Any] = [
            "schema_version": "1.0",
            "session_id": "session_1",
            "turn_id": "turn_first_001",
            "settlement_state": settlement,
            "narrative_state": narrative,
            "narrative_segments": segments,
            "audio_state": audio,
        ]
        if let settlementReason { object["settlement_reason"] = settlementReason }
        if let narrativeReason { object["narrative_reason"] = narrativeReason }
        if let audioReason { object["audio_reason"] = audioReason }
        return try JSONDecoder().decode(
            StoryTurnWorkGetResponseDTO.self,
            from: JSONSerialization.data(withJSONObject: object)
        )
    }

    private static let inFlight = try! work(narrative: "pending", audio: "pending")
    private static let running = try! work(settlement: "running", narrative: "running", audio: "running")
    private static let ready = try! work(
        narrative: "ready",
        segments: [["type": "narration", "text": "雨停了。"]],
        audio: "unavailable",
        audioReason: "voice_unavailable"
    )

    private func makeSession(
        interval: Duration = .milliseconds(10),
        horizon: Duration = .seconds(90)
    ) throws -> (StorySessionModel, FakeStoryClient, MemoryStoryJournal) {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let session = try StorySessionModelTests.view(turn: 1, storyRevision: 1, storeRevision: 2)
        let (model, client) = StorySessionModelTests.makeModel(
            log: log,
            journal: journal,
            entryView: try StorySessionModelTests.entry(
                session: session,
                storeRevision: 2,
                advice: [StorySessionModelTests.advice(forTurn: 2)]
            ),
            openView: StoryOpenViewDTO(
                session: session,
                openedStoreRevision: 2,
                replayed: false
            ),
            submitView: nil,
            adviceView: try StorySessionModelTests.adviceFound(),
            postCommitPollInterval: interval,
            postCommitPollHorizon: horizon
        )
        client.setPostCommitCapabilities([.turnWorkGet])
        return (model, client, journal)
    }

    /// Waits for a condition the background re-read is expected to satisfy.
    private func waitUntil(
        _ condition: @MainActor () -> Bool,
        timeout: Duration = .seconds(5)
    ) async throws {
        let deadline = ContinuousClock.now.advanced(by: timeout)
        while ContinuousClock.now < deadline {
            if condition() { return }
            try await Task.sleep(for: .milliseconds(5))
        }
        Issue.record("the post-COMMIT re-read never reached the expected state")
    }

    @Test("A pending turn is re-read until the projection reaches its terminal state")
    func observesTheTransition() async throws {
        let (model, client, _) = try makeSession()
        client.setPostCommitWorkScript([
            Self.inFlight,
            Self.running,
            Self.running,
            Self.ready,
        ])

        await model.refreshEntry()
        try await waitUntil { model.postCommitWork?.narrativeState == .ready }

        #expect(client.postCommitWorkObservedStates == [
            "succeeded/pending/pending",
            "running/running/running",
            "running/running/running",
            "succeeded/ready/unavailable",
        ])
        #expect(!model.postCommitWorkLoading)
        #expect(!model.postCommitWorkPollGaveUp)
        #expect(!model.postCommitWorkReadFailed)
        // A re-read is a pure projection read: it never retries work and never
        // re-submits the turn.
        #expect(client.postCommitWorkRetryIdentities.isEmpty)
        #expect(client.submittedCount == 0)
    }

    @Test("A turn that is already finished is read exactly once")
    func terminalProjectionIsNotPolledAgain() async throws {
        let (model, client, _) = try makeSession()
        client.setPostCommitWorkResponse(Self.ready)

        await model.refreshEntry()
        try await Task.sleep(for: .milliseconds(200))

        #expect(client.postCommitWorkObservedStates == ["succeeded/ready/unavailable"])
        #expect(!model.postCommitWorkLoading)
    }

    @Test("Blocked settlement and unavailable audio are outcomes, not in-flight states")
    func failureStatesAreTerminal() async throws {
        let blocked = try Self.work(
            settlement: "blocked",
            settlementReason: "settlement_blocked",
            narrative: "blocked",
            narrativeReason: "narrative_blocked",
            audio: "unavailable",
            audioReason: "voice_unavailable"
        )
        #expect(StorySessionModel.isTerminalPostCommitWork(blocked))

        let (model, client, _) = try makeSession()
        client.setPostCommitWorkResponse(blocked)

        await model.refreshEntry()
        try await Task.sleep(for: .milliseconds(200))

        #expect(client.postCommitWorkObservedStates == ["blocked/blocked/unavailable"])
        #expect(!model.postCommitWorkLoading)
    }

    @Test("A projection that never settles stops at the horizon instead of polling forever")
    func horizonIsAPatienceCeiling() async throws {
        let (model, client, _) = try makeSession(
            interval: .milliseconds(5),
            horizon: .milliseconds(60)
        )
        client.setPostCommitWorkResponse(Self.inFlight)

        await model.refreshEntry()
        try await waitUntil { model.postCommitWorkPollGaveUp }
        let readsAtGiveUp = client.postCommitWorkObservedStates.count
        try await Task.sleep(for: .milliseconds(200))

        #expect(readsAtGiveUp > 1)
        #expect(client.postCommitWorkObservedStates.count == readsAtGiveUp)
        #expect(!model.postCommitWorkLoading)
        // The last real projection is kept: giving up is not a rewrite.
        #expect(model.postCommitWork == Self.inFlight)
    }

    @Test("Moving to another turn cancels the previous turn's re-read")
    func sessionChangeStaysWithinItsOwnTurn() async throws {
        let log = StoryCallLog()
        let journal = MemoryStoryJournal()
        let first = try StorySessionModelTests.view(turn: 1, storyRevision: 1, storeRevision: 2)
        let second = try StorySessionModelTests.view(turn: 2, storyRevision: 2, storeRevision: 3)
        let (model, client) = StorySessionModelTests.makeModel(
            log: log,
            journal: journal,
            entryView: try StorySessionModelTests.entry(
                session: first,
                storeRevision: 2,
                advice: [StorySessionModelTests.advice(forTurn: 2)]
            ),
            openView: StoryOpenViewDTO(session: first, openedStoreRevision: 2, replayed: false),
            submitView: nil,
            adviceView: try StorySessionModelTests.adviceFound(),
            postCommitPollInterval: .milliseconds(5),
            postCommitPollHorizon: .seconds(90)
        )
        client.setPostCommitCapabilities([.turnWorkGet])
        client.setPostCommitWorkResponse(Self.inFlight)

        await model.refreshEntry()
        try await waitUntil { client.postCommitWorkObservedStates.count > 1 }

        // The world moved on: a second committed turn supersedes the first.
        client.setEntryView(
            try StorySessionModelTests.entry(
                session: second,
                storeRevision: 3,
                advice: [StorySessionModelTests.advice(forTurn: 3)]
            )
        )
        client.setPostCommitWorkResponse(Self.ready)
        await model.reloadSession()
        let readsAfterSwitch = client.postCommitWorkObservedStates.count
        try await Task.sleep(for: .milliseconds(200))

        #expect(model.postCommitWork?.narrativeState == .ready)
        #expect(client.postCommitWorkObservedStates.count == readsAfterSwitch)
    }
}
