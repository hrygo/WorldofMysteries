import Foundation

public nonisolated enum EngineMediaPlaybackFailure: Error, Sendable, Equatable, LocalizedError {
    case invalidGrant
    case invalidState
    case transport
    case protocolViolation(MediaProtocolFailure)
    case playback(NativePlaybackFailure)
    case remoteError(code: String)

    public var errorDescription: String? {
        "The Engine media playback stream could not be presented safely."
    }
}

public nonisolated enum EngineMediaPlaybackTerminal: Sendable, Equatable {
    case ended(NativePlaybackSnapshot)
    case cancelled
    case failed(EngineMediaPlaybackFailure)
}

/// One Engine -> App media stream.
///
/// SpeechRail is intentionally absent from this type: the Engine owns provider TTS.
/// This layer consumes the W-V01 protected media channel, validates stream integrity,
/// and feeds only accepted current-generation PCM into NativePlaybackActor.
public actor EngineMediaPlaybackSession {
    private enum Phase: Sendable, Equatable {
        case idle
        case running
        case ended
        case stopped
    }

    private let grant: MediaOpenGrant
    private let transport: any MediaFrameTransport
    private let playback: NativePlaybackActor
    private let playbackMode: VoicePlaybackMode
    private let connectTimeout: TimeInterval
    private var phase: Phase = .idle
    private var stopRequested = false

    public init(
        grant: MediaOpenGrant,
        transport: any MediaFrameTransport = UnixMediaFrameTransport(),
        playback: NativePlaybackActor,
        playbackMode: VoicePlaybackMode = .normal,
        connectTimeout: TimeInterval = 5
    ) {
        self.grant = grant
        self.transport = transport
        self.playback = playback
        self.playbackMode = playbackMode
        self.connectTimeout = connectTimeout
    }

    public func run() async -> EngineMediaPlaybackTerminal {
        guard phase == .idle else { return .failed(.invalidState) }
        guard grant.direction == .engineToApp,
              grant.format.codec == "pcm_s16le",
              grant.format.sampleRate == 24_000,
              grant.format.channels == 1,
              connectTimeout.isFinite,
              connectTimeout > 0
        else {
            return .failed(.invalidGrant)
        }

        let opened = grant.makeOpenHeader()
        var receiveState = MediaReceiveState(opened: opened)

        do {
            try await transport.connect(path: grant.socketPath, timeout: connectTimeout)
            try await playback.begin(
                streamID: grant.streamId,
                generation: grant.generation,
                format: grant.format,
                mode: playbackMode
            )
            phase = .running

            // OPEN burns the one-time ticket only after local playback is ready.
            try await transport.send(MediaFrame(header: .open(opened)))

            for try await frame in transport.frameStream() {
                if stopRequested {
                    await transport.close()
                    phase = .stopped
                    return .cancelled
                }

                switch frame.header {
                case .chunk(let header):
                    do {
                        try receiveState.accept(header, payload: frame.payload)
                    } catch let failure as MediaProtocolFailure {
                        throw EngineMediaPlaybackFailure.protocolViolation(failure)
                    }
                    let accepted: Bool
                    do {
                        accepted = try await playback.accept(header, payload: frame.payload)
                    } catch let failure as NativePlaybackFailure {
                        throw EngineMediaPlaybackFailure.playback(failure)
                    }
                    guard accepted else {
                        if stopRequested {
                            await transport.close()
                            phase = .stopped
                            return .cancelled
                        }
                        throw EngineMediaPlaybackFailure.invalidState
                    }

                    // Credit is replenished only after the backend has consumed/
                    // released the chunk passed to NativePlaybackActor.
                    let credit = MediaCreditHeader(
                        streamId: grant.streamId,
                        generation: grant.generation,
                        creditBytes: frame.payload.count
                    )
                    try await transport.send(MediaFrame(header: .credit(credit)))

                case .end(let header):
                    do {
                        try receiveState.finish(header)
                    } catch let failure as MediaProtocolFailure {
                        throw EngineMediaPlaybackFailure.protocolViolation(failure)
                    }
                    do {
                        try await playback.finishMediaStream(
                            generation: grant.generation,
                            totalFrames: header.totalFrames
                        )
                    } catch let failure as NativePlaybackFailure {
                        throw EngineMediaPlaybackFailure.playback(failure)
                    }
                    guard let snapshot = await playback.snapshot() else {
                        throw EngineMediaPlaybackFailure.invalidState
                    }
                    phase = .ended
                    await transport.close()
                    // Media END proves Engine->App transfer completeness only.
                    // It deliberately does not mark provider/audible completion.
                    return .ended(snapshot)

                case .cancel(let header):
                    guard header.streamId == grant.streamId,
                          header.generation == grant.generation
                    else {
                        throw EngineMediaPlaybackFailure.protocolViolation(.streamIdentityMismatch)
                    }
                    await playback.stop(providerCancel: {})
                    phase = .stopped
                    await transport.close()
                    return .cancelled

                case .error(let header):
                    guard header.streamId == grant.streamId,
                          header.generation == grant.generation
                    else {
                        throw EngineMediaPlaybackFailure.protocolViolation(.streamIdentityMismatch)
                    }
                    await playback.stop(providerCancel: {})
                    phase = .stopped
                    await transport.close()
                    return .failed(.remoteError(code: header.code))

                case .open, .credit:
                    throw EngineMediaPlaybackFailure.protocolViolation(.invalidHeader)
                }
            }

            if stopRequested {
                phase = .stopped
                return .cancelled
            }
            throw EngineMediaPlaybackFailure.transport
        } catch let failure as EngineMediaPlaybackFailure {
            await failClosed()
            return .failed(failure)
        } catch is CancellationError {
            await stop(reason: .sessionClosed)
            return .cancelled
        } catch {
            if stopRequested {
                phase = .stopped
                return .cancelled
            }
            await failClosed()
            return .failed(.transport)
        }
    }

    /// Local generation invalidation/device stop precedes the outbound CANCEL.
    /// Closing the media socket then guarantees late Engine chunks cannot revive speech.
    public func stop(reason: MediaCancelReason = .userStop) async {
        guard phase == .running else {
            if phase == .ended {
                await playback.stop(providerCancel: {})
                phase = .stopped
            }
            return
        }
        stopRequested = true
        let cancel = MediaCancelHeader(
            streamId: grant.streamId,
            generation: grant.generation,
            reason: reason
        )
        await playback.stop { [transport] in
            _ = try? await transport.send(MediaFrame(header: .cancel(cancel)))
        }
        await transport.close()
        phase = .stopped
    }

    /// END means the full media stream arrived; callers may later retire the local
    /// presentation using a rendered-position estimate. This remains weaker than
    /// measured audible completion.
    @discardableResult
    public func retireEndedPresentation(
        renderedEstimateFrames: Int64
    ) async throws -> NativePlaybackSnapshot {
        guard phase == .ended else { throw EngineMediaPlaybackFailure.invalidState }
        do {
            try await playback.reportRenderedEstimate(
                throughFrames: renderedEstimateFrames,
                generation: grant.generation
            )
        } catch let failure as NativePlaybackFailure {
            throw EngineMediaPlaybackFailure.playback(failure)
        }
        guard let snapshot = await playback.snapshot(),
              snapshot.mediaStreamEnded,
              snapshot.scheduledFrames == renderedEstimateFrames
        else {
            throw EngineMediaPlaybackFailure.invalidState
        }
        await playback.stop(providerCancel: {})
        phase = .stopped
        return snapshot
    }

    private func failClosed() async {
        await playback.stop(providerCancel: {})
        await transport.close()
        phase = .stopped
    }
}
