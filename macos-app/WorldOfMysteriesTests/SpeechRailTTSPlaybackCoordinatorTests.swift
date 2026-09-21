import CryptoKit
import Foundation
import Testing
@testable import WorldOfMysteriesCore

private actor TTSPlaybackEventLog {
    private var entries: [String] = []
    func append(_ value: String) { entries.append(value) }
    func snapshot() -> [String] { entries }
}

private actor CoordinatorPlaybackBackend: NativePCMPlaybackBackend {
    private let log: TTSPlaybackEventLog
    private var chunks: [Data] = []
    private var enqueueWaiters: [CheckedContinuation<Void, Never>] = []

    init(log: TTSPlaybackEventLog) { self.log = log }

    func start(sampleRate: Int, channels: Int) async throws {
        #expect(sampleRate == 24_000)
        #expect(channels == 1)
        await log.append("local_start")
    }

    func enqueue(pcm16: Data, frameCount: Int) async throws {
        #expect(pcm16.count == frameCount * 2)
        chunks.append(pcm16)
        await log.append("local_enqueue")
        let waiters = enqueueWaiters
        enqueueWaiters.removeAll()
        waiters.forEach { $0.resume() }
    }

    func stop() async {
        await log.append("local_stop")
    }

    func waitForEnqueue() async {
        if !chunks.isEmpty { return }
        await withCheckedContinuation { enqueueWaiters.append($0) }
    }

    func chunkCount() -> Int { chunks.count }
}

private actor CoordinatorTTSTransport: SpeechRailRealtimeTTSTransport {
    private let log: TTSPlaybackEventLog
    private var inbound: [Data] = []
    private var waiting: [CheckedContinuation<Data, any Error>] = []
    private var sent: [[String: Any]] = []

    init(log: TTSPlaybackEventLog) { self.log = log }

    func open(_ request: URLRequest) async throws { _ = request }

    func sendText(_ text: String) async throws {
        let object = try #require(
            try JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any]
        )
        sent.append(object)
        if object["type"] as? String == "speechrail.tts.cancel" {
            await log.append("provider_cancel")
        }
    }

    func receiveData() async throws -> Data {
        if !inbound.isEmpty { return inbound.removeFirst() }
        return try await withCheckedThrowingContinuation { waiting.append($0) }
    }

    func close() async {
        let pending = waiting
        waiting.removeAll()
        for waiter in pending {
            waiter.resume(throwing: SpeechRailRealtimeTTSFailure.connectionClosed)
        }
    }

    func push(_ object: [String: Any]) {
        let data = try! JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
        if !waiting.isEmpty { waiting.removeFirst().resume(returning: data) }
        else { inbound.append(data) }
    }

    func sentTypes() -> [String] { sent.compactMap { $0["type"] as? String } }
}

@Suite("SpeechRail TTS native playback coordinator")
struct SpeechRailTTSPlaybackCoordinatorTests {
    private func event(
        _ type: String,
        sequence: Int64,
        extra: [String: Any] = [:]
    ) -> [String: Any] {
        var object: [String: Any] = [
            "type": type,
            "event_id": "evt-\(sequence)",
            "session_id": "sess-tts",
            "sequence": sequence,
        ]
        extra.forEach { object[$0.key] = $0.value }
        return object
    }

    private func primeHandshake(_ transport: CoordinatorTTSTransport) async {
        await transport.push(
            event(
                "session.created",
                sequence: 1,
                extra: [
                    "session": [
                        "id": "sess-tts",
                        "type": "transcription",
                        "capabilities": ["transcription", "speech"],
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

    private func completedResponseEvents(
        requestID: String,
        responseID: String,
        itemID: String,
        pcm: Data,
        startSequence: Int64 = 3
    ) -> [[String: Any]] {
        let digest = SHA256.hash(data: pcm).map { String(format: "%02x", $0) }.joined()
        return [
            event(
                "response.created",
                sequence: startSequence,
                extra: ["response": ["id": responseID, "status": "in_progress"]]
            ),
            event(
                "response.output_audio.delta",
                sequence: startSequence + 1,
                extra: [
                    "response_id": responseID,
                    "item_id": itemID,
                    "delta": pcm.base64EncodedString(),
                ]
            ),
            event(
                "response.output_audio.done",
                sequence: startSequence + 2,
                extra: ["response_id": responseID, "item_id": itemID]
            ),
            event(
                "response.done",
                sequence: startSequence + 3,
                extra: [
                    "response": ["id": responseID, "status": "completed"],
                    "speechrail": [
                        "kind": "tts",
                        "request_id": requestID,
                        "voice_revision": "vr_1",
                        "render_receipt": [
                            "receipt_id": "rr_1",
                            "request_id": requestID,
                            "response_id": responseID,
                            "status": "completed",
                            "voice": ["id": "serena", "revision": "vr_1"],
                            "model": [:],
                            "audio": [
                                "format": "pcm16",
                                "pcm_sample_rate": 24_000,
                                "channels": 1,
                                "sample_count": pcm.count / 2,
                                "pcm_sha256": digest,
                            ],
                            "error_code": NSNull(),
                        ],
                    ],
                ]
            ),
        ]
    }

    @Test("Verified provider PCM is scheduled while device completion remains unproven")
    func completedRenderKeepsEvidenceBoundary() async throws {
        let log = TTSPlaybackEventLog()
        let transport = CoordinatorTTSTransport(log: log)
        let backend = CoordinatorPlaybackBackend(log: log)
        await primeHandshake(transport)
        let connection = SpeechRailRealtimeTTSConnection(transport: transport)
        let playback = NativePlaybackActor(backend: backend)
        let coordinator = SpeechRailTTSPlaybackCoordinator(
            connection: connection,
            playback: playback
        )
        let requestID = "req-one"
        let pcm = Data([1, 0, 2, 0, 3, 0, 4, 0])
        for serverEvent in completedResponseEvents(
            requestID: requestID,
            responseID: "resp-one",
            itemID: "item-one",
            pcm: pcm
        ) {
            await transport.push(serverEvent)
        }

        let terminal = await coordinator.render(
            SpeechRailTTSRequest(requestID: requestID, text: "你好。", voice: "serena")
        )
        guard case .completed(let result) = terminal else {
            Issue.record("Expected completed TTS playback")
            return
        }
        #expect(result.provider.sampleCount == 4)
        #expect(result.playback.scheduledFrames == 4)
        #expect(result.playback.mediaStreamEnded)
        #expect(result.playback.providerCompleted)
        #expect(!result.playback.devicePlaybackProvenComplete)
        #expect(await backend.chunkCount() == 1)

        let retired = try await coordinator.retireCompletedPresentation(renderedEstimateFrames: 4)
        #expect(retired.evidence == .renderedEstimate)
        #expect(!retired.devicePlaybackProvenComplete)
    }

    @Test("Stop is local-first and late PCM cannot re-enter playback")
    func stopIsLocalFirstAndDropsLatePCM() async throws {
        let log = TTSPlaybackEventLog()
        let transport = CoordinatorTTSTransport(log: log)
        let backend = CoordinatorPlaybackBackend(log: log)
        await primeHandshake(transport)
        let connection = SpeechRailRealtimeTTSConnection(transport: transport)
        let coordinator = SpeechRailTTSPlaybackCoordinator(
            connection: connection,
            playback: NativePlaybackActor(backend: backend)
        )
        let requestID = "req-stop"
        let responseID = "resp-stop"
        let itemID = "item-stop"
        let first = Data([1, 0, 2, 0])
        let late = Data([3, 0, 4, 0])

        await transport.push(
            event(
                "response.created",
                sequence: 3,
                extra: ["response": ["id": responseID, "status": "in_progress"]]
            )
        )
        await transport.push(
            event(
                "response.output_audio.delta",
                sequence: 4,
                extra: [
                    "response_id": responseID,
                    "item_id": itemID,
                    "delta": first.base64EncodedString(),
                ]
            )
        )

        let task = Task {
            await coordinator.render(
                SpeechRailTTSRequest(requestID: requestID, text: "停止前的句子", voice: "serena")
            )
        }
        await backend.waitForEnqueue()
        await coordinator.stop()

        await transport.push(
            event(
                "response.output_audio.delta",
                sequence: 5,
                extra: [
                    "response_id": responseID,
                    "item_id": itemID,
                    "delta": late.base64EncodedString(),
                ]
            )
        )
        await transport.push(
            event(
                "response.done",
                sequence: 6,
                extra: [
                    "response": ["id": responseID, "status": "cancelled"],
                    "speechrail": [
                        "kind": "tts",
                        "request_id": requestID,
                        "voice_revision": NSNull(),
                    ],
                ]
            )
        )

        #expect(await task.value == .cancelled)
        #expect(await backend.chunkCount() == 1)
        let order = await log.snapshot()
        let localStop = try #require(order.firstIndex(of: "local_stop"))
        let providerCancel = try #require(order.firstIndex(of: "provider_cancel"))
        #expect(localStop < providerCancel)
        #expect(await transport.sentTypes().contains("speechrail.tts.cancel"))
    }
}
