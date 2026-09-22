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
/// existing FIFO contract: commit, then clear, then wait until the assembler
/// proves every committed item terminal and observes cleared.
///
/// Failure/timeout/cancel closes this connection instead of attempting to reuse
/// an uncertain server buffer. The next turn must reconnect and therefore gets
/// a new connection epoch.
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
            startingSequence: info.lastServerSequence
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
            terminate(result)
            return result
        }

        do {
            try current.beginFinalization()
            assembler = current
            phaseStorage = .finalizing

            // FIFO send order is part of the current SpeechRail manual-ASR
            // contract. clear is deliberately sent immediately after commit;
            // the service processes it only after the commit handler drains.
            _ = try await connection.commit()
            _ = try await connection.clear()
        } catch {
            let result: InputTurnTerminalResult = .failed(.transportFailure)
            terminate(result)
            await connection.close()
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
        // Do not leave a clear acknowledgement or a late rollover item queued
        // for another logical turn. Closing forces a new connection epoch.
        terminate(.cancelled)
        await connection.close()
    }

    private func receiveLoop(epoch: UUID) async {
        while terminalStorage == nil {
            do {
                let envelope = try await connection.receiveEnvelope()
                ingest(envelope, epoch: epoch)
            } catch is CancellationError {
                return
            } catch {
                guard terminalStorage == nil else { return }
                terminate(.failed(.transportFailure))
                await connection.close()
                return
            }
        }
    }

    private func ingest(_ envelope: SpeechRailASRServerEnvelope, epoch: UUID) {
        guard terminalStorage == nil, var current = assembler else { return }
        current.observe(envelope, connectionEpoch: epoch)
        assembler = current

        let draft = current.latestDraftText
        if draft != lastDraft {
            lastDraft = draft
            updateSink.yield(.draft(draft))
        }

        if let result = current.terminalResult {
            terminate(result)
        }
    }

    private func finalizationTimedOut() async {
        guard terminalStorage == nil, phaseStorage == .finalizing else { return }
        terminate(.failed(.finalizationTimedOut))
        await connection.close()
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
