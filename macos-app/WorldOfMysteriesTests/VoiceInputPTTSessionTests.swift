import Foundation
import Testing
@testable import WorldOfMysteriesCore

@MainActor
private final class FakeMicrophonePCMSource: MicrophonePCMSource {
    private var continuation: AsyncThrowingStream<MicrophonePCM16Chunk, any Error>.Continuation?
    private var stream: AsyncThrowingStream<MicrophonePCM16Chunk, any Error>?
    private(set) var stopCount = 0

    func start() throws -> AsyncThrowingStream<MicrophonePCM16Chunk, any Error> {
        let channel = AsyncThrowingStream<MicrophonePCM16Chunk, any Error>.makeStream(
            bufferingPolicy: .bufferingOldest(8)
        )
        continuation = channel.continuation
        stream = channel.stream
        return channel.stream
    }

    func emit(_ bytes: [UInt8]) {
        let data = Data(bytes)
        continuation?.yield(
            MicrophonePCM16Chunk(
                data: data,
                sampleRate: 24_000,
                channels: 1,
                frameCount: data.count / 2
            )
        )
    }

    func fail(_ error: MicrophoneCaptureFailure) {
        continuation?.finish(throwing: error)
    }

    func stop() {
        stopCount += 1
        continuation?.finish()
        continuation = nil
        stream = nil
    }
}

private actor PTTScriptTransport: SpeechRailRealtimeASRTransport {
    private var sequence: Int64 = 0
    private var sessionID = "ptt"
    private var inbound: [Data] = []
    private var waiters: [CheckedContinuation<Data, any Error>] = []
    private(set) var sentTypes: [String] = []
    private(set) var appendPayloads: [Data] = []
    private(set) var closed = false

    func open(_ request: URLRequest) async throws {
        _ = request
        sequence = 0
        sessionID = UUID().uuidString
        emit("session.created")
        emit("conversation.created")
    }

    func sendText(_ text: String) async throws {
        let object = try #require(
            try JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any]
        )
        let type = try #require(object["type"] as? String)
        sentTypes.append(type)
        switch type {
        case "session.update":
            emit("session.updated")
        case "input_audio_buffer.append":
            let encoded = try #require(object["audio"] as? String)
            appendPayloads.append(try #require(Data(base64Encoded: encoded)))
        case "input_audio_buffer.commit":
            emit("input_audio_buffer.committed", extra: ["item_id": "final"])
            emit(
                "conversation.item.input_audio_transcription.completed",
                extra: ["item_id": "final", "transcript": "打开门"]
            )
        case "input_audio_buffer.clear":
            emit("input_audio_buffer.cleared")
        default:
            break
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

    func snapshot() -> (types: [String], payloads: [Data], closed: Bool) {
        (sentTypes, appendPayloads, closed)
    }

    private func emit(_ type: String, extra: [String: Any] = [:]) {
        sequence += 1
        var object: [String: Any] = [
            "type": type,
            "event_id": "evt-\(sequence)",
            "session_id": sessionID,
            "sequence": sequence,
        ]
        extra.forEach { object[$0.key] = $0.value }
        let data = try! JSONSerialization.data(withJSONObject: object)
        if !waiters.isEmpty { waiters.removeFirst().resume(returning: data) }
        else { inbound.append(data) }
    }
}

@Suite("Voice push-to-talk input ordering")
@MainActor
struct VoiceInputPTTSessionTests {
    @Test("Stopping capture drains all local appends before commit and clear")
    func drainBeforeCommit() async throws {
        let transport = PTTScriptTransport()
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        let microphone = FakeMicrophonePCMSource()
        let session = VoiceInputPTTSession(
            connection: connection,
            microphone: microphone
        )
        _ = try await session.start()

        microphone.emit([0, 0, 1, 0])
        microphone.emit([2, 0, 3, 0])
        try await Task.sleep(for: .milliseconds(20))

        let result = await session.finish()
        guard case .transcript(let final) = result else {
            Issue.record("Expected final transcript")
            return
        }
        #expect(final.text == "打开门")
        #expect(microphone.stopCount == 1)

        let snapshot = await transport.snapshot()
        #expect(snapshot.types == [
            "session.update",
            "input_audio_buffer.append",
            "input_audio_buffer.append",
            "input_audio_buffer.commit",
            "input_audio_buffer.clear",
        ])
        #expect(snapshot.payloads == [Data([0, 0, 1, 0]), Data([2, 0, 3, 0])])
    }

    @Test("Capture failure closes the turn without sending commit")
    func captureFailureDoesNotCommit() async throws {
        let transport = PTTScriptTransport()
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        let microphone = FakeMicrophonePCMSource()
        let session = VoiceInputPTTSession(
            connection: connection,
            microphone: microphone
        )
        _ = try await session.start()

        microphone.fail(.bufferOverflow)
        try await Task.sleep(for: .milliseconds(20))
        let result = await session.finish()

        #expect(result == .failed(.captureFailure))
        let snapshot = await transport.snapshot()
        #expect(!snapshot.types.contains("input_audio_buffer.commit"))
        #expect(snapshot.closed)
    }

    @Test("Explicit cancel never finalizes an Advice transcript")
    func cancel() async throws {
        let transport = PTTScriptTransport()
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        let microphone = FakeMicrophonePCMSource()
        let session = VoiceInputPTTSession(
            connection: connection,
            microphone: microphone
        )
        _ = try await session.start()
        microphone.emit([0, 0])
        await session.cancel()

        #expect(session.phase == .terminal)
        let snapshot = await transport.snapshot()
        #expect(!snapshot.types.contains("input_audio_buffer.commit"))
        #expect(snapshot.closed)
    }
}
