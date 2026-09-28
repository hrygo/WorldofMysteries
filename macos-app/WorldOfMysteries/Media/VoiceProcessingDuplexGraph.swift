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
        maxQueuedBytes: Int = NativePlaybackCapacity.sealedUtteranceBytes
    ) -> VoiceProcessingDuplexProvision {
        guard microphoneConfiguration.targetSampleRate == SpeechRailRealtimeWire.sampleRate,
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

    /// - Parameter maxQueuedBytes: Required on purpose. The playback queue must
    ///   hold one whole sealed utterance, and that budget belongs to
    ///   ``NativePlaybackCapacity/sealedUtteranceBytes``. A default here would be
    ///   a second, silently divergent answer to the same question — and the old
    ///   one (256 KiB) was small enough to reject a valid render. Callers state
    ///   the budget they were given.
    public init(maxQueuedBytes: Int) {
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

        Self.installCaptureTap(
            on: input,
            bufferSize: configuration.tapFrameCount,
            outputFormat: outputFormat,
            sink: sink,
            targetRate: targetRate
        )

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

    /// Installs the capture tap from a nonisolated context.
    ///
    /// `AVAudioEngine` dispatches this callback on its realtime audio thread.
    /// A closure formed inside this `@MainActor` type inherits that isolation,
    /// and the first buffer trips Swift's isolation check and traps with
    /// SIGTRAP -- only on a real microphone, which is why the automated suite
    /// never saw it. Building the closure here keeps it off the main actor.
    /// The mono format matching a delivered format's rate and sample type.
    nonisolated private static func monoFormat(from format: AVAudioFormat) -> AVAudioFormat {
        AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: format.sampleRate,
            channels: 1,
            interleaved: false
        )!
    }

    nonisolated private static func installCaptureTap(
        on node: AVAudioNode,
        bufferSize: AVAudioFrameCount,
        outputFormat: AVAudioFormat,
        sink: AsyncThrowingStream<MicrophonePCM16Chunk, any Error>.Continuation,
        targetRate: Int
    ) {
        // The converter is built from the format the engine *delivers*, not
        // from the one the input node advertised before voice processing was
        // switched on.
        //
        // With VoiceProcessingIO the node reports mono, but the tap is handed
        // the raw 9-channel layout (microphone plus the AEC reference
        // channels). A converter built from the advertised format accepts
        // those buffers and emits pure silence -- every frame zero, no error.
        // The turn then records a mute microphone and reports success. A mock
        // hands over a well-formed mono buffer, so no test ever sees it.
        let converter = CaptureConverter(target: outputFormat)
        node.installTap(
            onBus: 0,
            bufferSize: bufferSize,
            format: nil
        ) { buffer, _ in
            guard buffer.frameLength > 0 else { return }
            // VoiceProcessingIO hands over its raw 9-channel layout: channel 0
            // is the microphone, the rest are the AEC reference channels.
            // Extracting channel 0 explicitly is deliberate -- asking
            // AVAudioConverter to downmix that layout yields frames of silence
            // rather than an error, so a turn records a mute microphone and
            // reports success.
            let source: AVAudioPCMBuffer
            if buffer.format.channelCount > 1, let planes = buffer.floatChannelData {
                guard let mono = AVAudioPCMBuffer(
                    pcmFormat: Self.monoFormat(from: buffer.format),
                    frameCapacity: buffer.frameLength
                ), let out = mono.floatChannelData?[0] else {
                    sink.finish(
                        throwing: MicrophoneCaptureFailure.converterFailed
                    )
                    return
                }
                mono.frameLength = buffer.frameLength
                out.update(from: planes[0], count: Int(buffer.frameLength))
                source = mono
            } else {
                source = buffer
            }
            // The converter is built for what actually reaches it, so a
            // genuine route change is caught instead of silently resampling.
            guard converter.accepts(source.format) else {
                sink.finish(
                    throwing: MicrophoneCaptureFailure.converterFailed
                )
                return
            }
            let ratio = outputFormat.sampleRate / source.format.sampleRate
            let estimated = max(
                1,
                Int(ceil(Double(source.frameLength) * ratio)) + 32
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

            var error: NSError?
            let status = converter.convert(
                to: output, buffer: source, error: &error)

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

/// Resamples whatever the engine delivers down to the mono wire rate,
/// rebuilding itself whenever the delivered format changes.
///
/// Deliberately declared at file scope rather than inside the graph type: the
/// graph is `@MainActor`, and a nested type would inherit that isolation,
/// which the capture tap cannot satisfy on the audio realtime thread.
///
/// The format has to come from the buffers, not from `outputFormat(forBus: 0)`
/// read before voice processing is enabled. That reports mono while the tap is
/// handed VoiceProcessingIO's 9-channel layout, and a converter built for the
/// advertised shape returns frames of silence instead of failing.
nonisolated private final class CaptureConverter: @unchecked Sendable {
    private let target: AVAudioFormat
    private let lock = NSLock()
    private var source: AVAudioFormat?
    private var converter: AVAudioConverter?

    init(target: AVAudioFormat) {
        self.target = target
    }

    /// True when a converter for `format` is the one already in place, or when
    /// one can be built for it now.
    func accepts(_ format: AVAudioFormat) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        if let source, source == format { return true }
        guard format.channelCount > 0,
              format.sampleRate.isFinite,
              format.sampleRate > 0
        else { return false }
        guard let built = AVAudioConverter(from: format, to: target) else {
            return false
        }
        source = format
        converter = built
        return true
    }

    func convert(
        to output: AVAudioPCMBuffer,
        buffer: AVAudioPCMBuffer,
        error: inout NSError?
    ) -> AVAudioConverterOutputStatus {
        lock.lock()
        let active = converter
        lock.unlock()
        guard let active else { return .error }
        var supplied = false
        return active.convert(to: output, error: &error) { _, status in
            if supplied {
                status.pointee = .noDataNow
                return nil
            }
            supplied = true
            status.pointee = .haveData
            return buffer
        }
    }
}
