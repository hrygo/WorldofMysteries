import Foundation

public nonisolated enum SpeechRailTTSPlaybackFailure: Error, Sendable, Equatable, LocalizedError {
    case invalidState
    case provider(SpeechRailRealtimeTTSFailure)
    case playback(NativePlaybackFailure)
    case unexpected

    public var errorDescription: String? {
        "The SpeechRail TTS stream could not be safely presented by the local playback pipeline."
    }
}

public nonisolated struct SpeechRailTTSPlaybackResult: Sendable, Equatable {
    public let provider: SpeechRailTTSProviderResult
    public let playback: NativePlaybackSnapshot

    public init(provider: SpeechRailTTSProviderResult, playback: NativePlaybackSnapshot) {
        self.provider = provider
        self.playback = playback
    }
}

public nonisolated enum SpeechRailTTSPlaybackTerminal: Sendable, Equatable {
    case completed(SpeechRailTTSPlaybackResult)
    case cancelled
    case failed(SpeechRailTTSPlaybackFailure)
}

/// Caller-owned bridge from SpeechRail's current-only TTS wire to native PCM playback.
///
/// This coordinator deliberately keeps provider completion and device completion separate:
/// a successful Render Receipt proves the streamed provider PCM, while the returned playback
/// snapshot still exposes `devicePlaybackProvenComplete == false` until a later device evidence
/// source exists. One presentation remains active after provider completion and must be explicitly
/// stopped/retired before another request starts.
public actor SpeechRailTTSPlaybackCoordinator {
    private struct ActivePresentation: Sendable {
        let requestID: String
        let generation: Int64
        var stopRequested = false
        var providerTerminal: PlaybackProviderTerminal = .none
    }

    private let connection: SpeechRailRealtimeTTSConnection
    private let playback: NativePlaybackActor
    private var connected = false
    private var nextGeneration: Int64 = 0
    private var active: ActivePresentation?

    public init(
        connection: SpeechRailRealtimeTTSConnection,
        playback: NativePlaybackActor
    ) {
        self.connection = connection
        self.playback = playback
    }

    public func render(_ request: SpeechRailTTSRequest) async -> SpeechRailTTSPlaybackTerminal {
        guard active == nil else { return .failed(.invalidState) }
        let generation = nextGeneration
        nextGeneration += 1
        active = ActivePresentation(requestID: request.requestID, generation: generation)

        var accumulator = SpeechRailTTSRenderAccumulator(requestID: request.requestID)
        var responseID: String?
        var itemID: String?
        var mediaSequence: Int64 = 0
        var offsetFrames: Int64 = 0
        var playbackStarted = false

        do {
            if !connected {
                _ = try await connection.connect()
                connected = true
            }
            try await connection.begin(request)

            while true {
                let envelope = try await connection.receiveEnvelope()
                accumulator.observe(envelope)

                switch envelope.event {
                case .responseCreated(let createdResponseID):
                    guard responseID == nil || responseID == createdResponseID else {
                        throw SpeechRailRealtimeTTSFailure.responseMismatch
                    }
                    responseID = createdResponseID
                    if !isStopRequested(generation: generation) {
                        try await playback.begin(
                            streamID: createdResponseID,
                            generation: generation,
                            format: MediaFormat(sampleRate: 24_000)
                        )
                        playbackStarted = true
                        if isStopRequested(generation: generation) {
                            await playback.stop(providerCancel: {})
                            playbackStarted = false
                        }
                    }

                case .audioDelta(let eventResponseID, let eventItemID, let pcm16):
                    guard responseID == eventResponseID else {
                        throw SpeechRailRealtimeTTSFailure.responseMismatch
                    }
                    if let itemID, itemID != eventItemID {
                        throw SpeechRailRealtimeTTSFailure.responseMismatch
                    }
                    itemID = eventItemID
                    guard !isStopRequested(generation: generation) else { break }
                    guard playbackStarted else {
                        throw SpeechRailRealtimeTTSFailure.audioStreamIncomplete
                    }
                    let frameCount = pcm16.count / MemoryLayout<Int16>.size
                    mediaSequence += 1
                    let header = MediaChunkHeader(
                        streamId: eventResponseID,
                        generation: generation,
                        sequence: mediaSequence,
                        offsetFrames: offsetFrames,
                        frameCount: frameCount,
                        payloadBytes: pcm16.count
                    )
                    if try await playback.accept(header, payload: pcm16) {
                        offsetFrames += Int64(frameCount)
                    }

                case .audioDone(let eventResponseID, let eventItemID):
                    guard responseID == eventResponseID,
                          itemID == nil || itemID == eventItemID
                    else {
                        throw SpeechRailRealtimeTTSFailure.responseMismatch
                    }
                    itemID = eventItemID
                    if !isStopRequested(generation: generation), playbackStarted {
                        try await playback.finishMediaStream(
                            generation: generation,
                            totalFrames: offsetFrames
                        )
                    }

                case .responseDone:
                    guard let terminal = accumulator.terminal else {
                        throw SpeechRailRealtimeTTSFailure.audioStreamIncomplete
                    }
                    if isStopRequested(generation: generation) {
                        active = nil
                        return .cancelled
                    }
                    switch terminal {
                    case .completed(let provider):
                        guard playbackStarted,
                              provider.responseID == responseID,
                              provider.itemID == itemID
                        else {
                            throw SpeechRailRealtimeTTSFailure.responseMismatch
                        }
                        try await playback.observeProviderTerminal(
                            .completed,
                            generation: generation
                        )
                        guard let snapshot = await playback.snapshot() else {
                            throw NativePlaybackFailure.invalidState
                        }
                        active?.providerTerminal = .completed
                        return .completed(
                            SpeechRailTTSPlaybackResult(provider: provider, playback: snapshot)
                        )

                    case .cancelled:
                        if playbackStarted {
                            await playback.stop(providerCancel: {})
                        }
                        active = nil
                        return .cancelled

                    case .failed(let failure):
                        if playbackStarted {
                            try? await playback.observeProviderTerminal(.failed, generation: generation)
                        }
                        await playback.stop(providerCancel: {})
                        active = nil
                        return .failed(.provider(failure))
                    }

                case .error:
                    if case .failed(let failure)? = accumulator.terminal {
                        await playback.stop(providerCancel: {})
                        active = nil
                        return .failed(.provider(failure))
                    }

                default:
                    break
                }

                if case .failed(let failure)? = accumulator.terminal {
                    await playback.stop(providerCancel: {})
                    active = nil
                    return .failed(.provider(failure))
                }
            }
        } catch let failure as SpeechRailRealtimeTTSFailure {
            await failClosed()
            return .failed(.provider(failure))
        } catch let failure as NativePlaybackFailure {
            await failClosed()
            return .failed(.playback(failure))
        } catch {
            await failClosed()
            return .failed(.unexpected)
        }
    }

    /// Stop is local-first: invalidate/stop the native playback generation, then
    /// request provider cancellation. The render loop remains responsible for
    /// consuming the provider's terminal response when it arrives.
    public func stop() async {
        guard var current = active else { return }
        current.stopRequested = true
        current.providerTerminal = .cancelled
        active = current
        await playback.stop { [connection] in
            _ = try? await connection.cancelCurrent()
        }
    }

    public func currentPlaybackSnapshot() async -> NativePlaybackSnapshot? {
        await playback.snapshot()
    }

    /// Retire a provider-complete presentation only after the caller's own
    /// rendered-position estimate reaches the scheduled frame count. This is
    /// still an estimate, not proof of audible completion.
    @discardableResult
    public func retireCompletedPresentation(renderedEstimateFrames: Int64) async throws -> NativePlaybackSnapshot {
        guard let current = active, current.providerTerminal == .completed else {
            throw SpeechRailTTSPlaybackFailure.invalidState
        }
        try await playback.reportRenderedEstimate(
            throughFrames: renderedEstimateFrames,
            generation: current.generation
        )
        guard let snapshot = await playback.snapshot(),
              snapshot.scheduledFrames == renderedEstimateFrames,
              snapshot.mediaStreamEnded,
              snapshot.providerCompleted
        else {
            throw SpeechRailTTSPlaybackFailure.invalidState
        }
        await playback.stop(providerCancel: {})
        active = nil
        return snapshot
    }

    public func close() async {
        if active != nil {
            await playback.stop { [connection] in
                _ = try? await connection.cancelCurrent()
            }
        }
        active = nil
        await connection.close()
        connected = false
    }

    private func isStopRequested(generation: Int64) -> Bool {
        guard let active, active.generation == generation else { return true }
        return active.stopRequested
    }

    private func failClosed() async {
        await playback.stop(providerCancel: {})
        active = nil
        await connection.close()
        connected = false
    }
}
