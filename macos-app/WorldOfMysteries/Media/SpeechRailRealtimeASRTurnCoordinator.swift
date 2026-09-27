import Foundation

public nonisolated enum SpeechRailRealtimeASRTurnPhase: Sendable, Equatable {
    case idle
    case capturing
    case finalizing
    case terminal
}

public nonisolated enum SpeechRailRealtimeASRTurnUpdate: Sendable, Equatable {
    case draft(String)
    case terminal(InputTurnTerminalResult)
}

/// Owns exactly one logical input turn on one already-connected SpeechRail
/// Realtime ASR connection.
///
/// The coordinator continuously drains service events while capture is active,
/// so server rollover items cannot accumulate unnoticed. Finalization is the
/// FIFO barrier contract: commit, then re-send the identical effective session
/// update. Because the service handles client events on one queue, the
/// resulting `session.updated` can only be emitted after the commit handler
/// has drained its ASR reader — which is exactly the proof this turn needs.
///
/// Every terminal — success, empty, failure, timeout or cancel — closes the
/// connection instead of attempting to reuse an uncertain server buffer. The
/// next turn must reconnect and therefore gets a new connection epoch.
public actor SpeechRailRealtimeASRTurnCoordinator {
    private let connection: SpeechRailRealtimeASRConnection
    private let finalizationTimeout: Duration

    private var phaseStorage: SpeechRailRealtimeASRTurnPhase = .idle
    private var assembler: InputTurnAssembler?
    private var connectionEpoch: UUID?
    private var receiveTask: Task<Void, Never>?
    private var timeoutTask: Task<Void, Never>?
    private var finishWaiter: CheckedContinuation<InputTurnTerminalResult, Never>?
    private var terminalStorage: InputTurnTerminalResult?
    private var lastDraft = ""

    private let updateStreamStorage: AsyncStream<SpeechRailRealtimeASRTurnUpdate>
    private let updateSink: AsyncStream<SpeechRailRealtimeASRTurnUpdate>.Continuation

    public init(
        connection: SpeechRailRealtimeASRConnection,
        finalizationTimeout: Duration = .seconds(10)
    ) {
        self.connection = connection
        self.finalizationTimeout = finalizationTimeout
        let channel = AsyncStream<SpeechRailRealtimeASRTurnUpdate>.makeStream(
            bufferingPolicy: .bufferingNewest(32)
        )
        self.updateStreamStorage = channel.stream
        self.updateSink = channel.continuation
    }

    public var phase: SpeechRailRealtimeASRTurnPhase {
        phaseStorage
    }

    public func updates() -> AsyncStream<SpeechRailRealtimeASRTurnUpdate> {
        updateStreamStorage
    }

    @discardableResult
    public func start(inputTurnID: UUID = UUID()) async throws -> UUID {
        guard phaseStorage == .idle else {
            throw SpeechRailRealtimeASRFailure.invalidState
        }
        let info = try await connection.currentInfo()
        connectionEpoch = info.connectionEpoch
        assembler = InputTurnAssembler(
            inputTurnID: inputTurnID,
            connectionEpoch: info.connectionEpoch,
            startingSequence: info.lastServerSequence,
            expectedSession: info.session
        )
        phaseStorage = .capturing

        receiveTask = Task { [weak self] in
            await self?.receiveLoop(epoch: info.connectionEpoch)
        }
        return inputTurnID
    }

    public func appendPCM16(_ pcm16: Data) async throws {
        guard phaseStorage == .capturing else {
            throw SpeechRailRealtimeASRFailure.invalidState
        }
        _ = try await connection.appendPCM16(pcm16)
    }

    public func finish() async -> InputTurnTerminalResult {
        if let terminalStorage {
            return terminalStorage
        }
        guard phaseStorage == .capturing, var current = assembler else {
            let result: InputTurnTerminalResult = .failed(.invalidState)
            await terminateAndClose(result)
            return result
        }

        do {
            try current.beginFinalization()
            assembler = current
            phaseStorage = .finalizing

            // Both events must be identical apart from event_id. The second
            // one is the barrier; no client event id is echoed back, so the
            // assembler matches on the configuration instead.
            _ = try await connection.commit()
            _ = try await connection.resendSessionUpdate()
        } catch {
            let result: InputTurnTerminalResult = .failed(.transportFailure)
            await terminateAndClose(result)
            return result
        }

        if let terminalStorage {
            return terminalStorage
        }

        timeoutTask = Task { [weak self, finalizationTimeout] in
            do {
                try await Task.sleep(for: finalizationTimeout)
            } catch {
                return
            }
            await self?.finalizationTimedOut()
        }

        return await withTaskCancellationHandler {
            await withCheckedContinuation { continuation in
                if let terminalStorage {
                    continuation.resume(returning: terminalStorage)
                } else {
                    finishWaiter = continuation
                }
            }
        } onCancel: {
            Task { [weak self] in
                await self?.cancel()
            }
        }
    }

    public func cancel() async {
        guard terminalStorage == nil else { return }
        // Do not leave a barrier acknowledgement or a late rollover item
        // queued for another logical turn. Closing forces a new epoch.
        await terminateAndClose(.cancelled)
    }

    private func receiveLoop(epoch: UUID) async {
        while terminalStorage == nil {
            do {
                let envelope = try await connection.receiveEnvelope()
                await ingest(envelope, epoch: epoch)
            } catch is CancellationError {
                return
            } catch {
                guard terminalStorage == nil else { return }
                await terminateAndClose(.failed(.transportFailure))
                return
            }
        }
    }

    private func ingest(_ envelope: SpeechRailASRServerEnvelope, epoch: UUID) async {
        guard terminalStorage == nil, var current = assembler else { return }
        current.observe(envelope, connectionEpoch: epoch)
        assembler = current

        let draft = current.latestDraftText
        let display = draft.isEmpty ? (current.transientHypothesisText ?? "") : draft
        if display != lastDraft {
            lastDraft = display
            updateSink.yield(.draft(display))
        }

        if let result = current.terminalResult {
            await terminateAndClose(result)
        }
    }

    private func finalizationTimedOut() async {
        guard terminalStorage == nil, phaseStorage == .finalizing else { return }
        await terminateAndClose(.failed(.finalizationTimedOut))
    }

    /// Publish exactly one terminal and always close the connection with it.
    private func terminateAndClose(_ result: InputTurnTerminalResult) async {
        // Close before publishing: the close cancels the receive loop, so it
        // must not be the statement that cancels the task performing it.
        await connection.close()
        terminate(result)
    }

    private func terminate(_ result: InputTurnTerminalResult) {
        guard terminalStorage == nil else { return }
        terminalStorage = result
        phaseStorage = .terminal
        timeoutTask?.cancel()
        timeoutTask = nil
        updateSink.yield(.terminal(result))
        updateSink.finish()
        let waiter = finishWaiter
        finishWaiter = nil
        waiter?.resume(returning: result)
        receiveTask?.cancel()
        receiveTask = nil
    }
}
