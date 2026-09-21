import CryptoKit
import Foundation
import Testing
@testable import WorldOfMysteriesCore

private actor FakeSpeechRailRealtimeTTSTransport: SpeechRailRealtimeTTSTransport {
    private var openedRequests: [URLRequest] = []
    private var sentTextsStorage: [String] = []
    private var inbound: [Data] = []
    private var waiting: [CheckedContinuation<Data, any Error>] = []
    private(set) var closed = false

    func open(_ request: URLRequest) async throws {
        openedRequests.append(request)
    }

    func sendText(_ text: String) async throws {
        sentTextsStorage.append(text)
    }

    func receiveData() async throws -> Data {
        if !inbound.isEmpty { return inbound.removeFirst() }
        return try await withCheckedThrowingContinuation { waiting.append($0) }
    }

    func close() async {
        closed = true
        let pending = waiting
        waiting.removeAll()
        for continuation in pending {
            continuation.resume(throwing: SpeechRailRealtimeTTSFailure.connectionClosed)
        }
    }

    func push(_ object: [String: Any]) {
        let data = try! JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        if !waiting.isEmpty { waiting.removeFirst().resume(returning: data) }
        else { inbound.append(data) }
    }

    func requests() -> [URLRequest] { openedRequests }
    func sentTexts() -> [String] { sentTextsStorage }
}

@Suite("SpeechRail current-only Realtime TTS")
struct SpeechRailRealtimeTTSTests {
    private func event(
        _ type: String,
        sequence: Int64,
        extra: [String: Any] = [:],
        sessionID: String = "sess-tts"
    ) -> [String: Any] {
        var object: [String: Any] = [
            "type": type,
            "event_id": "evt-\(sequence)",
            "session_id": sessionID,
            "sequence": sequence,
        ]
        extra.forEach { object[$0.key] = $0.value }
        return object
    }

    private func primeHandshake(_ transport: FakeSpeechRailRealtimeTTSTransport) async {
        await transport.push(
            event(
                "session.created",
                sequence: 1,
                extra: [
                    "session": [
                        "id": "sess-tts",
                        "type": "transcription",
                        "capabilities": ["transcription", "speech"],
                        "speech_capabilities": ["available": true],
                        "speechrail": ["tts": ["enabled": false]],
                    ]
                ]
            )
        )
        await transport.push(
            event(
                "transcription_session.updated",
                sequence: 2,
                extra: [
                    "session": [
                        "id": "sess-tts",
                        "type": "transcription",
                        "speechrail": [
                            "tts": ["enabled": true],
                            "render_receipts": ["enabled": true, "version": 1],
                        ],
                    ]
                ]
            )
        )
    }

    @Test("Handshake opts into current-only TTS and Render Receipts")
    func handshake() async throws {
        let transport = FakeSpeechRailRealtimeTTSTransport()
        await primeHandshake(transport)
        let revision = String(repeating: "a", count: 40)
        let configuration = SpeechRailRealtimeTTSConfiguration(
            apiKey: "local-secret",
            expectedModelRevision: revision
        )
        let connection = SpeechRailRealtimeTTSConnection(
            configuration: configuration,
            transport: transport
        )

        let info = try await connection.connect()
        #expect(info.serviceSessionID == "sess-tts")
        #expect(info.lastServerSequence == 2)
        #expect(info.ttsEnabled)
        #expect(info.renderReceiptsEnabled)
        #expect(!configuration.description.contains("local-secret"))

        let requests = await transport.requests()
        #expect(requests.count == 1)
        #expect(requests[0].url?.absoluteString == "ws://127.0.0.1:8201/v1/realtime")
        #expect(requests[0].value(forHTTPHeaderField: "Authorization") == "Bearer local-secret")

        let sent = await transport.sentTexts()
        #expect(sent.count == 1)
        let object = try #require(
            try JSONSerialization.jsonObject(with: Data(sent[0].utf8)) as? [String: Any]
        )
        #expect(object["type"] as? String == "transcription_session.update")
        let session = try #require(object["session"] as? [String: Any])
        let speechrail = try #require(session["speechrail"] as? [String: Any])
        #expect((speechrail["tts"] as? [String: Any])?["enabled"] as? Bool == true)
        #expect((speechrail["render_receipts"] as? [String: Any])?["enabled"] as? Bool == true)
        #expect((speechrail["model_revision"] as? [String: Any])?["expected"] as? String == revision)
        #expect(session["turn_detection"] is NSNull)
    }

    @Test("TTS request uses only speechrail.tts.create and cancel")
    func createAndCancel() async throws {
        let transport = FakeSpeechRailRealtimeTTSTransport()
        await primeHandshake(transport)
        let connection = SpeechRailRealtimeTTSConnection(transport: transport)
        _ = try await connection.connect()

        try await connection.begin(
            SpeechRailTTSRequest(
                requestID: "turn-42-sentence-3",
                text: "克莱恩抬起头。",
                voice: "narrator",
                expectedVoiceRevision: "vr_abc"
            )
        )
        await transport.push(
            event(
                "response.created",
                sequence: 3,
                extra: [
                    "response": [
                        "id": "resp-1",
                        "object": "realtime.response",
                        "status": "in_progress",
                    ]
                ]
            )
        )
        _ = try await connection.receiveEnvelope()
        try await connection.cancelCurrent()

        let sent = await transport.sentTexts()
        #expect(sent.count == 3)
        let create = try #require(
            try JSONSerialization.jsonObject(with: Data(sent[1].utf8)) as? [String: Any]
        )
        #expect(create["type"] as? String == "speechrail.tts.create")
        #expect(create["request_id"] as? String == "turn-42-sentence-3")
        #expect(create["expected_voice_revision"] as? String == "vr_abc")

        let cancel = try #require(
            try JSONSerialization.jsonObject(with: Data(sent[2].utf8)) as? [String: Any]
        )
        #expect(cancel["type"] as? String == "speechrail.tts.cancel")
        #expect(cancel["request_id"] as? String == "turn-42-sentence-3")
        #expect(cancel["response_id"] as? String == "resp-1")
        #expect(!sent.contains(where: { $0.contains("response.create") }))
        #expect(!sent.contains(where: { $0.contains("response.cancel") }))
    }

    @Test("Completed render is accepted only when streamed PCM matches Render Receipt")
    func verifiedRenderReceipt() async throws {
        let transport = FakeSpeechRailRealtimeTTSTransport()
        await primeHandshake(transport)
        let connection = SpeechRailRealtimeTTSConnection(transport: transport)
        _ = try await connection.connect()
        let requestID = "req-verified"
        try await connection.begin(
            SpeechRailTTSRequest(requestID: requestID, text: "你好。", voice: "serena")
        )

        let pcm = Data([1, 0, 2, 0, 3, 0, 4, 0])
        let digest = SHA256.hash(data: pcm).map { String(format: "%02x", $0) }.joined()
        await transport.push(
            event(
                "response.created",
                sequence: 3,
                extra: ["response": ["id": "resp-verified", "status": "in_progress"]]
            )
        )
        await transport.push(
            event(
                "response.output_audio.delta",
                sequence: 4,
                extra: [
                    "response_id": "resp-verified",
                    "item_id": "item-1",
                    "delta": pcm.base64EncodedString(),
                ]
            )
        )
        await transport.push(
            event(
                "response.output_audio.done",
                sequence: 5,
                extra: ["response_id": "resp-verified", "item_id": "item-1"]
            )
        )
        await transport.push(
            event(
                "response.done",
                sequence: 6,
                extra: [
                    "response": ["id": "resp-verified", "status": "completed"],
                    "speechrail": [
                        "kind": "tts",
                        "request_id": requestID,
                        "voice_revision": "vr_1",
                        "render_receipt": [
                            "receipt_id": "rr_1",
                            "request_id": requestID,
                            "response_id": "resp-verified",
                            "status": "completed",
                            "voice": ["id": "serena", "revision": "vr_1"],
                            "model": [:],
                            "audio": [
                                "format": "pcm16",
                                "pcm_sample_rate": 24_000,
                                "channels": 1,
                                "sample_count": 4,
                                "pcm_sha256": digest,
                            ],
                            "error_code": NSNull(),
                        ],
                    ],
                ]
            )
        )

        var accumulator = SpeechRailTTSRenderAccumulator(requestID: requestID)
        for _ in 0..<4 {
            accumulator.observe(try await connection.receiveEnvelope())
        }
        guard case .completed(let result)? = accumulator.terminal else {
            Issue.record("Expected verified provider completion")
            return
        }
        #expect(result.sampleCount == 4)
        #expect(result.pcmSHA256 == digest)
        #expect(result.receipt.receiptID == "rr_1")
        #expect(result.voiceRevision == "vr_1")
    }

    @Test("response.done cannot wash an incomplete audio stream into success")
    func incompleteStreamFailsClosed() throws {
        let requestID = "req-incomplete"
        var accumulator = SpeechRailTTSRenderAccumulator(requestID: requestID)
        accumulator.observe(
            SpeechRailTTSServerEnvelope(
                eventID: "e1",
                sessionID: "s",
                sequence: 1,
                event: .responseCreated(responseID: "r")
            )
        )
        accumulator.observe(
            SpeechRailTTSServerEnvelope(
                eventID: "e2",
                sessionID: "s",
                sequence: 2,
                event: .audioDelta(
                    responseID: "r",
                    itemID: "i",
                    pcm16: Data([0, 0])
                )
            )
        )
        accumulator.observe(
            SpeechRailTTSServerEnvelope(
                eventID: "e3",
                sessionID: "s",
                sequence: 3,
                event: .responseDone(
                    responseID: "r",
                    status: .completed,
                    requestID: requestID,
                    voiceRevision: nil,
                    receipt: nil
                )
            )
        )
        #expect(accumulator.terminal == .failed(.audioStreamIncomplete))
    }

    @Test("Odd PCM is rejected before playback can see it")
    func oddPCMRejected() throws {
        let bad = event(
            "response.output_audio.delta",
            sequence: 1,
            extra: [
                "response_id": "r",
                "item_id": "i",
                "delta": Data([1, 2, 3]).base64EncodedString(),
            ]
        )
        let data = try JSONSerialization.data(withJSONObject: bad)
        #expect(throws: SpeechRailRealtimeTTSFailure.audioChunkInvalid) {
            try SpeechRailTTSServerEnvelope.decode(data)
        }
    }

    @Test("Remote plaintext service is rejected before opening a socket")
    func remotePlaintextRejected() async {
        let transport = FakeSpeechRailRealtimeTTSTransport()
        let connection = SpeechRailRealtimeTTSConnection(
            configuration: .init(
                baseURL: URL(string: "http://speech.example.test:8201/v1")!,
                allowRemote: true
            ),
            transport: transport
        )
        do {
            _ = try await connection.connect()
            Issue.record("Remote plaintext endpoint was accepted")
        } catch let failure as SpeechRailRealtimeTTSFailure {
            #expect(failure == .invalidConfiguration)
        } catch {
            Issue.record("Unexpected error: \(error)")
        }
        #expect(await transport.requests().isEmpty)
    }
}
