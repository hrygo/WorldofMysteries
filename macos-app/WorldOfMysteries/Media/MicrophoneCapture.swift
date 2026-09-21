@preconcurrency import AVFoundation
import Foundation

public nonisolated enum MicrophoneCaptureFailure: Error, Sendable, Equatable, LocalizedError {
    case permissionDenied
    case deviceUnavailable
    case invalidDeviceFormat
    case converterUnavailable
    case converterFailed
    case bufferOverflow
    case alreadyRunning

    public var errorDescription: String? {
        switch self {
        case .permissionDenied:
            "Microphone permission is required for voice input."
        case .bufferOverflow:
            "Microphone input overflowed its bounded realtime buffer."
        default:
            "Microphone capture could not produce valid realtime PCM."
        }
    }
}

public nonisolated enum MicrophoneAuthorizationStatus: Sendable, Equatable {
    case notDetermined
    case denied
    case restricted
    case authorized
}

public nonisolated struct MicrophonePCM16Chunk: Sendable, Equatable {
    public let data: Data
    public let sampleRate: Int
    public let channels: Int
    public let frameCount: Int

    public init(data: Data, sampleRate: Int, channels: Int, frameCount: Int) {
        self.data = data
        self.sampleRate = sampleRate
        self.channels = channels
        self.frameCount = frameCount
    }
}

public nonisolated struct MicrophoneCaptureConfiguration: Sendable, Equatable {
    public let targetSampleRate: Int
    public let tapFrameCount: AVAudioFrameCount
    public let bufferedChunkLimit: Int

    public init(
        targetSampleRate: Int = 16_000,
        tapFrameCount: AVAudioFrameCount = 960,
        bufferedChunkLimit: Int = 8
    ) {
        self.targetSampleRate = targetSampleRate
        self.tapFrameCount = tapFrameCount
        self.bufferedChunkLimit = bufferedChunkLimit
    }

    fileprivate func validate() throws {
        guard targetSampleRate == 16_000,
              (128...4096).contains(tapFrameCount),
              (2...32).contains(bufferedChunkLimit)
        else {
            throw MicrophoneCaptureFailure.invalidDeviceFormat
        }
    }
}

public nonisolated enum PCM16Quantizer {
    public static func encode(_ monoSamples: UnsafePointer<Float>, count: Int) -> Data {
        guard count > 0 else { return Data() }
        var data = Data(count: count * MemoryLayout<Int16>.size)
        data.withUnsafeMutableBytes { raw in
            let output = raw.bindMemory(to: Int16.self)
            for index in 0..<count {
                let sample = max(-1.0, min(1.0, monoSamples[index]))
                let scaled = sample < 0 ? sample * 32768.0 : sample * 32767.0
                output[index] = Int16(
                    max(Float(Int16.min), min(Float(Int16.max), scaled.rounded()))
                ).littleEndian
            }
        }
        return data
    }
}

/// One push-to-talk microphone capture lifetime.
///
/// The audio callback performs only bounded format conversion, sample
/// quantization and an AsyncThrowingStream yield. It never performs network,
/// JSON, filesystem, model, database or MainActor work. The stream is bounded;
/// if the consumer cannot keep up, capture fails rather than silently dropping
/// samples and submitting a partial utterance.
@MainActor
public final class MicrophoneCaptureSession {
    private let configuration: MicrophoneCaptureConfiguration
    private let engine = AVAudioEngine()
    private var continuation: AsyncThrowingStream<MicrophonePCM16Chunk, any Error>.Continuation?
    private var streamStorage: AsyncThrowingStream<MicrophonePCM16Chunk, any Error>?
    private var running = false

    public init(configuration: MicrophoneCaptureConfiguration = .init()) throws {
        try configuration.validate()
        self.configuration = configuration
    }

    public static var authorizationStatus: MicrophoneAuthorizationStatus {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .notDetermined: .notDetermined
        case .denied: .denied
        case .restricted: .restricted
        case .authorized: .authorized
        @unknown default: .denied
        }
    }

    public static func requestAuthorization() async -> Bool {
        if authorizationStatus == .authorized { return true }
        if authorizationStatus == .denied || authorizationStatus == .restricted {
            return false
        }
        return await withCheckedContinuation { continuation in
            AVCaptureDevice.requestAccess(for: .audio) { granted in
                continuation.resume(returning: granted)
            }
        }
    }

    public func start() throws -> AsyncThrowingStream<MicrophonePCM16Chunk, any Error> {
        guard !running else { throw MicrophoneCaptureFailure.alreadyRunning }
        guard Self.authorizationStatus == .authorized else {
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
              let converter = AVAudioConverter(from: inputFormat, to: outputFormat)
        else {
            throw MicrophoneCaptureFailure.converterUnavailable
        }

        let channel = AsyncThrowingStream<MicrophonePCM16Chunk, any Error>.makeStream(
            bufferingPolicy: .bufferingOldest(configuration.bufferedChunkLimit)
        )
        streamStorage = channel.stream
        continuation = channel.continuation
        let sink = channel.continuation
        let targetRate = configuration.targetSampleRate

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
                sink.finish(throwing: MicrophoneCaptureFailure.converterFailed)
                return
            }

            var supplied = false
            var error: NSError?
            let status = converter.convert(to: output, error: &error) { _, inputStatus in
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
                sink.finish(throwing: MicrophoneCaptureFailure.converterFailed)
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
                sink.finish(throwing: MicrophoneCaptureFailure.bufferOverflow)
            }
        }

        do {
            engine.prepare()
            try engine.start()
            running = true
            return channel.stream
        } catch {
            input.removeTap(onBus: 0)
            continuation?.finish(throwing: error)
            continuation = nil
            streamStorage = nil
            throw error
        }
    }

    public func stop() {
        guard running else { return }
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        running = false
        continuation?.finish()
        continuation = nil
        streamStorage = nil
    }
}


@MainActor
public protocol MicrophonePCMSource: AnyObject {
    func start() throws -> AsyncThrowingStream<MicrophonePCM16Chunk, any Error>
    func stop()
}

extension MicrophoneCaptureSession: MicrophonePCMSource {}
