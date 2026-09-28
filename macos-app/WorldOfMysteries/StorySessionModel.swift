import Foundation
import Observation

/// Typed story surface of the Local Engine. Losing a response never authorizes a
/// mutation retry: the model only re-reads durable state unless the user re-sends
/// the frozen request identity.
public protocol StoryEngineClient: StorySubmissionClient {
    func storyEntry(scenarioId: String) async throws -> StoryEntryViewDTO
    func storyOpen(openRequestId: String, expectedStoreRevision: Int) async throws -> StoryOpenViewDTO
    func storySession(sessionId: String) async throws -> StorySessionGetViewDTO
    func supportsStoryExpression() async -> Bool
    func storyExpressionGet(sessionId: String, turnId: String) async throws -> StoryExpressionGetResponseDTO
    func storyTurnWorkGet(
        sessionId: String,
        turnId: String
    ) async throws -> StoryTurnWorkGetResponseDTO
    func storyTurnWorkRetry(
        sessionId: String,
        turnId: String,
        kind: StoryTurnWorkKind,
        retryRequestId: String
    ) async throws -> StoryTurnWorkRetryResponseDTO
}

public extension StoryEngineClient {
    /// Older clients and test doubles default to the pre-expression capability set.
    func supportsStoryExpression() async -> Bool { false }

    func storyExpressionGet(
        sessionId: String,
        turnId: String
    ) async throws -> StoryExpressionGetResponseDTO {
        _ = sessionId
        _ = turnId
        throw EngineConnectionError.methodUnavailable
    }

    func storyTurnWorkGet(
        sessionId: String,
        turnId: String
    ) async throws -> StoryTurnWorkGetResponseDTO {
        _ = sessionId
        _ = turnId
        throw EngineConnectionError.methodUnavailable
    }

    func storyTurnWorkRetry(
        sessionId: String,
        turnId: String,
        kind: StoryTurnWorkKind,
        retryRequestId: String
    ) async throws -> StoryTurnWorkRetryResponseDTO {
        _ = sessionId
        _ = turnId
        _ = kind
        _ = retryRequestId
        throw EngineConnectionError.methodUnavailable
    }
}

/// Business failure reported by the Engine. The code is a stable public interface.
public nonisolated struct StoryControlServiceError: Error, Equatable, Sendable {
    public let code: String
    public let retryable: Bool

    public init(code: String, retryable: Bool) {
        self.code = code
        self.retryable = retryable
    }
}

@Observable
@MainActor
public final class StorySessionModel {
    public enum State: Equatable, Sendable {
        case unavailable
        case loading
        case notStarted
        case opening
        case ready
        case submitting
        case recovering
        case pending
        case completed
        case failed(code: String)

        public var isBusy: Bool {
            switch self {
            case .loading, .opening, .submitting, .recovering: return true
            default: return false
            }
        }
    }

    public private(set) var state: State = .unavailable
    public private(set) var supportedAdvice: [String] = []
    public private(set) var view: StoryPublicViewDTO?
    public private(set) var expression: StoryExpressionGetResponseDTO?
    public private(set) var expressionReadFailed = false
    public private(set) var postCommitWork: StoryTurnWorkGetResponseDTO?
    public private(set) var postCommitWorkReadFailed = false
    public private(set) var postCommitWorkLoading = false
    public private(set) var audioUnavailableReason: String?
    public private(set) var pendingInputTurnId: String?
    public private(set) var generation: UInt64 = 0
    public private(set) var canRetrySameRequest = false
    public private(set) var lastServiceCode: String?
    public var draft: String = ""
    public let submissionCoordinator: StorySubmissionCoordinator

    @ObservationIgnored private let client: any StoryEngineClient
    @ObservationIgnored private let journal: any StoryJournalWriting
    @ObservationIgnored private let idFactory: @Sendable () -> String
    @ObservationIgnored private var expressionRequestGeneration: UInt64 = 0
    @ObservationIgnored private var postCommitWorkRequestGeneration: UInt64 = 0
    @ObservationIgnored private var currentCommittedTurnId: String?

    public init(
        client: any StoryEngineClient,
        journal: any StoryJournalWriting = StoryRequestJournal(),
        idFactory: @escaping @Sendable () -> String = { UUID().uuidString },
        submissionCoordinator: StorySubmissionCoordinator? = nil
    ) {
        self.client = client
        self.journal = journal
        self.idFactory = idFactory
        self.submissionCoordinator = submissionCoordinator ?? StorySubmissionCoordinator(
            client: client,
            journal: journal,
            idFactory: idFactory
        )
    }

    // MARK: - Public UI inputs

    /// The panel is only usable when the Engine advertises story capability and
    /// the transport is ready; a demo snapshot never unlocks it.
    public var canStartStory: Bool {
        switch state {
        case .notStarted: return true
        default: return false
        }
    }

    public var canSubmitStory: Bool {
        guard state == .ready, let view, view.canSubmit,
              submissionCoordinator.canAcceptNewInput else { return false }
        return !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// Explicit continuation is only offered when the frozen text is still local.
    public var canContinuePending: Bool {
        guard state == .pending else { return false }
        return submissionCoordinator.state == .received
            && submissionCoordinator.frozenSubmission != nil
    }

    public var canRecover: Bool {
        guard state != .unavailable, state != .pending else { return false }
        return submissionCoordinator.state == .outcomeUnknown
            || submissionCoordinator.state == .notFound
    }

    /// At least one fixed turn is durably committed. Further turns may follow.
    public var isFirstTurnSaved: Bool { view?.turn ?? 0 > 0 }

    /// The fixed run reached its final turn: the Engine advertises no further
    /// advice and refuses a sixth submit.
    public var isFixedRunComplete: Bool { state == .completed && view?.canSubmit == false }

    /// Next fixed turn number, derived from committed turns only.
    private var nextTurnNumber: Int { (view?.turn ?? 0) + 1 }

    public var statusText: String {
        switch state {
        case .unavailable: return "本地引擎未提供固定五轮故事能力"
        case .loading: return "正在读取固定五轮验证入口…"
        case .notStarted: return "工程验证 · 固定五轮"
        case .opening: return "正在创建可信开场…"
        case .ready: return "填入第 \(nextTurnNumber) 轮建议后提交"
        case .submitting: return "正在提交第 \(nextTurnNumber) 轮…"
        case .recovering: return "正在确认是否已保存…"
        case .pending: return "请求已记录，尚未提交"
        case .completed: return "第 \(view?.turn ?? 0) 轮已保存 · 固定五轮验证已完成"
        case .failed(let code): return Self.failureText(code)
        }
    }

    public var submissionStatusText: String? {
        submissionCoordinator.statusText
    }

    static func failureText(_ code: String) -> String {
        switch code {
        case "deterministic_input_unsupported": return "仅支持本轮指定的建议，可修改后重试"
        case "iteration_limit_reached": return "固定五轮验证已完成，后续回合不再开放"
        case "revision_conflict": return "状态已变化，请刷新只读结果"
        case "recovery_required": return "恢复受阻，保留现有数据"
        case "input_not_found": return "未查到提交记录，可显式重试同一请求"
        case "journal_unavailable": return "本地重试记录写入失败，未发送请求"
        case "authorization_denied": return "该会话不可访问"
        default: return "本地引擎暂时不可用"
        }
    }

    // MARK: - Lifecycle

    /// Connection generation changes discard stale completions and never resubmit.
    public func detachForConnectionChange() {
        generation &+= 1
        expressionRequestGeneration &+= 1
        postCommitWorkRequestGeneration &+= 1
        submissionCoordinator.detachForConnectionChange()
        state = .unavailable
        expression = nil
        expressionReadFailed = false
        postCommitWork = nil
        postCommitWorkReadFailed = false
        postCommitWorkLoading = false
        audioUnavailableReason = nil
        currentCommittedTurnId = nil
        pendingInputTurnId = nil
        canRetrySameRequest = false
        lastServiceCode = nil
    }

    /// Called once the transport is ready and the handshake advertises story methods.
    public func attach() async {
        guard state == .unavailable else { return }
        state = .loading
        await refreshEntry()
    }

    public func fillSupportedAdvice() {
        // A closed run advertises no acceptable input: never refill a stale hint.
        guard state == .ready, let advice = supportedAdvice.first else { return }
        draft = advice
    }

    public func refreshEntry() async {
        let attempt = generation
        canRetrySameRequest = false
        lastServiceCode = nil
        do {
            let entry = try await client.storyEntry(scenarioId: StoryControl.scenarioId)
            guard attempt == generation else { return }
            supportedAdvice = entry.supportedAdvice
            await apply(entry: entry, attempt: attempt)
        } catch {
            guard attempt == generation else { return }
            fail(error)
        }
    }

    private func apply(entry: StoryEntryViewDTO, attempt: UInt64) async {
        guard let session = entry.session else {
            pendingInputTurnId = entry.pendingInputTurnId
            updateCurrentSession(nil)
            let record: StoryRequestRecord?
            do {
                record = try journal.load()
            } catch {
                submissionCoordinator.block(code: "journal_unreadable")
                canRetrySameRequest = false
                state = entry.pendingInputTurnId == nil
                    ? .failed(code: "journal_unreadable")
                    : .pending
                return
            }
            if entry.pendingInputTurnId != nil {
                submissionCoordinator.block(code: "journal_missing")
                state = .pending
                return
            }
            if let record, record.frozenSubmission != nil {
                submissionCoordinator.block(code: "session_missing")
                canRetrySameRequest = false
                state = .failed(code: "session_missing")
                return
            }
            state = .notStarted
            await recoverPendingOpen(entry: entry, attempt: attempt)
            return
        }
        updateCurrentSession(session)
        pendingInputTurnId = nil
        let record: StoryRequestRecord?
        do {
            record = try journal.load()
        } catch {
            submissionCoordinator.block(code: "journal_unreadable")
            canRetrySameRequest = false
            state = .failed(code: "journal_unreadable")
            return
        }
        if let record, let frozen = record.frozenSubmission {
            guard frozen.sessionId == session.sessionId else {
                submissionCoordinator.block(code: "session_mismatch")
                canRetrySameRequest = false
                state = .failed(code: "session_mismatch")
                return
            }
            await submissionCoordinator.recover(expectedSessionId: session.sessionId)
            await applySubmissionOutcome(attempt: attempt)
            return
        }
        if entry.pendingInputTurnId != nil {
            submissionCoordinator.block(code: "journal_missing")
            state = .pending
            canRetrySameRequest = false
            return
        }
        state = Self.settledState(session)
        if let turnId = currentCommittedTurnId {
            let usesPostCommitWork = await refreshPostCommitWork(
                sessionId: session.sessionId,
                turnId: turnId,
                attempt: attempt
            )
            if !usesPostCommitWork {
                await refreshExpression(
                    sessionId: session.sessionId,
                    turnId: turnId,
                    attempt: attempt
                )
            }
        }
    }

    /// A committed turn is only "completed" when the Engine stops advertising
    /// `can_submit`; the fixed five-turn run stays `.ready` between turns.
    static func settledState(_ session: StoryPublicViewDTO) -> State {
        session.canSubmit ? .ready : .completed
    }

    /// A lost open ACK is recovered by re-issuing the frozen identity, never a new one.
    private func recoverPendingOpen(entry: StoryEntryViewDTO, attempt: UInt64) async {
        guard let record = try? journal.load(), record.isOpenPending,
              let openRequestId = record.openRequestId,
              let frozenRevision = record.openStoreRevision else { return }
        _ = entry
        state = .opening
        do {
            let opened = try await client.storyOpen(
                openRequestId: openRequestId, expectedStoreRevision: frozenRevision)
            guard attempt == generation else { return }
            updateCurrentSession(opened.session)
            try? journal.save(
                StoryRequestRecord(phase: .opened, openRequestId: openRequestId,
                                   openStoreRevision: frozenRevision,
                                   sessionId: opened.session.sessionId))
            state = .ready
        } catch {
            guard attempt == generation else { return }
            fail(error)
        }
    }

    public func startStory() async {
        guard canStartStory else { return }
        let attempt = generation
        let openRequestId = idFactory()
        let expectedStoreRevision = view?.observedStoreRevision ?? 0
        let record = StoryRequestRecord(
            phase: .opening, openRequestId: openRequestId,
            openStoreRevision: expectedStoreRevision)
        guard writeJournal(record) else { return }
        state = .opening
        do {
            let opened = try await client.storyOpen(
                openRequestId: openRequestId, expectedStoreRevision: expectedStoreRevision)
            guard attempt == generation else { return }
            updateCurrentSession(opened.session)
            guard writeJournal(
                StoryRequestRecord(phase: .opened, openRequestId: openRequestId,
                                   openStoreRevision: expectedStoreRevision,
                                   sessionId: opened.session.sessionId))
            else { return }
            state = .ready
        } catch {
            guard attempt == generation else { return }
            state = .recovering
            await refreshEntry()
        }
    }

    // MARK: - First turn

    public func submit() async {
        guard canSubmitStory, let view else { return }
        await submit(rawInput: draft, view: view)
    }

    /// Submit the exact advice the composer delivered.
    ///
    /// `AdviceDraftSubmission` hands the handler its trimmed advice and then
    /// empties the binding *synchronously*, before the handler's `Task` body
    /// runs. A handler that re-reads `draft` therefore always observes an empty
    /// string and silently fails the `canSubmitStory` guard, so the panel must
    /// carry its own frozen text instead of depending on the draft surviving.
    public func submit(advice: String) async {
        guard state == .ready, let view, view.canSubmit else { return }
        await submit(rawInput: advice, view: view)
    }

    private func submit(rawInput: String, view: StoryPublicViewDTO) async {
        let trimmed = rawInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let attempt = generation
        let frozen = await submissionCoordinator.submit(
            rawInput: trimmed,
            inputMode: .text,
            sessionId: view.sessionId,
            expectedStoryRevision: view.storyRevision,
            expectedStoreRevision: view.observedStoreRevision
        )
        if frozen != nil {
            canRetrySameRequest = false
        }
        await applySubmissionOutcome(attempt: attempt)
    }

    public func retryFrozenSubmission() async {
        guard canRetrySameRequest,
              submissionCoordinator.state == .notFound else { return }
        let attempt = generation
        await submissionCoordinator.continuePendingRequest()
        await applySubmissionOutcome(attempt: attempt)
    }

    /// Read-only refresh of the next turn's advice after a durable commit.
    ///
    /// The Engine only advertises the expected input for the current turn, so
    /// the client re-reads the entry instead of guessing. A transport failure
    /// here leaves the committed turn visible and never rewrites facts; the
    /// next explicit refresh re-syncs the advice.
    private func refreshAdviceAfterCommit(attempt: UInt64) async {
        do {
            let entry = try await client.storyEntry(scenarioId: StoryControl.scenarioId)
            guard attempt == generation else { return }
            supportedAdvice = entry.supportedAdvice
            pendingInputTurnId = entry.pendingInputTurnId
            guard let session = entry.session else { return }
            updateCurrentSession(session)
            if entry.pendingInputTurnId != nil {
                state = .pending
            } else {
                state = Self.settledState(session)
            }
        } catch {
            // Committed facts stay authoritative; only the advice hint is stale.
        }
    }

    /// Reads the independent post-COMMIT projection after commit or restore.
    /// This is a pure read: it neither retries work nor invokes a provider.
    /// Returns true once `turnWorkGet` is advertised, including read failures,
    /// so a v2 session never falls through to a different projection.
    private func refreshPostCommitWork(
        sessionId: String,
        turnId: String,
        attempt: UInt64
    ) async -> Bool {
        guard attempt == generation,
              view?.sessionId == sessionId,
              currentCommittedTurnId == turnId else {
            return false
        }
        postCommitWorkRequestGeneration &+= 1
        let queryAttempt = postCommitWorkRequestGeneration
        postCommitWork = nil
        postCommitWorkReadFailed = false
        postCommitWorkLoading = true
        defer {
            if queryAttempt == postCommitWorkRequestGeneration {
                postCommitWorkLoading = false
            }
        }

        guard await client.supportsStoryPostCommitMethod(.turnWorkGet),
              attempt == generation,
              queryAttempt == postCommitWorkRequestGeneration,
              view?.sessionId == sessionId,
              currentCommittedTurnId == turnId else {
            return false
        }

        do {
            let response = try await client.storyTurnWorkGet(
                sessionId: sessionId,
                turnId: turnId
            )
            guard attempt == generation,
                  queryAttempt == postCommitWorkRequestGeneration,
                  view?.sessionId == sessionId,
                  currentCommittedTurnId == turnId else {
                return true
            }
            guard response.sessionId == sessionId, response.turnId == turnId else {
                postCommitWorkReadFailed = true
                return true
            }
            postCommitWork = response
        } catch {
            guard attempt == generation,
                  queryAttempt == postCommitWorkRequestGeneration,
                  view?.sessionId == sessionId,
                  currentCommittedTurnId == turnId else {
                return true
            }
            postCommitWorkReadFailed = true
        }
        return true
    }

    /// Reads the legacy disclosed-text projection without resubmitting a turn.
    private func refreshExpression(
        sessionId: String,
        turnId: String,
        attempt: UInt64
    ) async {
        guard attempt == generation,
              view?.sessionId == sessionId,
              currentCommittedTurnId == turnId else {
            return
        }
        expressionRequestGeneration &+= 1
        let queryAttempt = expressionRequestGeneration
        expression = nil
        expressionReadFailed = false

        guard await client.supportsStoryExpression(),
              attempt == generation,
              queryAttempt == expressionRequestGeneration,
              view?.sessionId == sessionId,
              currentCommittedTurnId == turnId else {
            return
        }

        do {
            let response = try await client.storyExpressionGet(
                sessionId: sessionId,
                turnId: turnId
            )
            guard attempt == generation,
                  queryAttempt == expressionRequestGeneration,
                  view?.sessionId == sessionId,
                  currentCommittedTurnId == turnId else {
                return
            }
            guard response.sessionId == sessionId, response.turnId == turnId else {
                expressionReadFailed = true
                return
            }
            expression = response
        } catch {
            guard attempt == generation,
                  queryAttempt == expressionRequestGeneration,
                  view?.sessionId == sessionId,
                  currentCommittedTurnId == turnId else {
                return
            }
            expressionReadFailed = true
        }
    }

    // MARK: - Recovery

    /// Re-read the committed session after a turn this client did not submit
    /// through `submit()` — for example a voice turn, which commits its own
    /// durable input turn id.
    public func reloadSession() async {
        guard state != .unavailable, let sessionId = view?.sessionId else { return }
        let attempt = generation
        do {
            let entry = try await client.storyEntry(scenarioId: StoryControl.scenarioId)
            guard attempt == generation else { return }
            supportedAdvice = entry.supportedAdvice
            pendingInputTurnId = entry.pendingInputTurnId
            let fetched: StoryPublicViewDTO
            if let session = entry.session {
                fetched = session
            } else {
                fetched = try await client.storySession(sessionId: sessionId).session
            }
            guard attempt == generation else { return }
            updateCurrentSession(
                fetched,
                committedTurnId: submissionCoordinator.latestReceipt?.turnId
            )
            if let delivery = submissionCoordinator.latestResult?.delivery,
               delivery.state == .unavailable {
                audioUnavailableReason = delivery.reason
            }
            if submissionCoordinator.state == .committed {
                state = Self.settledState(fetched)
            } else if submissionCoordinator.state != .idle {
                await applySubmissionOutcome(attempt: attempt)
            } else if entry.pendingInputTurnId != nil {
                submissionCoordinator.block(code: "journal_missing")
                state = .pending
            }
            if let turnId = currentCommittedTurnId {
                let usesPostCommitWork = await refreshPostCommitWork(
                    sessionId: fetched.sessionId,
                    turnId: turnId,
                    attempt: attempt
                )
                if !usesPostCommitWork {
                    await refreshExpression(
                        sessionId: fetched.sessionId,
                        turnId: turnId,
                        attempt: attempt
                    )
                }
            }
        } catch {
            // A failed refresh must not invent a failure the player did not have:
            // the committed world is unchanged and the next read will catch up.
        }
    }

    public func recover() async {
        // A detached panel never queries the previous connection's Engine.
        guard state != .unavailable else { return }
        let attempt = generation
        await submissionCoordinator.recover(expectedSessionId: view?.sessionId)
        await applySubmissionOutcome(attempt: attempt)
    }

    /// Explicit user continuation of an already-received request.
    public func continuePendingRequest() async {
        guard canContinuePending else { return }
        let attempt = generation
        await submissionCoordinator.continuePendingRequest()
        await applySubmissionOutcome(attempt: attempt)
    }

    private func applySubmissionOutcome(attempt: UInt64) async {
        guard attempt == generation else { return }
        switch submissionCoordinator.state {
        case .idle:
            return
        case .selectingMethod:
            state = .submitting
            canRetrySameRequest = false
        case .submitting:
            state = .submitting
            canRetrySameRequest = false
        case .outcomeUnknown, .querying:
            state = .recovering
            canRetrySameRequest = false
        case .received:
            state = .pending
            canRetrySameRequest = false
            pendingInputTurnId = submissionCoordinator.frozenSubmission?.inputTurnId
        case .notFound:
            state = .failed(code: "input_not_found")
            canRetrySameRequest = true
            pendingInputTurnId = submissionCoordinator.frozenSubmission?.inputTurnId
        case .blocked(let code):
            lastServiceCode = code
            canRetrySameRequest = false
            state = .failed(code: code)
        case .committed:
            canRetrySameRequest = false
            lastServiceCode = nil
            guard let frozen = submissionCoordinator.frozenSubmission else {
                state = .failed(code: "journal_unreadable")
                return
            }
            var committedSession = submissionCoordinator.latestSession
            if committedSession == nil {
                do {
                    committedSession = try await client.storySession(
                        sessionId: frozen.sessionId
                    ).session
                } catch {
                    guard attempt == generation else { return }
                }
            }
            guard attempt == generation, let committedSession else {
                state = .recovering
                return
            }
            updateCurrentSession(
                committedSession,
                committedTurnId: submissionCoordinator.latestReceipt?.turnId
            )
            if let delivery = submissionCoordinator.latestResult?.delivery {
                audioUnavailableReason = delivery.state == .unavailable
                    ? delivery.reason
                    : nil
            }
            draft = ""
            pendingInputTurnId = nil
            state = Self.settledState(committedSession)
            if committedSession.canSubmit {
                await refreshAdviceAfterCommit(attempt: attempt)
            } else {
                supportedAdvice = []
            }
            if let turnId = currentCommittedTurnId {
                let usesPostCommitWork = await refreshPostCommitWork(
                    sessionId: committedSession.sessionId,
                    turnId: turnId,
                    attempt: attempt
                )
                if !usesPostCommitWork {
                    await refreshExpression(
                        sessionId: committedSession.sessionId,
                        turnId: turnId,
                        attempt: attempt
                    )
                }
            }
        }
    }

    // MARK: - Helpers

    private func updateCurrentSession(
        _ session: StoryPublicViewDTO?,
        committedTurnId: String? = nil
    ) {
        let oldSessionId = view?.sessionId
        let oldTurn = view?.turn
        let oldCommittedTurnId = currentCommittedTurnId
        view = session

        guard let session else {
            currentCommittedTurnId = nil
            expressionRequestGeneration &+= 1
            postCommitWorkRequestGeneration &+= 1
            expression = nil
            expressionReadFailed = false
            postCommitWork = nil
            postCommitWorkReadFailed = false
            postCommitWorkLoading = false
            audioUnavailableReason = nil
            return
        }

        let sameSessionAndTurn = oldSessionId == session.sessionId && oldTurn == session.turn
        let nextCommittedTurnId =
            committedTurnId
            ?? session.lastCommittedTurnId
            ?? (sameSessionAndTurn ? oldCommittedTurnId : nil)
        let changedSessionOrTurn =
            oldSessionId != session.sessionId
            || oldTurn != session.turn
            || oldCommittedTurnId != nextCommittedTurnId

        if changedSessionOrTurn {
            expressionRequestGeneration &+= 1
            postCommitWorkRequestGeneration &+= 1
            expression = nil
            expressionReadFailed = false
            postCommitWork = nil
            postCommitWorkReadFailed = false
            postCommitWorkLoading = false
            audioUnavailableReason = nil
        }
        currentCommittedTurnId = nextCommittedTurnId
    }

    private func writeJournal(_ record: StoryRequestRecord) -> Bool {
        do {
            try journal.save(record)
            return true
        } catch {
            state = .failed(code: "journal_unavailable")
            return false
        }
    }

    private func clearCommittedJournal() {
        try? journal.clear()
    }

    private func fail(_ error: any Error) {
        if let service = error as? StoryControlServiceError {
            lastServiceCode = service.code
            canRetrySameRequest = service.code == "service_unavailable"
            state = .failed(code: service.code)
        } else {
            lastServiceCode = nil
            canRetrySameRequest = false
            state = .failed(code: "service_unavailable")
        }
    }
}

private extension StoryRequestRecord {
    func withPhase(_ phase: Phase) -> StoryRequestRecord {
        var copy = self
        copy.phase = phase
        return copy
    }
}
