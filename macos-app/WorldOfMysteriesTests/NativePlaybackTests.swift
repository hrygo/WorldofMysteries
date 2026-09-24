import Foundation
import Testing
@testable import WorldOfMysteriesCore

private actor PlaybackEventRecorder {
    private(set) var events: [String] = []

    func record(_ event: String) {
        events.append(event)
    }

    func snapshot() -> [String] { events }
}

private actor FakeNativePCMPlaybackBackend: NativePCMPlaybackBackend {
    private let recorder: PlaybackEventRecorder
    private(set) var started: [(Int, Int, Double)] = []
    private(set) var payloads: [Data] = []
    private(set) var stopCount = 0

    init(recorder: PlaybackEventRecorder) {
        self.recorder = recorder
    }

    func start(sampleRate: Int, channels: Int, outputGain: Double) async throws {
        started.append((sampleRate, channels, outputGain))
        await recorder.record("backend.start")
    }

    func enqueue(pcm16: Data, frameCount: Int) async throws {
        #expect(pcm16.count == frameCount * 2)
        payloads.append(pcm16)
        await recorder.record("backend.enqueue")
    }

    func stop() async {
        stopCount += 1
        await recorder.record("backend.stop")
    }
}

@Suite("Native TTS playback generation boundary")
struct NativePlaybackTests {
    private func makePlayer() -> (
        NativePlaybackActor,
        FakeNativePCMPlaybackBackend,
        PlaybackEventRecorder
    ) {
        let recorder = PlaybackEventRecorder()
        let backend = FakeNativePCMPlaybackBackend(recorder: recorder)
        return (NativePlaybackActor(backend: backend), backend, recorder)
    }

    private func header(
        generation: Int64,
        sequence: Int64 = 0,
        offsetFrames: Int64 = 0,
        frameCount: Int = 2
    ) -> MediaChunkHeader {
        MediaChunkHeader(
            streamId: "tts_1",
            generation: generation,
            sequence: sequence,
            offsetFrames: offsetFrames,
            frameCount: frameCount,
            payloadBytes: frameCount * 2
        )
    }

    @Test("SpeechRail PCM is scheduled as 24 kHz mono and offsets stay contiguous")
    func schedulesPCM() async throws {
        let (player, backend, _) = makePlayer()
        try await player.begin(
            streamID: "tts_1",
            generation: 3,
            format: .init(sampleRate: 24_000)
        )

        #expect(try await player.accept(header(generation: 3), payload: Data([1, 0, 2, 0])))
        #expect(
            try await player.accept(
                header(generation: 3, sequence: 1, offsetFrames: 2, frameCount: 1),
                payload: Data([3, 0])
            )
        )
        try await player.finishMediaStream(generation: 3, totalFrames: 3)

        let snapshot = try #require(await player.snapshot())
        #expect(snapshot.scheduledFrames == 3)
        #expect(snapshot.mediaStreamEnded)
        #expect(snapshot.evidence == .scheduled)
        #expect(snapshot.mode == .normal)
        #expect(snapshot.outputGain == 1.0)
        #expect(await backend.started == [(24_000, 1, 1.0)])
        #expect(await backend.payloads == [Data([1, 0, 2, 0]), Data([3, 0])])
    }

    @Test("Local stop invalidates playback before provider cancellation")
    func stopOrdering() async throws {
        let (player, _, recorder) = makePlayer()
        try await player.begin(
            streamID: "tts_1",
            generation: 7,
            format: .init(sampleRate: 24_000)
        )

        await player.stop {
            await recorder.record("provider.cancel")
        }

        let events = await recorder.snapshot()
        #expect(events.suffix(2) == ["backend.stop", "provider.cancel"])
        #expect(await player.snapshot() == nil)
        #expect(
            try await player.accept(
                header(generation: 7),
                payload: Data([0, 0, 0, 0])
            ) == false
        )
    }

    @Test("Late prior-generation PCM is dropped after a new generation starts")
    func staleGenerationIsDropped() async throws {
        let (player, _, recorder) = makePlayer()
        try await player.begin(
            streamID: "tts_1",
            generation: 1,
            format: .init(sampleRate: 24_000)
        )
        await player.stop { await recorder.record("provider.cancel.1") }
        try await player.begin(
            streamID: "tts_1",
            generation: 2,
            format: .init(sampleRate: 24_000)
        )

        #expect(
            try await player.accept(
                header(generation: 1),
                payload: Data([0, 0, 0, 0])
            ) == false
        )
        let snapshot = try #require(await player.snapshot())
        #expect(snapshot.generation == 2)
        #expect(snapshot.scheduledFrames == 0)
    }

    @Test("Provider completed does not claim audible device completion")
    func providerCompletionIsNotDeviceCompletion() async throws {
        let (player, _, _) = makePlayer()
        try await player.begin(
            streamID: "tts_1",
            generation: 11,
            format: .init(sampleRate: 24_000)
        )
        _ = try await player.accept(
            header(generation: 11),
            payload: Data([1, 0, 2, 0])
        )
        try await player.finishMediaStream(generation: 11, totalFrames: 2)
        try await player.observeProviderTerminal(.completed, generation: 11)

        var snapshot = try #require(await player.snapshot())
        #expect(snapshot.providerCompleted)
        #expect(!snapshot.devicePlaybackProvenComplete)
        #expect(snapshot.evidence == .scheduled)

        try await player.reportRenderedEstimate(throughFrames: 2, generation: 11)
        snapshot = try #require(await player.snapshot())
        #expect(snapshot.evidence == .renderedEstimate)
        #expect(!snapshot.devicePlaybackProvenComplete)
    }

    @Test("Invalid PCM shape and non-contiguous offsets fail closed")
    func malformedPCM() async throws {
        let (player, _, _) = makePlayer()
        try await player.begin(
            streamID: "tts_1",
            generation: 5,
            format: .init(sampleRate: 24_000)
        )

        await #expect(throws: NativePlaybackFailure.invalidChunk) {
            try await player.accept(
                header(generation: 5),
                payload: Data([0, 0])
            )
        }
        await #expect(throws: NativePlaybackFailure.invalidOffset) {
            try await player.accept(
                header(generation: 5, offsetFrames: 1),
                payload: Data([0, 0, 0, 0])
            )
        }
    }
}


    @Test("Low-stimulation mode caps local gain while preserving a single clear stream")
    func lowStimulationGain() async throws {
        let (player, backend, _) = makePlayer()
        try await player.begin(
            streamID: "tts_low",
            generation: 21,
            format: .init(sampleRate: 24_000),
            mode: .lowStimulation
        )

        let snapshot = try #require(await player.snapshot())
        #expect(snapshot.mode == .lowStimulation)
        #expect(snapshot.outputGain == 0.45)
        #expect(await backend.started == [(24_000, 1, 0.45)])

        await #expect(throws: NativePlaybackFailure.invalidState) {
            try await player.begin(
                streamID: "tts_overlap",
                generation: 22,
                format: .init(sampleRate: 24_000),
                mode: .normal
            )
        }
    }
