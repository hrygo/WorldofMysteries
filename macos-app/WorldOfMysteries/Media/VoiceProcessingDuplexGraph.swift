@preconcurrency import AVFoundation
import Foundation

public nonisolated enum VoiceProcessingDuplexFallbackReason: String, Sendable, Equatable {
    case unavailable
    case invalidConfiguration = "invalid_configuration"
    case configurationFailed = "configuration_failed"
}

public nonisolated struct VoiceProcessingDuplexSnapshot: Sendable, Equatable {
    public let voiceProcessingEnabled: Bool
    public let captureActive: Bool
    public let playbackActive: Bool
}

@MainActor
public enum VoiceProcessingDuplexProvision {
    case fullDuplex(VoiceProcessingDuplexStack)
    case halfDuplexPTT(VoiceProcessingDuplexFallbackReason)
}

@MainActor
public struct VoiceProcessingDuplexStack {
    public let microphone: VoiceProcessingMicrophoneSource
    public let playback: VoiceProcessingPlaybackBackend

    fileprivate init(
        microphone: VoiceProcessingMicrophoneSource,
        playback: VoiceProcessingPlaybackBackend
    ) {
        self.microphone = microphone
        self.playback = playback
    }
}

@MainActor
public enum VoiceProcessingDuplexFactory {
    public static func make(
        microphoneConfiguration: MicrophoneCaptureConfiguration = .init(),
        maxQueuedBytes: Int = 256 * 1024
    ) -> VoiceProcessingDuplexProvision {
        guard microphoneConfiguration.targetSampleRate == 16_000,
              (128...4096).contains(microphoneConfiguration.tapFrameCount),
              (2...32).contains(microphoneConfiguration.bufferedChunkLimit),
              maxQueuedBytes > 0
        else {
            return .halfDuplexPTT(.invalidConfiguration)
        }

        let graph = VoiceProcessingAudioGraph(maxQueuedBytes: maxQueuedBytes)
        do {
            try graph.enableVoiceProcessing()
            return .fullDuplex(
                VoiceProcessingDuplexStack(
                    microphone: VoiceProcessingMicrophoneSource(
                        graph: graph,
                        configuration: microphoneConfiguration
                    ),
                    playback: VoiceProcessingPlaybackBackend(graph: graph)
                )
            )
        } catch {
            graph.shutdown()
            return .halfDuplexPTT(.configurationFailed)
        }
    }
}

/// One shared AVAudioEngine for echo-cancelled input and primary voice output.
///
/// Apple voice processing requires input and output I/O nodes in the same engine
/// graph. The graph is configured only while stopped. Playback and capture may
/// overlap; the engine is stopped only when both sides are inactive.
@MainActor
public final class VoiceProcessingAudioGraph {
    private let engine = AVAudioEngine()
    private let player = AVAudioPlayerNode()
    private let maxQueuedBytes: Int

    private var captureActive = false
    private var playbackActive = false
    private var captureContinuation:
        AsyncThrowingStream<MicrophonePCM16Chunk, any Error>.Continuation?
    private var configurationObserver: NSObjectProtocol?

    private var queuedFrames: Int64 = 0
    private var peakQueuedFrames: Int64 = 0
    private var queuedBytes = 0
    private var peakQueuedBytes = 0
    private var saturationCount = 0
    private var underrunCount = 0

    public init(maxQueuedBytes: Int = 256 * 1024) {
        precondition(maxQueuedBytes > 0)
        self.maxQueuedBytes = maxQueuedBytes
        engine.attach(player)
        configurationObserver = NotificationCenter.default.addObserver(
            forName: .AVAudioEngineConfigurationChange,
            object: engine,
            queue: nil
        ) { [weak self] _ in
            Task { @MainActor in
                self?.configurationChanged()
            }
        }
    }

    deinit {
        if let configurationObserver {
            NotificationCenter.default.removeObserver(configurationObserver)
        }
    }

    public var isVoiceProcessingEnabled: Bool {
        engine.inputNode.isVoiceProcessingEnabled
            && engine.outputNode.isVoiceProcessingEnabled
    }

    public func snapshot() -> VoiceProcessingDuplexSnapshot {
        VoiceProcessingDuplexSnapshot(
            voiceProcessingEnabled: isVoiceProcessingEnabled,
            captureActive: captureActive,
            playbackActive: playbackActive
        )
    }

    public func enableVoiceProcessing() throws {
        guard !engine.isRunning, !captureActive, !playbackActive else {
            throw MicrophoneCaptureFailure.alreadyRunning
        }

        let outputFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: 24_000,
            channels: 1,
            interleaved: false
        )
        guard let outputFormat else {
            throw NativePlaybackFailure.invalidFormat
        }

        engine.disconnectNodeOutput(player)
        engine.connect(player, to: engine.mainMixerNode, format: outputFormat)

        do {
            // Enabling either I/O node switches both I/O nodes into voice
            // processing mode. Both are explicitly accessed before the call so
            // the duplex graph is materialized before configuration.
            _ = engine.outputNode
            try engine.inputNode.setVoiceProcessingEnabled(true)
        } catch {
            throw MicrophoneCaptureFailure.deviceUnavailable
        }

        guard isVoiceProcessingEnabled else {
            throw MicrophoneCaptureFailure.deviceUnavailable
        }
    }

    public func startCapture(
        configuration: MicrophoneCaptureConfiguration
    ) throws -> AsyncThrowingStream<MicrophonePCM16Chunk, any Error> {
        guard !captureActive else {
            throw MicrophoneCaptureFailure.alreadyRunning
        }
        guard isVoiceProcessingEnabled else {
            throw MicrophoneCaptureFailure.deviceUnavailable
        }
        guard MicrophoneCaptureSession.authorizationStatus == .authorized else {
            throw MicrophoneCaptureFailure.permissionDenied
        }

        let input = engine.inputNode
        let inputFormat = input.outputFormat(forBus: 0)
        guard inputFormat.channelCount > 0,
              inputFormat.sampleRate.isFinite,
              inputFormat.sampleRate > 0,
              let outputFormat = AVAudioFormat(
                  commonFormat: .pcmFormatFloat32,
                  sampleRate: Double(configuration.targetSampleRate),
                  channels: 1,
                  interleaved: false
              ),
              let converter = AVAudioConverter(
                  from: inputFormat,
                  to: outputFormat
              )
        else {
            throw MicrophoneCaptureFailure.converterUnavailable
        }

        let channel = AsyncThrowingStream<MicrophonePCM16Chunk, any Error>.makeStream(
            bufferingPolicy: .bufferingOldest(configuration.bufferedChunkLimit)
        )
        let sink = channel.continuation
        let targetRate = configuration.targetSampleRate
        captureContinuation = sink

        input.installTap(
            onBus: 0,
            bufferSize: configuration.tapFrameCount,
            format: inputFormat
        ) { buffer, _ in
            guard buffer.frameLength > 0 else { return }
            let ratio = outputFormat.sampleRate / inputFormat.sampleRate
            let estimated = max(
                1,
                Int(ceil(Double(buffer.frameLength) * ratio)) + 32
            )
            guard let output = AVAudioPCMBuffer(
                pcmFormat: outputFormat,
                frameCapacity: AVAudioFrameCount(estimated)
            ) else {
                sink.finish(
                    throwing: MicrophoneCaptureFailure.converterFailed
                )
                return
            }

            var supplied = false
            var error: NSError?
            let status = converter.convert(
                to: output,
                error: &error
            ) { _, inputStatus in
                if supplied {
                    inputStatus.pointee = .noDataNow
                    return nil
                }
                supplied = true
                inputStatus.pointee = .haveData
                return buffer
            }

            guard error == nil,
                  status != .error,
                  output.frameLength > 0,
                  let samples = output.floatChannelData?[0]
            else {
                sink.finish(
                    throwing: MicrophoneCaptureFailure.converterFailed
                )
                return
            }

            let frameCount = Int(output.frameLength)
            let pcm = PCM16Quantizer.encode(samples, count: frameCount)
            guard !pcm.isEmpty else { return }
            let result = sink.yield(
                MicrophonePCM16Chunk(
                    data: pcm,
                    sampleRate: targetRate,
                    channels: 1,
                    frameCount: frameCount
                )
            )
            if case .dropped = result {
                sink.finish(
                    throwing: MicrophoneCaptureFailure.bufferOverflow
                )
            }
        }

        do {
            try startEngineIfNeeded()
            captureActive = true
            return channel.stream
        } catch {
            input.removeTap(onBus: 0)
            captureContinuation = nil
            sink.finish(throwing: error)
            throw error
        }
    }

    public func stopCapture() {
        guard captureActive else { return }
        engine.inputNode.removeTap(onBus: 0)
        captureActive = false
        captureContinuation?.finish()
        captureContinuation = nil
        stopEngineIfIdle()
    }

    public func startPlayback(
        sampleRate: Int,
        channels: Int,
        outputGain: Double
    ) throws {
        guard !playbackActive else {
            throw NativePlaybackFailure.invalidState
        }
        guard isVoiceProcessingEnabled,
              sampleRate == 24_000,
              channels == 1,
              outputGain.isFinite,
              outputGain > 0,
              outputGain <= 1.0
        else {
            throw NativePlaybackFailure.invalidFormat
        }

        queuedFrames = 0
        peakQueuedFrames = 0
        queuedBytes = 0
        peakQueuedBytes = 0
        saturationCount = 0
        underrunCount = 0

        try startEngineIfNeeded()
        player.volume = Float(outputGain)
        player.play()
        playbackActive = true
    }

    public func enqueuePlayback(
        pcm16: Data,
        frameCount: Int
    ) throws {
        guard playbackActive,
              frameCount > 0,
              pcm16.count == frameCount * MemoryLayout<Int16>.size,
              let format = AVAudioFormat(
                  commonFormat: .pcmFormatInt16,
                  sampleRate: 24_000,
                  channels: 1,
                  interleaved: false
              )
        else {
            throw NativePlaybackFailure.invalidChunk
        }

        guard queuedBytes + pcm16.count <= maxQueuedBytes else {
            saturationCount += 1
            throw NativePlaybackFailure.queueCapacityExceeded
        }

        if !player.isPlaying {
            underrunCount += 1
            player.play()
        }

        guard let buffer = AVAudioPCMBuffer(
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

        let bytes = pcm16.count
        queuedFrames += Int64(frameCount)
        queuedBytes += bytes
        peakQueuedFrames = max(peakQueuedFrames, queuedFrames)
        peakQueuedBytes = max(peakQueuedBytes, queuedBytes)

        player.scheduleBuffer(
            buffer,
            completionCallbackType: .dataPlayedBack
        ) { [weak self] _ in
            Task { @MainActor in
                self?.didPlayBuffer(frames: frameCount, bytes: bytes)
            }
        }
    }

    public func playbackMetrics() -> NativePlaybackBackendMetrics {
        NativePlaybackBackendMetrics(
            queuedFrames: queuedFrames,
            peakQueuedFrames: peakQueuedFrames,
            queuedBytes: queuedBytes,
            peakQueuedBytes: peakQueuedBytes,
            queueCapacityBytes: maxQueuedBytes,
            saturationCount: saturationCount,
            underrunCount: underrunCount
        )
    }

    public func stopPlayback() {
        guard playbackActive else { return }
        player.stop()
        playbackActive = false
        queuedFrames = 0
        queuedBytes = 0
        stopEngineIfIdle()
    }

    public func shutdown() {
        if captureActive {
            engine.inputNode.removeTap(onBus: 0)
        }
        captureActive = false
        playbackActive = false
        captureContinuation?.finish()
        captureContinuation = nil
        player.stop()
        engine.stop()
        queuedFrames = 0
        queuedBytes = 0
    }

    private func startEngineIfNeeded() throws {
        if engine.isRunning { return }
        engine.prepare()
        do {
            try engine.start()
        } catch {
            throw MicrophoneCaptureFailure.deviceUnavailable
        }
    }

    private func stopEngineIfIdle() {
        guard !captureActive, !playbackActive else { return }
        engine.stop()
    }

    private func didPlayBuffer(frames: Int, bytes: Int) {
        queuedFrames = max(0, queuedFrames - Int64(frames))
        queuedBytes = max(0, queuedBytes - bytes)
    }

    private func configurationChanged() {
        // A changed device graph invalidates the AEC reference. Do not continue
        // using old input/output assumptions across the route change.
        if captureActive {
            engine.inputNode.removeTap(onBus: 0)
            captureContinuation?.finish(
                throwing: MicrophoneCaptureFailure.deviceUnavailable
            )
        }
        captureContinuation = nil
        captureActive = false
        playbackActive = false
        player.stop()
        engine.stop()
        queuedFrames = 0
        queuedBytes = 0
    }
}

@MainActor
public final class VoiceProcessingMicrophoneSource: MicrophonePCMSource {
    private let graph: VoiceProcessingAudioGraph
    private let configuration: MicrophoneCaptureConfiguration

    fileprivate init(
        graph: VoiceProcessingAudioGraph,
        configuration: MicrophoneCaptureConfiguration
    ) {
        self.graph = graph
        self.configuration = configuration
    }

    public func start()
        throws -> AsyncThrowingStream<MicrophonePCM16Chunk, any Error>
    {
        try graph.startCapture(configuration: configuration)
    }

    public func stop() {
        graph.stopCapture()
    }
}

public actor VoiceProcessingPlaybackBackend: NativePCMPlaybackBackend {
    private let graph: VoiceProcessingAudioGraph

    fileprivate init(graph: VoiceProcessingAudioGraph) {
        self.graph = graph
    }

    public func start(
        sampleRate: Int,
        channels: Int,
        outputGain: Double
    ) async throws {
        try await graph.startPlayback(
            sampleRate: sampleRate,
            channels: channels,
            outputGain: outputGain
        )
    }

    public func enqueue(pcm16: Data, frameCount: Int) async throws {
        try await graph.enqueuePlayback(
            pcm16: pcm16,
            frameCount: frameCount
        )
    }

    public func metrics() async -> NativePlaybackBackendMetrics {
        await graph.playbackMetrics()
    }

    public func stop() async {
        await graph.stopPlayback()
    }
}
