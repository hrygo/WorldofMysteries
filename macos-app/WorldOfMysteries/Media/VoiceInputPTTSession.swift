import Foundation

public nonisolated enum VoiceInputPTTPhase: Sendable, Equatable {
    case idle
    case capturing
    case finalizing
    case terminal
}

/// Push-to-talk orchestration for one logical player utterance.
///
/// Ordering is intentional:
/// 1. capture produces bounded PCM chunks;
/// 2. one consumer appends them serially to SpeechRail;
/// 3. stopCapture finishes the local stream;
/// 4. finish waits for that consumer to drain;
/// 5. only then may the ASR turn send commit -> clear.
///
/// This makes the local append-drain fence executable rather than a timing
/// assumption. No Advice or Domain COMMIT occurs in this layer.
@MainActor
public final class VoiceInputPTTSession {
    private let connection: SpeechRailRealtimeASRConnection
    private let microphone: any MicrophonePCMSource
    private let finalizationTimeout: Duration

    public private(set) var phase: VoiceInputPTTPhase = .idle
    public private(set) var inputTurnID: UUID?

    private var coordinator: SpeechRailRealtimeASRTurnCoordinator?
    private var pumpTask: Task<Void, Never>?
    private var pumpFailure: SpeechRailRealtimeASRFailure?

    public init(
        connection: SpeechRailRealtimeASRConnection,
        microphone: any MicrophonePCMSource,
        finalizationTimeout: Duration = .seconds(10)
    ) {
        self.connection = connection
        self.microphone = microphone
        self.finalizationTimeout = finalizationTimeout
    }

    @discardableResult
    public func start() async throws -> UUID {
        guard phase == .idle else {
            throw SpeechRailRealtimeASRFailure.invalidState
        }

        _ = try await connection.connect()
        let coordinator = SpeechRailRealtimeASRTurnCoordinator(
            connection: connection,
            finalizationTimeout: finalizationTimeout
        )
        let turnID = try await coordinator.start()

        let stream: AsyncThrowingStream<MicrophonePCM16Chunk, any Error>
        do {
            stream = try microphone.start()
        } catch {
            await coordinator.cancel()
            throw error
        }

        self.coordinator = coordinator
        inputTurnID = turnID
        phase = .capturing
        pumpFailure = nil

        pumpTask = Task { [weak self] in
            do {
                for try await chunk in stream {
                    guard chunk.channels == 1,
                          chunk.sampleRate == 16_000,
                          chunk.frameCount > 0,
                          chunk.data.count == chunk.frameCount * MemoryLayout<Int16>.size
                    else {
                        self?.pumpFailure = .captureFailure
                        await coordinator.cancel()
                        return
                    }
                    try await coordinator.appendPCM16(chunk.data)
                }
            } catch is CancellationError {
                return
            } catch let failure as SpeechRailRealtimeASRFailure {
                self?.pumpFailure = failure
                await coordinator.cancel()
            } catch {
                self?.pumpFailure = .captureFailure
                await coordinator.cancel()
            }
        }

        return turnID
    }

    public func finish() async -> InputTurnTerminalResult {
        guard phase == .capturing, let coordinator else {
            return .failed(.invalidState)
        }
        phase = .finalizing

        // Stop first, then drain the one serial append consumer. Nothing can be
        // appended after this barrier.
        microphone.stop()
        let pump = pumpTask
        pumpTask = nil
        await pump?.value

        if let pumpFailure {
            let result: InputTurnTerminalResult = .failed(pumpFailure)
            phase = .terminal
            return result
        }

        let result = await coordinator.finish()
        phase = .terminal
        return result
    }

    public func cancel() async {
        guard phase == .capturing || phase == .finalizing else { return }
        microphone.stop()
        let pump = pumpTask
        pumpTask = nil
        await pump?.value
        if let coordinator {
            await coordinator.cancel()
        } else {
            await connection.close()
        }
        phase = .terminal
    }

    public func updates() async throws -> AsyncStream<SpeechRailRealtimeASRTurnUpdate> {
        guard let coordinator else {
            throw SpeechRailRealtimeASRFailure.invalidState
        }
        return await coordinator.updates()
    }
}
