import Foundation

#if canImport(AVFoundation)
@preconcurrency import AVFoundation
#endif

public nonisolated enum NativePlaybackFailure: Error, Sendable, Equatable, LocalizedError {
    case invalidFormat
    case invalidGeneration
    case invalidChunk
    case invalidOffset
    case invalidState
    case backendFailure

    public var errorDescription: String? {
        "The local voice playback stream violated its playback contract."
    }
}

public nonisolated enum PlaybackProviderTerminal: String, Sendable, Equatable {
    case none
    case completed
    case failed
    case cancelled
}

public nonisolated enum PlaybackCompletionEvidence: String, Sendable, Equatable {
    case scheduled
    case renderedEstimate = "rendered_estimate"
}

public nonisolated enum VoicePlaybackMode: String, Sendable, Equatable {
    case normal
    case lowStimulation = "low_stimulation"

    public var outputGain: Double {
        switch self {
        case .normal: 1.0
        case .lowStimulation: 0.45
        }
    }
}

public nonisolated struct NativePlaybackSnapshot: Sendable, Equatable {
    public let streamID: String
    public let generation: Int64
    public let scheduledFrames: Int64
    public let renderedEstimateFrames: Int64
    public let providerTerminal: PlaybackProviderTerminal
    public let mediaStreamEnded: Bool
    public let evidence: PlaybackCompletionEvidence
    public let mode: VoicePlaybackMode
    public let outputGain: Double

    public var providerCompleted: Bool { providerTerminal == .completed }

    /// Provider completion is not device playback completion. The first W-V03
    /// implementation exposes only schedule/render estimates; measured audible
    /// completion requires a later device/loopback evidence source.
    public var devicePlaybackProvenComplete: Bool { false }
}

public nonisolated protocol NativePCMPlaybackBackend: Sendable {
    func start(sampleRate: Int, channels: Int, outputGain: Double) async throws
    func enqueue(pcm16: Data, frameCount: Int) async throws
    func stop() async
}

/// Generation-safe local TTS playback coordinator.
///
/// It owns only local media presentation state. Domain state is never mutated
/// here. `stop` invalidates the local generation and stops the device before it
/// awaits provider cancellation, so late PCM cannot resurrect old speech.
public actor NativePlaybackActor {
    private struct ActivePlayback: Sendable {
        let streamID: String
        let generation: Int64
        let format: MediaFormat
        let mode: VoicePlaybackMode
        let outputGain: Double
        var scheduledFrames: Int64 = 0
        var renderedEstimateFrames: Int64 = 0
        var providerTerminal: PlaybackProviderTerminal = .none
        var mediaStreamEnded = false
    }

    private let backend: any NativePCMPlaybackBackend
    private var active: ActivePlayback?
    private var highestGeneration: Int64 = -1

    public init(backend: any NativePCMPlaybackBackend) {
        self.backend = backend
    }

    public func begin(
        streamID: String,
        generation: Int64,
        format: MediaFormat,
        mode: VoicePlaybackMode = .normal
    ) async throws {
        guard active == nil else { throw NativePlaybackFailure.invalidState }
        guard !streamID.isEmpty, generation >= 0, generation > highestGeneration else {
            throw NativePlaybackFailure.invalidGeneration
        }
        guard format.codec == "pcm_s16le",
              format.sampleRate == 24_000,
              format.channels == 1
        else {
            throw NativePlaybackFailure.invalidFormat
        }

        do {
            try await backend.start(
                sampleRate: format.sampleRate,
                channels: format.channels,
                outputGain: mode.outputGain
            )
        } catch {
            throw NativePlaybackFailure.backendFailure
        }
        highestGeneration = generation
        active = ActivePlayback(
            streamID: streamID,
            generation: generation,
            format: format,
            mode: mode,
            outputGain: mode.outputGain
        )
    }

    /// Returns false for a stale generation. Stale PCM is intentionally dropped
    /// instead of surfacing as a user-visible playback failure.
    @discardableResult
    public func accept(_ header: MediaChunkHeader, payload: Data) async throws -> Bool {
        guard let current = active else {
            if header.generation <= highestGeneration { return false }
            throw NativePlaybackFailure.invalidState
        }
        guard header.generation == current.generation else {
            if header.generation < current.generation { return false }
            throw NativePlaybackFailure.invalidGeneration
        }
        guard header.streamId == current.streamID,
              header.frameCount > 0,
              header.payloadBytes == payload.count,
              payload.count == header.frameCount * 2,
              payload.count.isMultiple(of: 2)
        else {
            throw NativePlaybackFailure.invalidChunk
        }
        guard header.offsetFrames == current.scheduledFrames else {
            throw NativePlaybackFailure.invalidOffset
        }

        let generation = current.generation
        do {
            try await backend.enqueue(pcm16: payload, frameCount: header.frameCount)
        } catch {
            throw NativePlaybackFailure.backendFailure
        }

        // Actor reentrancy permits stop() to run while the backend is awaited.
        // In that case the backend stop has cleared the just-scheduled audio and
        // this stale continuation must not advance presentation state.
        guard var stillActive = active, stillActive.generation == generation else {
            return false
        }
        stillActive.scheduledFrames += Int64(header.frameCount)
        active = stillActive
        return true
    }

    public func finishMediaStream(
        generation: Int64,
        totalFrames: Int64
    ) throws {
        guard var current = active, current.generation == generation else {
            throw NativePlaybackFailure.invalidGeneration
        }
        guard totalFrames == current.scheduledFrames else {
            throw NativePlaybackFailure.invalidOffset
        }
        current.mediaStreamEnded = true
        active = current
    }

    public func observeProviderTerminal(
        _ terminal: PlaybackProviderTerminal,
        generation: Int64
    ) throws {
        guard terminal != .none else { throw NativePlaybackFailure.invalidState }
        guard var current = active, current.generation == generation else {
            throw NativePlaybackFailure.invalidGeneration
        }
        current.providerTerminal = terminal
        active = current
    }

    public func reportRenderedEstimate(
        throughFrames: Int64,
        generation: Int64
    ) throws {
        guard var current = active, current.generation == generation else {
            throw NativePlaybackFailure.invalidGeneration
        }
        guard throughFrames >= current.renderedEstimateFrames,
              throughFrames <= current.scheduledFrames
        else {
            throw NativePlaybackFailure.invalidOffset
        }
        current.renderedEstimateFrames = throughFrames
        active = current
    }

    public func snapshot() -> NativePlaybackSnapshot? {
        guard let current = active else { return nil }
        let evidence: PlaybackCompletionEvidence = current.renderedEstimateFrames > 0
            ? .renderedEstimate
            : .scheduled
        return NativePlaybackSnapshot(
            streamID: current.streamID,
            generation: current.generation,
            scheduledFrames: current.scheduledFrames,
            renderedEstimateFrames: current.renderedEstimateFrames,
            providerTerminal: current.providerTerminal,
            mediaStreamEnded: current.mediaStreamEnded,
            evidence: evidence,
            mode: current.mode,
            outputGain: current.outputGain
        )
    }

    /// Local invalidation/device stop is completed before provider cancellation
    /// is awaited. This ordering is the barge-in/Stop safety boundary.
    public func stop(providerCancel: @Sendable () async -> Void) async {
        if let current = active {
            highestGeneration = max(highestGeneration, current.generation)
        }
        active = nil
        await backend.stop()
        await providerCancel()
    }
}

#if canImport(AVFoundation)
/// Minimal native PCM backend for the first W-V03 playback slice.
///
/// It schedules SpeechRail's 24 kHz mono signed-16-bit PCM directly. Scheduling
/// completion is deliberately not exposed as audible completion evidence.
public actor AVAudioEnginePCMPlaybackBackend: NativePCMPlaybackBackend {
    private let engine = AVAudioEngine()
    private let player = AVAudioPlayerNode()
    private var format: AVAudioFormat?
    private var running = false

    public init() {
        engine.attach(player)
    }

    public func start(sampleRate: Int, channels: Int, outputGain: Double) async throws {
        guard sampleRate == 24_000, channels == 1,
              outputGain.isFinite, outputGain > 0, outputGain <= 1.0,
              let format = AVAudioFormat(
                  commonFormat: .pcmFormatInt16,
                  sampleRate: Double(sampleRate),
                  channels: AVAudioChannelCount(channels),
                  interleaved: false
              )
        else {
            throw NativePlaybackFailure.invalidFormat
        }

        if running {
            player.stop()
            engine.stop()
        }
        engine.disconnectNodeOutput(player)
        engine.connect(player, to: engine.mainMixerNode, format: format)
        engine.prepare()
        do {
            try engine.start()
        } catch {
            throw NativePlaybackFailure.backendFailure
        }
        player.volume = Float(outputGain)
        player.play()
        self.format = format
        running = true
    }

    public func enqueue(pcm16: Data, frameCount: Int) async throws {
        guard running, let format,
              frameCount > 0,
              pcm16.count == frameCount * MemoryLayout<Int16>.size,
              let buffer = AVAudioPCMBuffer(
                  pcmFormat: format,
                  frameCapacity: AVAudioFrameCount(frameCount)
              ),
              let samples = buffer.int16ChannelData?[0]
        else {
            throw NativePlaybackFailure.invalidChunk
        }

        buffer.frameLength = AVAudioFrameCount(frameCount)
        pcm16.withUnsafeBytes { raw in
            guard let base = raw.baseAddress else { return }
            memcpy(samples, base, pcm16.count)
        }
        await player.scheduleBuffer(buffer)
    }

    public func stop() async {
        player.stop()
        engine.stop()
        format = nil
        running = false
    }
}
#endif
