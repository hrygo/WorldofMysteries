import Foundation
import Testing
@testable import WorldOfMysteriesCore

/// A scripted peer that models the locked SpeechRail FIFO contract: the
/// `session.update` handler answers only after the preceding `commit` handler
/// has drained its ASR reader. The second `session.update` is therefore the
/// barrier the client relies on.
private actor ScriptedASRTurnTransport: SpeechRailRealtimeASRTransport {
    enum CommitBehavior: Sendable {
        case completed(String)
        case missingTerminal
        case partialOnly(String)
        case failed(String)
        case serverError(String)
    }

    private let commitBehavior: CommitBehavior
    private let answersBarrier: Bool
    private var sessionID = "sess-turn-0"
    private var sequence: Int64 = 0
    private var connectionCount = 0
    private var inbound: [Data] = []
    private var waiters: [CheckedContinuation<Data, any Error>] = []
    private var sessionUpdateCount = 0
    private(set) var sentTypes: [String] = []
    private(set) var closeCount = 0

    init(commitBehavior: CommitBehavior = .completed("尾段"), answersBarrier: Bool = true) {
        self.commitBehavior = commitBehavior
        self.answersBarrier = answersBarrier
    }

    func open(_ request: URLRequest) async throws {
        _ = request
        connectionCount += 1
        sequence = 0
        sessionUpdateCount = 0
        sessionID = "sess-turn-\(connectionCount)"
        emitSession(type: "session.created")
    }

    func sendText(_ text: String) async throws {
        let object = try #require(
            try JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any]
        )
        let type = try #require(object["type"] as? String)
        sentTypes.append(type)

        switch type {
        case "session.update":
            sessionUpdateCount += 1
            // The handshake update is answered immediately; the barrier update
            // is answered only when this peer is configured to model the drain.
            if sessionUpdateCount == 1 || answersBarrier {
                emitSession(type: "session.updated")
            }
        case "input_audio_buffer.commit":
            let itemID = "tail"
            switch commitBehavior {
            case .completed(let transcript):
                emit(
                    type: "conversation.item.input_audio_transcription.completed",
                    extra: ["item_id": itemID, "content_index": 0, "transcript": transcript]
                )
            case .missingTerminal:
                break
            case .partialOnly(let delta):
                emit(
                    type: "conversation.item.input_audio_transcription.delta",
                    extra: ["item_id": itemID, "content_index": 0, "delta": delta]
                )
            case .failed(let code):
                emit(
                    type: "conversation.item.input_audio_transcription.failed",
                    extra: [
                        "item_id": itemID, "content_index": 0,
                        "error": ["code": code],
                    ]
                )
            case .serverError(let code):
                emit(type: "error", extra: ["error": ["code": code]])
            }
        default:
            break
        }
    }

    func receiveData() async throws -> Data {
        if !inbound.isEmpty {
            return inbound.removeFirst()
        }
        return try await withCheckedThrowingContinuation { continuation in
            waiters.append(continuation)
        }
    }

    func close() async {
        closeCount += 1
        let pending = waiters
        waiters.removeAll()
        for waiter in pending {
            waiter.resume(throwing: SpeechRailRealtimeASRFailure.connectionClosed)
        }
    }

    /// A rollover item the service finalizes while capture is still running.
    func injectFinal(itemID: String, transcript: String) {
        emit(
            type: "conversation.item.input_audio_transcription.completed",
            extra: ["item_id": itemID, "content_index": 0, "transcript": transcript]
        )
    }

    func types() -> [String] { sentTypes }

    private func emitSession(type: String) {
        let speechrail: [String: Any] = [
            "task": "transcription",
            "tts": ["enabled": false],
            "alignment": ["enabled": false],
            "diarization": ["enabled": false],
        ]
        emit(
            type: type,
            extra: [
                "session": [
                    "id": sessionID,
                    "type": "transcription",
                    "audio": [
                        "input": [
                            "format": ["type": "audio/pcm", "rate": 24_000],
                            "transcription": [
                                "model": SpeechRailRealtimeSessionConfiguration.registeredASRModel,
                                "language": "zh",
                            ],
                            "turn_detection": NSNull(),
                            "speechrail": speechrail,
                        ],
                    ],
                    "speechrail": speechrail,
                ],
            ]
        )
    }

    private func emit(type: String, extra: [String: Any] = [:]) {
        sequence += 1
        var object: [String: Any] = [
            "type": type,
            "event_id": "srv-\(sequence)",
            "session_id": sessionID,
            "sequence": sequence,
        ]
        for (key, value) in extra {
            object[key] = value
        }
        let data = try! JSONSerialization.data(
            withJSONObject: object,
            options: [.sortedKeys]
        )
        if !waiters.isEmpty {
            waiters.removeFirst().resume(returning: data)
        } else {
            inbound.append(data)
        }
    }
}

@Suite("SpeechRail Realtime ASR turn coordinator")
struct SpeechRailRealtimeASRTurnCoordinatorTests {
    private actor UpdateTape {
        private(set) var drafts: [String] = []
        private(set) var terminals = 0

        func record(_ update: SpeechRailRealtimeASRTurnUpdate) {
            switch update {
            case .draft(let text): drafts.append(text)
            case .terminal: terminals += 1
            }
        }
    }

    private func connected(
        behavior: ScriptedASRTurnTransport.CommitBehavior = .completed("尾段"),
        answersBarrier: Bool = true
    ) async throws -> (
        SpeechRailRealtimeASRConnection,
        ScriptedASRTurnTransport,
        SpeechRailRealtimeASRConnectionInfo
    ) {
        let transport = ScriptedASRTurnTransport(
            commitBehavior: behavior,
            answersBarrier: answersBarrier
        )
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        let info = try await connection.connect()
        return (connection, transport, info)
    }

    @Test("A rollover item is drained during capture and the barrier closes one logical turn")
    func rolloverAndFinish() async throws {
        let (connection, transport, _) = try await connected()
        let coordinator = SpeechRailRealtimeASRTurnCoordinator(connection: connection)
        _ = try await coordinator.start()

        await transport.injectFinal(itemID: "rollover", transcript: "先观察")
        try await Task.sleep(for: .milliseconds(20))
        #expect(await coordinator.phase == .capturing)

        let result = await coordinator.finish()
        guard case .transcript(let final) = result else {
            Issue.record("Expected final transcript, got \(result)")
            return
        }
        #expect(final.text == "先观察尾段")
        #expect(final.segments.map(\.itemID) == ["rollover", "tail"])
        // The barrier is commit followed by the identical session re-send; the
        // removed `input_audio_buffer.clear` must not reappear.
        #expect(await transport.types().suffix(2) == [
            "input_audio_buffer.commit",
            "session.update",
        ])
        #expect(await coordinator.phase == .terminal)
    }

    @Test("A successful turn closes its connection so no barrier reply reaches the next turn")
    func successClosesConnection() async throws {
        let (connection, transport, _) = try await connected()
        let coordinator = SpeechRailRealtimeASRTurnCoordinator(connection: connection)
        _ = try await coordinator.start()
        _ = await coordinator.finish()

        #expect(await transport.closeCount == 1)
        do {
            _ = try await connection.currentInfo()
            Issue.record("A completed turn left the connection reusable")
        } catch let failure as SpeechRailRealtimeASRFailure {
            #expect(failure == .notConnected)
        }
    }

    @Test("A turn whose only item never appears at the barrier yields no Advice")
    func missingTerminal() async throws {
        let (connection, _, _) = try await connected(behavior: .missingTerminal)
        let coordinator = SpeechRailRealtimeASRTurnCoordinator(connection: connection)
        _ = try await coordinator.start()
        let result = await coordinator.finish()
        // Nothing was ever observed for this turn, so the barrier proves an
        // empty transcript rather than inventing a partial one.
        #expect(result == .empty)
    }

    @Test("A barrier with an observed but unfinished item fails the whole turn")
    func unfinishedItemFailsClosed() async throws {
        let (connection, _, _) = try await connected(behavior: .partialOnly("尾段"))
        let coordinator = SpeechRailRealtimeASRTurnCoordinator(connection: connection)
        _ = try await coordinator.start()
        let result = await coordinator.finish()
        // Partial text is a draft; the barrier refuses to promote it.
        #expect(result == .failed(.itemNotTerminal(itemIDs: ["tail"])))
    }

    @Test("A backend item failure stays failed even though the barrier still arrives")
    func failedTerminal() async throws {
        let (connection, _, _) = try await connected(behavior: .failed("backend_timeout"))
        let coordinator = SpeechRailRealtimeASRTurnCoordinator(connection: connection)
        _ = try await coordinator.start()
        let result = await coordinator.finish()
        #expect(result == .failed(.itemFailed(itemID: "tail", code: "backend_timeout")))
    }

    @Test("A commit error is not laundered into success by the later barrier")
    func commitErrorSurvivesBarrier() async throws {
        let (connection, _, _) = try await connected(behavior: .serverError("backend_busy"))
        let coordinator = SpeechRailRealtimeASRTurnCoordinator(connection: connection)
        _ = try await coordinator.start()
        let result = await coordinator.finish()
        #expect(result == .failed(.serverError(code: "backend_busy")))
    }

    @Test("A peer that never answers the barrier times out instead of returning partial text")
    func unansweredBarrierTimesOut() async throws {
        let (connection, transport, _) = try await connected(answersBarrier: false)
        let coordinator = SpeechRailRealtimeASRTurnCoordinator(
            connection: connection,
            finalizationTimeout: .milliseconds(80)
        )
        _ = try await coordinator.start()
        let result = await coordinator.finish()

        #expect(result == .failed(.finalizationTimedOut))
        #expect(await transport.closeCount == 1)
    }

    @Test("Cancellation closes the connection so no stale barrier can reach the next turn")
    func cancellationClosesEpoch() async throws {
        let (connection, transport, oldInfo) = try await connected()
        let coordinator = SpeechRailRealtimeASRTurnCoordinator(connection: connection)
        _ = try await coordinator.start()

        await coordinator.cancel()
        #expect(await coordinator.phase == .terminal)
        #expect(await transport.closeCount == 1)

        do {
            _ = try await connection.currentInfo()
            Issue.record("Cancelled connection remained reusable")
        } catch let failure as SpeechRailRealtimeASRFailure {
            #expect(failure == .notConnected)
        }

        // Reconnect creates a new connection epoch even when the same transport
        // fixture is reused, so late events from the old turn cannot match it.
        let newInfo = try await connection.connect()
        #expect(newInfo.connectionEpoch != oldInfo.connectionEpoch)
        await connection.close()
    }

    @Test("A cancelled turn publishes exactly one terminal even if finish is also called")
    func cancelTerminatesOnce() async throws {
        let (connection, transport, _) = try await connected(answersBarrier: false)
        let coordinator = SpeechRailRealtimeASRTurnCoordinator(
            connection: connection,
            finalizationTimeout: .seconds(5)
        )
        _ = try await coordinator.start()

        async let cancelled = coordinator.finish()
        try await Task.sleep(for: .milliseconds(20))
        await coordinator.cancel()

        let first = await cancelled
        let second = await coordinator.finish()
        #expect(first == .cancelled)
        #expect(second == .cancelled)
        #expect(await transport.closeCount == 1)
    }

    @Test("Turn updates publish drafts and exactly one terminal")
    func updatesPublishDraftsThenOneTerminal() async throws {
        let (connection, _, _) = try await connected()
        let coordinator = SpeechRailRealtimeASRTurnCoordinator(connection: connection)
        _ = try await coordinator.start()
        let stream = await coordinator.updates()

        let tape = UpdateTape()
        let collector = Task {
            for await update in stream {
                await tape.record(update)
            }
        }

        let result = await coordinator.finish()
        _ = await collector.value

        #expect(await tape.terminals == 1)
        #expect(await tape.drafts == ["尾段"])
        if case .transcript = result {} else {
            Issue.record("Expected a transcript, got \(result)")
        }
    }
}
