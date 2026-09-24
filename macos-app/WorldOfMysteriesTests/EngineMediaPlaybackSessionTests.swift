import CryptoKit
import Foundation
import Testing
@testable import WorldOfMysteriesCore

private actor MediaPlaybackEventLog {
    private var entries: [String] = []
    func append(_ entry: String) { entries.append(entry) }
    func snapshot() -> [String] { entries }
}

private actor FakeMediaFrameTransport: MediaFrameTransport {
    private let log: MediaPlaybackEventLog
    private let stream: AsyncThrowingStream<MediaFrame, any Error>
    private let continuation: AsyncThrowingStream<MediaFrame, any Error>.Continuation
    private var sent: [MediaFrame] = []
    private var waiters: [(Int, CheckedContinuation<Void, Never>)] = []
    private(set) var path: String?
    private(set) var closed = false

    init(log: MediaPlaybackEventLog) {
        self.log = log
        let channel = AsyncThrowingStream<MediaFrame, any Error>.makeStream(
            bufferingPolicy: .bufferingOldest(16)
        )
        stream = channel.stream
        continuation = channel.continuation
    }

    func connect(path: String, timeout: TimeInterval) async throws {
        #expect(timeout > 0)
        self.path = path
        await log.append("wire_connect")
    }

    func send(_ frame: MediaFrame) async throws {
        sent.append(frame)
        switch frame.header {
        case .open:
            await log.append("wire_open")
        case .credit:
            await log.append("wire_credit")
        case .cancel:
            await log.append("wire_cancel")
        default:
            break
        }
        let pending = waiters
        waiters.removeAll()
        for (count, waiter) in pending where sent.count >= count {
            waiter.resume()
        }
        for (count, waiter) in pending where sent.count < count {
            waiters.append((count, waiter))
        }
    }

    nonisolated func frameStream() -> AsyncThrowingStream<MediaFrame, any Error> {
        stream
    }

    func close() async {
        guard !closed else { return }
        closed = true
        await log.append("wire_close")
        continuation.finish(throwing: MediaSocketTransportFailure.disconnected)
    }

    func push(_ frame: MediaFrame) {
        continuation.yield(frame)
    }

    func waitForSentCount(_ count: Int) async {
        if sent.count >= count { return }
        await withCheckedContinuation { waiters.append((count, $0)) }
    }

    func sentFrames() -> [MediaFrame] { sent }
}

private actor MediaPlaybackBackend: NativePCMPlaybackBackend {
    private let log: MediaPlaybackEventLog
    private var chunks: [Data] = []
    private var enqueueWaiters: [CheckedContinuation<Void, Never>] = []

    init(log: MediaPlaybackEventLog) { self.log = log }

    func start(sampleRate: Int, channels: Int, outputGain: Double) async throws {
        #expect(sampleRate == 24_000)
        #expect(channels == 1)
        #expect(outputGain > 0 && outputGain <= 1.0)
        await log.append("local_start")
    }

    func enqueue(pcm16: Data, frameCount: Int) async throws {
        #expect(pcm16.count == frameCount * 2)
        chunks.append(pcm16)
        await log.append("local_enqueue")
        let pending = enqueueWaiters
        enqueueWaiters.removeAll()
        pending.forEach { $0.resume() }
    }

    func metrics() async -> NativePlaybackBackendMetrics {
        NativePlaybackBackendMetrics(queueCapacityBytes: 262_144)
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

@Suite("Engine media UDS -> native playback")
struct EngineMediaPlaybackSessionTests {
    private func grant(generation: Int64 = 4) throws -> MediaOpenGrant {
        try MediaOpenGrant(payload: [
            "protocol_version": .string("1.0"),
            "socket_path": .string("/tmp/wom-media-test.sock"),
            "stream_id": .string("tts-stream"),
            "trace_id": .string("trace-1"),
            "engine_epoch": .string("engine-1"),
            "generation": .int(Int(generation)),
            "ticket": .string(String(repeating: "a", count: 64)),
            "direction": .string("engine_to_app"),
            "format": .object([
                "codec": .string("pcm_s16le"),
                "sample_rate": .int(24_000),
                "channels": .int(1),
            ]),
            "max_payload_bytes": .int(65_536),
            "initial_credit_bytes": .int(262_144),
            "expires_in_ms": .int(10_000),
        ])
    }

    @Test("OPEN -> CHUNK -> CREDIT -> END validates integrity before playback stream end")
    func completeMediaStream() async throws {
        let log = MediaPlaybackEventLog()
        let transport = FakeMediaFrameTransport(log: log)
        let backend = MediaPlaybackBackend(log: log)
        let playback = NativePlaybackActor(backend: backend)
        let session = EngineMediaPlaybackSession(
            grant: try grant(),
            transport: transport,
            playback: playback
        )
        let task = Task { await session.run() }

        await transport.waitForSentCount(1)
        let pcm = Data([1, 0, 2, 0, 3, 0, 4, 0])
        let chunk = MediaChunkHeader(
            streamId: "tts-stream",
            generation: 4,
            sequence: 0,
            offsetFrames: 0,
            frameCount: 4,
            payloadBytes: pcm.count
        )
        await transport.push(MediaFrame(header: .chunk(chunk), payload: pcm))
        await transport.waitForSentCount(2)

        let digest = SHA256.hash(data: pcm).map { String(format: "%02x", $0) }.joined()
        await transport.push(
            MediaFrame(
                header: .end(
                    MediaEndHeader(
                        streamId: "tts-stream",
                        generation: 4,
                        totalFrames: 4,
                        totalBytes: Int64(pcm.count),
                        sha256: digest
                    )
                )
            )
        )

        guard case .ended(let snapshot) = await task.value else {
            Issue.record("Expected a validated media END")
            return
        }
        #expect(snapshot.scheduledFrames == 4)
        #expect(snapshot.mediaStreamEnded)
        #expect(snapshot.providerTerminal == .none)
        #expect(!snapshot.devicePlaybackProvenComplete)

        let sent = await transport.sentFrames()
        guard case .open = sent[0].header else {
            Issue.record("First outbound media frame must be OPEN")
            return
        }
        guard case .credit(let credit) = sent[1].header else {
            Issue.record("Consumed PCM must replenish media credit")
            return
        }
        #expect(credit.creditBytes == pcm.count)

        let retired = try await session.retireEndedPresentation(renderedEstimateFrames: 4)
        #expect(retired.evidence == .renderedEstimate)
        #expect(!retired.devicePlaybackProvenComplete)
    }

    @Test("Stop is local-first, sends CANCEL, and closes transport")
    func localFirstStop() async throws {
        let log = MediaPlaybackEventLog()
        let transport = FakeMediaFrameTransport(log: log)
        let backend = MediaPlaybackBackend(log: log)
        let session = EngineMediaPlaybackSession(
            grant: try grant(),
            transport: transport,
            playback: NativePlaybackActor(backend: backend)
        )
        let task = Task { await session.run() }

        await transport.waitForSentCount(1)
        let pcm = Data([1, 0, 2, 0])
        await transport.push(
            MediaFrame(
                header: .chunk(
                    MediaChunkHeader(
                        streamId: "tts-stream",
                        generation: 4,
                        sequence: 0,
                        offsetFrames: 0,
                        frameCount: 2,
                        payloadBytes: pcm.count
                    )
                ),
                payload: pcm
            )
        )
        await backend.waitForEnqueue()
        await session.stop()

        #expect(await task.value == .cancelled)
        let order = await log.snapshot()
        let localStop = try #require(order.firstIndex(of: "local_stop"))
        let wireCancel = try #require(order.firstIndex(of: "wire_cancel"))
        #expect(localStop < wireCancel)
        #expect(await transport.closed)
    }

    @Test("Digest mismatch fails closed before declaring media stream complete")
    func digestMismatchFailsClosed() async throws {
        let log = MediaPlaybackEventLog()
        let transport = FakeMediaFrameTransport(log: log)
        let backend = MediaPlaybackBackend(log: log)
        let session = EngineMediaPlaybackSession(
            grant: try grant(),
            transport: transport,
            playback: NativePlaybackActor(backend: backend)
        )
        let task = Task { await session.run() }

        await transport.waitForSentCount(1)
        let pcm = Data([1, 0])
        await transport.push(
            MediaFrame(
                header: .chunk(
                    MediaChunkHeader(
                        streamId: "tts-stream",
                        generation: 4,
                        sequence: 0,
                        offsetFrames: 0,
                        frameCount: 1,
                        payloadBytes: pcm.count
                    )
                ),
                payload: pcm
            )
        )
        await transport.waitForSentCount(2)
        await transport.push(
            MediaFrame(
                header: .end(
                    MediaEndHeader(
                        streamId: "tts-stream",
                        generation: 4,
                        totalFrames: 1,
                        totalBytes: 2,
                        sha256: String(repeating: "0", count: 64)
                    )
                )
            )
        )

        #expect(
            await task.value
                == .failed(.protocolViolation(.streamDigestMismatch))
        )
        #expect(await transport.closed)
    }
}


@Suite("Engine media playback performance policy")
struct EngineMediaPlaybackPerformanceTests {
    @Test("Low-stimulation mode reaches the native backend before media OPEN")
    func lowStimulationModeIsAppliedBeforeOpen() async throws {
        let log = MediaPlaybackEventLog()
        let transport = FakeMediaFrameTransport(log: log)
        let backend = MediaPlaybackBackend(log: log)
        let playback = NativePlaybackActor(backend: backend)
        let grant = try MediaOpenGrant(payload: [
            "protocol_version": .string("1.0"),
            "socket_path": .string("/tmp/wom-media-test.sock"),
            "stream_id": .string("tts-low"),
            "trace_id": .string("trace-low"),
            "engine_epoch": .string("engine-low"),
            "generation": .int(31),
            "ticket": .string(String(repeating: "a", count: 64)),
            "direction": .string("engine_to_app"),
            "format": .object([
                "codec": .string("pcm_s16le"),
                "sample_rate": .int(24_000),
                "channels": .int(1),
            ]),
            "max_payload_bytes": .int(65_536),
            "initial_credit_bytes": .int(262_144),
            "expires_in_ms": .int(10_000),
        ])
        let session = EngineMediaPlaybackSession(
            grant: grant,
            transport: transport,
            playback: playback,
            playbackMode: .lowStimulation
        )
        let task = Task { await session.run() }
        await transport.waitForSentCount(1)

        let snapshot = try #require(await playback.snapshot())
        #expect(snapshot.mode == .lowStimulation)
        #expect(snapshot.outputGain == 0.45)

        await session.stop()
        #expect(await task.value == .cancelled)
    }
}


private actor FakeVoiceDeliveryReporter: VoiceDeliveryCursorReporting {
    private var cursor: VoiceDeliveryCursorDTO?
    private(set) var updates: [VoiceDeliveryCursorUpdateDTO] = []

    init(cursor: VoiceDeliveryCursorDTO? = nil) {
        self.cursor = cursor
    }

    func loadVoiceDeliveryCursor(
        trackId: String,
        consumerId: String,
        traceId: String
    ) async throws -> VoiceDeliveryCursorDTO? {
        cursor
    }

    func updateVoiceDeliveryCursor(
        _ request: VoiceDeliveryCursorUpdateDTO,
        traceId: String
    ) async throws -> VoiceDeliveryCursorDTO {
        updates.append(request)
        let next = VoiceDeliveryCursorDTO(
            trackId: request.trackId,
            consumerId: request.consumerId,
            unitId: request.unitId,
            generation: request.generation,
            sourceOffsetFrames: request.sourceOffsetFrames,
            totalSourceFrames: request.totalSourceFrames,
            evidence: request.evidence,
            stopReason: request.stopReason,
            cursorRevision: request.expectedCursorRevision + 1,
            fullyOutput: false
        )
        cursor = next
        return next
    }

    func snapshotUpdates() -> [VoiceDeliveryCursorUpdateDTO] { updates }
}

@Suite("Engine media playback DeliveryCursor milestones")
struct EngineMediaPlaybackCursorTests {
    @Test("Queued precedes OPEN and scheduled follows local enqueue")
    func queuedThenScheduled() async throws {
        let log = MediaPlaybackEventLog()
        let transport = FakeMediaFrameTransport(log: log)
        let backend = MediaPlaybackBackend(log: log)
        let playback = NativePlaybackActor(backend: backend)
        let reporter = FakeVoiceDeliveryReporter()
        let grant = try MediaOpenGrant(payload: [
            "protocol_version": .string("1.0"),
            "socket_path": .string("/tmp/wom-media-test.sock"),
            "stream_id": .string("tts-cursor"),
            "trace_id": .string("trace-cursor"),
            "engine_epoch": .string("engine-cursor"),
            "generation": .int(41),
            "ticket": .string(String(repeating: "a", count: 64)),
            "direction": .string("engine_to_app"),
            "format": .object([
                "codec": .string("pcm_s16le"),
                "sample_rate": .int(24_000),
                "channels": .int(1),
            ]),
            "max_payload_bytes": .int(65_536),
            "initial_credit_bytes": .int(262_144),
            "expires_in_ms": .int(10_000),
        ])
        let session = EngineMediaPlaybackSession(
            grant: grant,
            transport: transport,
            playback: playback,
            deliveryReporter: reporter,
            deliveryContext: VoiceDeliverySessionContext(
                trackId: "track-1",
                consumerId: "local-playback",
                unitId: "speech-1"
            )
        )
        let task = Task { await session.run() }
        await transport.waitForSentCount(1)

        var updates = await reporter.snapshotUpdates()
        #expect(updates.count == 1)
        #expect(updates[0].evidence == .queued)
        #expect(updates[0].sourceOffsetFrames == 0)
        #expect(updates[0].expectedCursorRevision == 0)

        let pcm = Data([1, 0, 2, 0])
        await transport.push(
            MediaFrame(
                header: .chunk(
                    MediaChunkHeader(
                        streamId: "tts-cursor",
                        generation: 41,
                        sequence: 0,
                        offsetFrames: 0,
                        frameCount: 2,
                        payloadBytes: pcm.count
                    )
                ),
                payload: pcm
            )
        )
        await transport.waitForSentCount(2)
        updates = await reporter.snapshotUpdates()
        #expect(updates.count == 2)
        #expect(updates[1].evidence == .scheduled)
        #expect(updates[1].sourceOffsetFrames == 2)

        await session.stop()
        #expect(await task.value == .cancelled)
    }

    @Test("Existing cursor forces a new generation to restart at sentence start")
    func restartFromSentenceStart() async throws {
        let existing = VoiceDeliveryCursorDTO(
            trackId: "track-1",
            consumerId: "local-playback",
            unitId: "speech-old",
            generation: 8,
            sourceOffsetFrames: 200,
            totalSourceFrames: 500,
            evidence: .renderedEstimate,
            stopReason: .suspend,
            cursorRevision: 4,
            fullyOutput: false
        )
        let reporter = FakeVoiceDeliveryReporter(cursor: existing)
        let log = MediaPlaybackEventLog()
        let transport = FakeMediaFrameTransport(log: log)
        let backend = MediaPlaybackBackend(log: log)
        let grant = try MediaOpenGrant(payload: [
            "protocol_version": .string("1.0"),
            "socket_path": .string("/tmp/wom-media-test.sock"),
            "stream_id": .string("tts-restart"),
            "trace_id": .string("trace-restart"),
            "engine_epoch": .string("engine-restart"),
            "generation": .int(9),
            "ticket": .string(String(repeating: "a", count: 64)),
            "direction": .string("engine_to_app"),
            "format": .object([
                "codec": .string("pcm_s16le"),
                "sample_rate": .int(24_000),
                "channels": .int(1),
            ]),
            "max_payload_bytes": .int(65_536),
            "initial_credit_bytes": .int(262_144),
            "expires_in_ms": .int(10_000),
        ])
        let session = EngineMediaPlaybackSession(
            grant: grant,
            transport: transport,
            playback: NativePlaybackActor(backend: backend),
            deliveryReporter: reporter,
            deliveryContext: VoiceDeliverySessionContext(
                trackId: "track-1",
                consumerId: "local-playback",
                unitId: "speech-1"
            )
        )
        let task = Task { await session.run() }
        await transport.waitForSentCount(1)

        let updates = await reporter.snapshotUpdates()
        #expect(updates.count == 1)
        #expect(updates[0].generation == 9)
        #expect(updates[0].sourceOffsetFrames == 0)
        #expect(updates[0].evidence == .queued)
        #expect(updates[0].expectedCursorRevision == 4)

        await session.stop(reason: .sessionClosed)
        #expect(await task.value == .cancelled)
    }
}


extension EngineMediaPlaybackCursorTests {
    @Test("Remote media cancel persists the mapped durable stop reason")
    func remoteCancelPersistsStopReason() async throws {
        let log = MediaPlaybackEventLog()
        let transport = FakeMediaFrameTransport(log: log)
        let backend = MediaPlaybackBackend(log: log)
        let reporter = FakeVoiceDeliveryReporter()
        let grant = try MediaOpenGrant(payload: [
            "protocol_version": .string("1.0"),
            "socket_path": .string("/tmp/wom-media-test.sock"),
            "stream_id": .string("tts-remote-cancel"),
            "trace_id": .string("trace-remote-cancel"),
            "engine_epoch": .string("engine-remote-cancel"),
            "generation": .int(51),
            "ticket": .string(String(repeating: "a", count: 64)),
            "direction": .string("engine_to_app"),
            "format": .object([
                "codec": .string("pcm_s16le"),
                "sample_rate": .int(24_000),
                "channels": .int(1),
            ]),
            "max_payload_bytes": .int(65_536),
            "initial_credit_bytes": .int(262_144),
            "expires_in_ms": .int(10_000),
        ])
        let session = EngineMediaPlaybackSession(
            grant: grant,
            transport: transport,
            playback: NativePlaybackActor(backend: backend),
            deliveryReporter: reporter,
            deliveryContext: VoiceDeliverySessionContext(
                trackId: "track-remote-cancel",
                consumerId: "local-playback",
                unitId: "speech-remote-cancel"
            )
        )
        let task = Task { await session.run() }
        await transport.waitForSentCount(1)

        await transport.push(
            MediaFrame(
                header: .cancel(
                    MediaCancelHeader(
                        streamId: "tts-remote-cancel",
                        generation: 51,
                        reason: .superseded
                    )
                )
            )
        )

        #expect(await task.value == .cancelled)
        let updates = await reporter.snapshotUpdates()
        #expect(updates.count == 2)
        #expect(updates[1].stopReason == .superseded)
        #expect(updates[1].evidence == .queued)
        #expect(updates[1].sourceOffsetFrames == 0)
    }

    @Test("Remote media error persists media_error without promoting completion")
    func remoteErrorPersistsMediaError() async throws {
        let log = MediaPlaybackEventLog()
        let transport = FakeMediaFrameTransport(log: log)
        let backend = MediaPlaybackBackend(log: log)
        let reporter = FakeVoiceDeliveryReporter()
        let grant = try MediaOpenGrant(payload: [
            "protocol_version": .string("1.0"),
            "socket_path": .string("/tmp/wom-media-test.sock"),
            "stream_id": .string("tts-remote-error"),
            "trace_id": .string("trace-remote-error"),
            "engine_epoch": .string("engine-remote-error"),
            "generation": .int(52),
            "ticket": .string(String(repeating: "a", count: 64)),
            "direction": .string("engine_to_app"),
            "format": .object([
                "codec": .string("pcm_s16le"),
                "sample_rate": .int(24_000),
                "channels": .int(1),
            ]),
            "max_payload_bytes": .int(65_536),
            "initial_credit_bytes": .int(262_144),
            "expires_in_ms": .int(10_000),
        ])
        let session = EngineMediaPlaybackSession(
            grant: grant,
            transport: transport,
            playback: NativePlaybackActor(backend: backend),
            deliveryReporter: reporter,
            deliveryContext: VoiceDeliverySessionContext(
                trackId: "track-remote-error",
                consumerId: "local-playback",
                unitId: "speech-remote-error"
            )
        )
        let task = Task { await session.run() }
        await transport.waitForSentCount(1)

        await transport.push(
            MediaFrame(
                header: .error(
                    MediaErrorHeader(
                        streamId: "tts-remote-error",
                        generation: 52,
                        code: "provider_failed",
                        message: "failed",
                        retryable: false
                    )
                )
            )
        )

        guard case .failed(.remoteError(code: "provider_failed")) = await task.value else {
            Issue.record("Expected remote media error")
            return
        }
        let updates = await reporter.snapshotUpdates()
        #expect(updates.count == 2)
        #expect(updates[1].stopReason == .mediaError)
        #expect(updates[1].evidence == .queued)
        #expect(updates[1].sourceOffsetFrames == 0)
    }
}


extension EngineMediaPlaybackCursorTests {
    @Test("Stop after media END persists a durable reason without claiming rendered completion")
    func stopAfterMediaEndPersistsReason() async throws {
        let log = MediaPlaybackEventLog()
        let transport = FakeMediaFrameTransport(log: log)
        let backend = MediaPlaybackBackend(log: log)
        let reporter = FakeVoiceDeliveryReporter()
        let grant = try MediaOpenGrant(payload: [
            "protocol_version": .string("1.0"),
            "socket_path": .string("/tmp/wom-media-test.sock"),
            "stream_id": .string("tts-ended-stop"),
            "trace_id": .string("trace-ended-stop"),
            "engine_epoch": .string("engine-ended-stop"),
            "generation": .int(53),
            "ticket": .string(String(repeating: "a", count: 64)),
            "direction": .string("engine_to_app"),
            "format": .object([
                "codec": .string("pcm_s16le"),
                "sample_rate": .int(24_000),
                "channels": .int(1),
            ]),
            "max_payload_bytes": .int(65_536),
            "initial_credit_bytes": .int(262_144),
            "expires_in_ms": .int(10_000),
        ])
        let playback = NativePlaybackActor(backend: backend)
        let session = EngineMediaPlaybackSession(
            grant: grant,
            transport: transport,
            playback: playback,
            deliveryReporter: reporter,
            deliveryContext: VoiceDeliverySessionContext(
                trackId: "track-ended-stop",
                consumerId: "local-playback",
                unitId: "speech-ended-stop"
            )
        )
        let task = Task { await session.run() }
        await transport.waitForSentCount(1)

        let pcm = Data([1, 0, 2, 0])
        await transport.push(
            MediaFrame(
                header: .chunk(
                    MediaChunkHeader(
                        streamId: "tts-ended-stop",
                        generation: 53,
                        sequence: 0,
                        offsetFrames: 0,
                        frameCount: 2,
                        payloadBytes: pcm.count
                    )
                ),
                payload: pcm
            )
        )
        await transport.waitForSentCount(2)
        let digest = SHA256.hash(data: pcm).map {
            String(format: "%02x", $0)
        }.joined()
        await transport.push(
            MediaFrame(
                header: .end(
                    MediaEndHeader(
                        streamId: "tts-ended-stop",
                        generation: 53,
                        totalFrames: 2,
                        totalBytes: Int64(pcm.count),
                        sha256: digest
                    )
                )
            )
        )

        guard case .ended = await task.value else {
            Issue.record("Expected media END before local Stop")
            return
        }

        await session.stop(reason: .userStop)
        let updates = await reporter.snapshotUpdates()
        #expect(updates.count == 3)
        #expect(updates[1].evidence == .scheduled)
        #expect(updates[1].sourceOffsetFrames == 2)
        #expect(updates[2].stopReason == .userStop)
        #expect(updates[2].evidence == .scheduled)
        #expect(updates[2].sourceOffsetFrames == 2)
    }
}


private final class FakePlaybackInterruptionSource:
    PlaybackInterruptionSource, @unchecked Sendable
{
    private let lock = NSLock()
    private var handler: (@Sendable (PlaybackInterruption) -> Void)?

    func start(_ handler: @escaping @Sendable (PlaybackInterruption) -> Void) {
        lock.lock()
        self.handler = handler
        lock.unlock()
    }

    func stop() {
        lock.lock()
        handler = nil
        lock.unlock()
    }

    func triggerDeviceConfigurationChange() {
        lock.lock()
        let callback = handler
        lock.unlock()
        callback?(.deviceConfigurationChanged)
    }
}

@Suite("Engine media device-route recovery")
struct EngineMediaDeviceRecoveryTests {
    @Test("Device configuration change stops old stream and persists media_error")
    func deviceChangeStopsOldGeneration() async throws {
        let log = MediaPlaybackEventLog()
        let transport = FakeMediaFrameTransport(log: log)
        let backend = MediaPlaybackBackend(log: log)
        let reporter = FakeVoiceDeliveryReporter()
        let interruption = FakePlaybackInterruptionSource()
        let grant = try MediaOpenGrant(payload: [
            "protocol_version": .string("1.0"),
            "socket_path": .string("/tmp/wom-media-test.sock"),
            "stream_id": .string("tts-device-change"),
            "trace_id": .string("trace-device-change"),
            "engine_epoch": .string("engine-device-change"),
            "generation": .int(61),
            "ticket": .string(String(repeating: "a", count: 64)),
            "direction": .string("engine_to_app"),
            "format": .object([
                "codec": .string("pcm_s16le"),
                "sample_rate": .int(24_000),
                "channels": .int(1),
            ]),
            "max_payload_bytes": .int(65_536),
            "initial_credit_bytes": .int(262_144),
            "expires_in_ms": .int(10_000),
        ])
        let session = EngineMediaPlaybackSession(
            grant: grant,
            transport: transport,
            playback: NativePlaybackActor(backend: backend),
            deliveryReporter: reporter,
            deliveryContext: VoiceDeliverySessionContext(
                trackId: "track-device",
                consumerId: "local-playback",
                unitId: "speech-device"
            ),
            interruptionSource: interruption
        )
        let task = Task { await session.run() }
        await transport.waitForSentCount(1)

        interruption.triggerDeviceConfigurationChange()

        #expect(await task.value == .cancelled)
        #expect(await transport.closed)
        let updates = await reporter.snapshotUpdates()
        #expect(updates.count == 2)
        #expect(updates[1].stopReason == .mediaError)
        #expect(updates[1].generation == 61)
        #expect(updates[1].sourceOffsetFrames == 0)

        let order = await log.snapshot()
        #expect(order.contains("local_stop"))
        #expect(order.contains("wire_close"))
    }

    @Test("Recovered session must use newer generation and restarts at sentence start")
    func deviceRecoveryUsesNewGenerationFromSentenceStart() async throws {
        let previous = VoiceDeliveryCursorDTO(
            trackId: "track-device",
            consumerId: "local-playback",
            unitId: "speech-device",
            generation: 61,
            sourceOffsetFrames: 240,
            totalSourceFrames: nil,
            evidence: .scheduled,
            stopReason: .mediaError,
            cursorRevision: 2,
            fullyOutput: false
        )
        let reporter = FakeVoiceDeliveryReporter(cursor: previous)
        let log = MediaPlaybackEventLog()
        let transport = FakeMediaFrameTransport(log: log)
        let backend = MediaPlaybackBackend(log: log)
        let grant = try MediaOpenGrant(payload: [
            "protocol_version": .string("1.0"),
            "socket_path": .string("/tmp/wom-media-test.sock"),
            "stream_id": .string("tts-device-recovery"),
            "trace_id": .string("trace-device-recovery"),
            "engine_epoch": .string("engine-device-recovery"),
            "generation": .int(62),
            "ticket": .string(String(repeating: "b", count: 64)),
            "direction": .string("engine_to_app"),
            "format": .object([
                "codec": .string("pcm_s16le"),
                "sample_rate": .int(24_000),
                "channels": .int(1),
            ]),
            "max_payload_bytes": .int(65_536),
            "initial_credit_bytes": .int(262_144),
            "expires_in_ms": .int(10_000),
        ])
        let session = EngineMediaPlaybackSession(
            grant: grant,
            transport: transport,
            playback: NativePlaybackActor(backend: backend),
            deliveryReporter: reporter,
            deliveryContext: VoiceDeliverySessionContext(
                trackId: "track-device",
                consumerId: "local-playback",
                unitId: "speech-device"
            ),
            interruptionSource: nil
        )
        let task = Task { await session.run() }
        await transport.waitForSentCount(1)

        let updates = await reporter.snapshotUpdates()
        #expect(updates.count == 1)
        #expect(updates[0].generation == 62)
        #expect(updates[0].sourceOffsetFrames == 0)
        #expect(updates[0].evidence == .queued)
        #expect(updates[0].expectedCursorRevision == 2)

        await session.stop(reason: .sessionClosed)
        #expect(await task.value == .cancelled)
    }
}
