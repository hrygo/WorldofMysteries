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
        emit(bytes, sampleRate: SpeechRailRealtimeWire.sampleRate)
    }

    func emit(_ bytes: [UInt8], sampleRate: Int) {
        let data = Data(bytes)
        continuation?.yield(
            MicrophonePCM16Chunk(
                data: data,
                sampleRate: sampleRate,
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

private actor PTTOrderProbe {
    private var events: [String] = []
    func record(_ event: String) { events.append(event) }
    func snapshot() -> [String] { events }
}

private actor PTTScriptTransport: SpeechRailRealtimeASRTransport {
    private var sequence: Int64 = 0
    private var sessionID = "ptt"
    private var inbound: [Data] = []
    private var waiters: [CheckedContinuation<Data, any Error>] = []
    private(set) var sentTypes: [String] = []
    private(set) var appendPayloads: [Data] = []
    private(set) var closed = false
    private let orderProbe: PTTOrderProbe?

    init(orderProbe: PTTOrderProbe? = nil) {
        self.orderProbe = orderProbe
    }

    func open(_ request: URLRequest) async throws {
        _ = request
        await orderProbe?.record("transport.open")
        sequence = 0
        sessionID = UUID().uuidString
        emitSession()
    }

    func sendText(_ text: String) async throws {
        let object = try #require(
            try JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any]
        )
        let type = try #require(object["type"] as? String)
        sentTypes.append(type)
        switch type {
        case "session.update":
            let speechrail = pendingSessionSpeechrail ?? [
                "task": "transcription",
                "tts": ["enabled": false],
                "alignment": ["enabled": false],
                "diarization": ["enabled": false],
            ]
            emit(
                "session.updated",
                extra: ["session": sessionObject(speechrail: speechrail)]
            )
        case "input_audio_buffer.append":
            let encoded = try #require(object["audio"] as? String)
            appendPayloads.append(try #require(Data(base64Encoded: encoded)))
        case "input_audio_buffer.commit":
            emit(
                "conversation.item.input_audio_transcription.completed",
                extra: ["item_id": "final", "content_index": 0, "transcript": "打开门"]
            )
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

    private func emitSession() {
        let speechrail: [String: Any] = [
            "task": "transcription",
            "tts": ["enabled": false],
            "alignment": ["enabled": false],
            "diarization": ["enabled": false],
        ]
        pendingSessionSpeechrail = speechrail
        emit("session.created", extra: ["session": sessionObject(speechrail: speechrail)])
    }

    private var pendingSessionSpeechrail: [String: Any]?

    private func sessionObject(speechrail: [String: Any]) -> [String: Any] {
        [
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
        ]
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
    @Test("Stopping capture drains all local appends before commit and the barrier update")
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
            "session.update",
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

    @Test("A chunk that is not the 24 kHz wire rate fails the turn before commit")
    func wrongSampleRateDoesNotCommit() async throws {
        let transport = PTTScriptTransport()
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        let microphone = FakeMicrophonePCMSource()
        let session = VoiceInputPTTSession(
            connection: connection,
            microphone: microphone
        )
        _ = try await session.start()

        // 16 kHz was the pre-4.0 rate; accepting it would put audio on the wire
        // that the service would have to resample or reject on its own terms.
        microphone.emit([0, 0], sampleRate: 16_000)
        try await Task.sleep(for: .milliseconds(20))
        let result = await session.finish()

        #expect(result == .failed(.captureFailure))
        let snapshot = await transport.snapshot()
        #expect(!snapshot.types.contains("input_audio_buffer.commit"))
        #expect(snapshot.closed)
    }

    @Test("A malformed frame is rejected rather than partially appended")
    func malformedChunkDoesNotCommit() async throws {
        let transport = PTTScriptTransport()
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        let microphone = FakeMicrophonePCMSource()
        let session = VoiceInputPTTSession(
            connection: connection,
            microphone: microphone
        )
        _ = try await session.start()

        // An odd byte count cannot be a whole PCM16 frame.
        microphone.emit([0, 0, 1], sampleRate: SpeechRailRealtimeWire.sampleRate)
        try await Task.sleep(for: .milliseconds(20))
        let result = await session.finish()

        #expect(result == .failed(.captureFailure))
        let snapshot = await transport.snapshot()
        #expect(!snapshot.types.contains("input_audio_buffer.commit"))
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


extension VoiceInputPTTSessionTests {
    @Test("Half-duplex local interruption happens before ASR network connect")
    func localInterruptionPrecedesNetwork() async throws {
        let order = PTTOrderProbe()
        let transport = PTTScriptTransport(orderProbe: order)
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        let microphone = FakeMicrophonePCMSource()
        let session = VoiceInputPTTSession(
            connection: connection,
            microphone: microphone,
            beforeCapture: {
                await order.record("local.interrupt")
            }
        )

        _ = try await session.start()
        await session.cancel()

        let events = await order.snapshot()
        #expect(events.prefix(2) == ["local.interrupt", "transport.open"])
    }
}
