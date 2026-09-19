import Foundation
import Testing
@testable import WorldOfMysteriesCore

private actor ScriptedASRTurnTransport: SpeechRailRealtimeASRTransport {
    enum CommitBehavior: Sendable {
        case completed(String)
        case missingTerminal
        case failed(String)
    }

    private let commitBehavior: CommitBehavior
    private var sessionID = "sess-turn"
    private var sequence: Int64 = 0
    private var inbound: [Data] = []
    private var waiters: [CheckedContinuation<Data, any Error>] = []
    private(set) var sentTypes: [String] = []
    private(set) var closeCount = 0

    init(commitBehavior: CommitBehavior = .completed("尾段")) {
        self.commitBehavior = commitBehavior
    }

    func open(_ request: URLRequest) async throws {
        del(request)
        emit(type: "session.created")
        emit(type: "conversation.created")
    }

    func sendText(_ text: String) async throws {
        let object = try #require(
            try JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any]
        )
        let type = try #require(object["type"] as? String)
        sentTypes.append(type)

        switch type {
        case "session.update":
            emit(type: "session.updated")
        case "input_audio_buffer.commit":
            let itemID = "tail"
            emit(
                type: "input_audio_buffer.committed",
                extra: ["item_id": itemID]
            )
            switch commitBehavior {
            case .completed(let transcript):
                emit(
                    type: "conversation.item.input_audio_transcription.completed",
                    extra: ["item_id": itemID, "transcript": transcript]
                )
            case .missingTerminal:
                break
            case .failed(let code):
                emit(
                    type: "conversation.item.input_audio_transcription.failed",
                    extra: ["item_id": itemID, "error": ["code": code]]
                )
            }
        case "input_audio_buffer.clear":
            emit(type: "input_audio_buffer.cleared")
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

    func injectCommitted(itemID: String, transcript: String) {
        emit(type: "input_audio_buffer.committed", extra: ["item_id": itemID])
        emit(
            type: "conversation.item.input_audio_transcription.completed",
            extra: ["item_id": itemID, "transcript": transcript]
        )
    }

    func types() -> [String] { sentTypes }

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

    private func del(_ request: URLRequest) {
        _ = request
    }
}

@Suite("SpeechRail Realtime ASR turn coordinator")
struct SpeechRailRealtimeASRTurnCoordinatorTests {
    private func connected(
        behavior: ScriptedASRTurnTransport.CommitBehavior = .completed("尾段")
    ) async throws -> (
        SpeechRailRealtimeASRConnection,
        ScriptedASRTurnTransport,
        SpeechRailRealtimeASRConnectionInfo
    ) {
        let transport = ScriptedASRTurnTransport(commitBehavior: behavior)
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        let info = try await connection.connect()
        return (connection, transport, info)
    }

    @Test("Auto rollover is drained during capture and final commit closes one logical turn")
    func rolloverAndFinish() async throws {
        let (connection, transport, _) = try await connected()
        let coordinator = SpeechRailRealtimeASRTurnCoordinator(connection: connection)
        _ = try await coordinator.start()

        await transport.injectCommitted(itemID: "rollover", transcript: "先观察")
        try await Task.sleep(for: .milliseconds(20))

        let result = await coordinator.finish()
        guard case .transcript(let final) = result else {
            Issue.record("Expected final transcript")
            return
        }
        #expect(final.text == "先观察尾段")
        #expect(final.segments.map(\.itemID) == ["rollover", "tail"])
        #expect(await transport.types().suffix(2) == [
            "input_audio_buffer.commit",
            "input_audio_buffer.clear",
        ])
    }

    @Test("Clear after a missing terminal fails the whole turn")
    func missingTerminal() async throws {
        let (connection, _, _) = try await connected(behavior: .missingTerminal)
        let coordinator = SpeechRailRealtimeASRTurnCoordinator(connection: connection)
        _ = try await coordinator.start()
        let result = await coordinator.finish()
        #expect(
            result
                == .failed(
                    .clearedBeforeAllItemsTerminal(missingItemIDs: ["tail"])
                )
        )
    }

    @Test("Backend failed terminal remains failed even though clear follows")
    func failedTerminal() async throws {
        let (connection, _, _) = try await connected(
            behavior: .failed("backend_timeout")
        )
        let coordinator = SpeechRailRealtimeASRTurnCoordinator(connection: connection)
        _ = try await coordinator.start()
        let result = await coordinator.finish()
        #expect(
            result
                == .failed(
                    .itemFailed(itemID: "tail", code: "backend_timeout")
                )
        )
    }

    @Test("Cancellation closes the connection so no stale clear can reach the next turn")
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

    @Test("Finalization timeout fails closed and closes the connection")
    func timeoutClosesConnection() async throws {
        actor NeverTerminalTransport: SpeechRailRealtimeASRTransport {
            private var sequence: Int64 = 0
            private var inbound: [Data] = []
            private var waiters: [CheckedContinuation<Data, any Error>] = []
            private(set) var closed = false

            func open(_ request: URLRequest) async throws {
                _ = request
                emit("session.created")
                emit("conversation.created")
            }

            func sendText(_ text: String) async throws {
                let object = try #require(
                    try JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any]
                )
                if object["type"] as? String == "session.update" {
                    emit("session.updated")
                }
            }

            func receiveData() async throws -> Data {
                if !inbound.isEmpty { return inbound.removeFirst() }
                return try await withCheckedThrowingContinuation { waiters.append($0) }
            }

            func close() async {
                closed = true
                let pending = waiters
                waiters.removeAll()
                for waiter in pending {
                    waiter.resume(throwing: SpeechRailRealtimeASRFailure.connectionClosed)
                }
            }

            private func emit(_ type: String) {
                sequence += 1
                let object: [String: Any] = [
                    "type": type,
                    "event_id": "e\(sequence)",
                    "session_id": "never",
                    "sequence": sequence,
                ]
                let data = try! JSONSerialization.data(withJSONObject: object)
                if !waiters.isEmpty { waiters.removeFirst().resume(returning: data) }
                else { inbound.append(data) }
            }
        }

        let transport = NeverTerminalTransport()
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        _ = try await connection.connect()
        let coordinator = SpeechRailRealtimeASRTurnCoordinator(
            connection: connection,
            finalizationTimeout: .milliseconds(50)
        )
        _ = try await coordinator.start()
        let result = await coordinator.finish()

        #expect(result == .failed(.finalizationTimedOut))
        #expect(await transport.closed)
    }
}
