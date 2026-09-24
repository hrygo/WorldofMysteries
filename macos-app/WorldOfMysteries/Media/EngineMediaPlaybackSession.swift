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

public nonisolated struct VoiceDeliverySessionContext: Sendable, Equatable {
    public let trackId: String
    public let consumerId: String
    public let unitId: String

    public init(trackId: String, consumerId: String, unitId: String) {
        self.trackId = trackId
        self.consumerId = consumerId
        self.unitId = unitId
    }
}

public nonisolated protocol VoiceDeliveryCursorReporting: Sendable {
    func loadVoiceDeliveryCursor(
        trackId: String,
        consumerId: String,
        traceId: String
    ) async throws -> VoiceDeliveryCursorDTO?

    func updateVoiceDeliveryCursor(
        _ request: VoiceDeliveryCursorUpdateDTO,
        traceId: String
    ) async throws -> VoiceDeliveryCursorDTO
}

extension EngineIPCClient: VoiceDeliveryCursorReporting {}

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
    private let deliveryReporter: (any VoiceDeliveryCursorReporting)?
    private let deliveryContext: VoiceDeliverySessionContext?
    private var deliveryCursor: VoiceDeliveryCursorDTO?
    private var phase: Phase = .idle
    private var stopRequested = false

    public init(
        grant: MediaOpenGrant,
        transport: any MediaFrameTransport = UnixMediaFrameTransport(),
        playback: NativePlaybackActor,
        playbackMode: VoicePlaybackMode = .normal,
        deliveryReporter: (any VoiceDeliveryCursorReporting)? = nil,
        deliveryContext: VoiceDeliverySessionContext? = nil,
        connectTimeout: TimeInterval = 5
    ) {
        self.grant = grant
        self.transport = transport
        self.playback = playback
        self.playbackMode = playbackMode
        self.deliveryReporter = deliveryReporter
        self.deliveryContext = deliveryContext
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
            try await beginDeliveryCursor()

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

                    try await recordScheduledOffset(
                        Int64(header.offsetFrames + Int64(header.frameCount))
                    )

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
                    await recordStopped(reason: header.reason)
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
                    await recordDeliveryStop(.mediaError)
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
        await recordStopped(reason: reason)
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
        try await recordRenderedEstimate(renderedEstimateFrames)
        await playback.stop(providerCancel: {})
        phase = .stopped
        return snapshot
    }

    private func beginDeliveryCursor() async throws {
        guard let deliveryReporter, let deliveryContext else { return }
        let traceId = UUID().uuidString
        let existing = try await deliveryReporter.loadVoiceDeliveryCursor(
            trackId: deliveryContext.trackId,
            consumerId: deliveryContext.consumerId,
            traceId: traceId
        )

        if let existing {
            guard existing.generation < Int(grant.generation) else {
                throw EngineMediaPlaybackFailure.invalidState
            }
            deliveryCursor = try await deliveryReporter.updateVoiceDeliveryCursor(
                VoiceDeliveryCursorUpdateDTO(
                    trackId: deliveryContext.trackId,
                    consumerId: deliveryContext.consumerId,
                    unitId: deliveryContext.unitId,
                    generation: Int(grant.generation),
                    sourceOffsetFrames: 0,
                    totalSourceFrames: nil,
                    evidence: .queued,
                    stopReason: nil,
                    expectedCursorRevision: existing.cursorRevision
                ),
                traceId: traceId
            )
        } else {
            deliveryCursor = try await deliveryReporter.updateVoiceDeliveryCursor(
                VoiceDeliveryCursorUpdateDTO(
                    trackId: deliveryContext.trackId,
                    consumerId: deliveryContext.consumerId,
                    unitId: deliveryContext.unitId,
                    generation: Int(grant.generation),
                    sourceOffsetFrames: 0,
                    totalSourceFrames: nil,
                    evidence: .queued,
                    stopReason: nil,
                    expectedCursorRevision: 0
                ),
                traceId: traceId
            )
        }
    }

    private func recordScheduledOffset(_ sourceOffsetFrames: Int64) async throws {
        guard let deliveryReporter, let deliveryContext, let current = deliveryCursor else { return }
        guard sourceOffsetFrames <= Int64(Int.max) else {
            throw EngineMediaPlaybackFailure.invalidState
        }
        deliveryCursor = try await deliveryReporter.updateVoiceDeliveryCursor(
            VoiceDeliveryCursorUpdateDTO(
                trackId: deliveryContext.trackId,
                consumerId: deliveryContext.consumerId,
                unitId: deliveryContext.unitId,
                generation: Int(grant.generation),
                sourceOffsetFrames: Int(sourceOffsetFrames),
                totalSourceFrames: current.totalSourceFrames,
                evidence: .scheduled,
                stopReason: nil,
                expectedCursorRevision: current.cursorRevision
            ),
            traceId: UUID().uuidString
        )
    }

    private func recordRenderedEstimate(_ frames: Int64) async throws {
        guard let deliveryReporter, let deliveryContext, let current = deliveryCursor else { return }
        guard frames >= 0, frames <= Int64(Int.max) else {
            throw EngineMediaPlaybackFailure.invalidState
        }
        deliveryCursor = try await deliveryReporter.updateVoiceDeliveryCursor(
            VoiceDeliveryCursorUpdateDTO(
                trackId: deliveryContext.trackId,
                consumerId: deliveryContext.consumerId,
                unitId: deliveryContext.unitId,
                generation: Int(grant.generation),
                sourceOffsetFrames: Int(frames),
                totalSourceFrames: Int(frames),
                evidence: .renderedEstimate,
                stopReason: .completed,
                expectedCursorRevision: current.cursorRevision
            ),
            traceId: UUID().uuidString
        )
    }

    private func recordStopped(reason: MediaCancelReason) async {
        let stopReason: VoiceDeliveryStopReason
        switch reason {
        case .userStop: stopReason = .userStop
        case .superseded: stopReason = .superseded
        case .sessionClosed, .shutdown: stopReason = .suspend
        case .timeout: stopReason = .mediaError
        }
        await recordDeliveryStop(stopReason)
    }

    private func recordDeliveryStop(_ stopReason: VoiceDeliveryStopReason) async {
        guard let deliveryReporter, let deliveryContext, let current = deliveryCursor else { return }
        deliveryCursor = try? await deliveryReporter.updateVoiceDeliveryCursor(
            VoiceDeliveryCursorUpdateDTO(
                trackId: deliveryContext.trackId,
                consumerId: deliveryContext.consumerId,
                unitId: deliveryContext.unitId,
                generation: Int(grant.generation),
                sourceOffsetFrames: current.sourceOffsetFrames,
                totalSourceFrames: current.totalSourceFrames,
                evidence: current.evidence,
                stopReason: stopReason,
                expectedCursorRevision: current.cursorRevision
            ),
            traceId: UUID().uuidString
        )
    }

    private func failClosed() async {
        await recordDeliveryStop(.mediaError)
        await playback.stop(providerCancel: {})
        await transport.close()
        phase = .stopped
    }
}
