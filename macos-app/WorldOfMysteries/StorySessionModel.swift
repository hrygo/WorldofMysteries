import Foundation
import Observation

/// Typed story surface of the Local Engine. Losing a response never authorizes a
/// mutation retry: the model only re-reads durable state unless the user re-sends
/// the frozen request identity.
public protocol StoryEngineClient: Sendable {
    func storyEntry(scenarioId: String) async throws -> StoryEntryViewDTO
    func storyOpen(openRequestId: String, expectedStoreRevision: Int) async throws -> StoryOpenViewDTO
    func storySession(sessionId: String) async throws -> StorySessionGetViewDTO
    func storySubmit(_ request: StoryAdviceSubmitRequestDTO) async throws -> StoryAdviceSubmitViewDTO
    func storyAdvice(sessionId: String, inputTurnId: String) async throws -> StoryAdviceGetViewDTO
    func supportsStoryExpression() async -> Bool
    func storyExpressionGet(sessionId: String, turnId: String) async throws -> StoryExpressionGetResponseDTO
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
    public private(set) var audioUnavailableReason: String?
    public private(set) var pendingInputTurnId: String?
    public private(set) var generation: UInt64 = 0
    public private(set) var canRetrySameRequest = false
    public private(set) var lastServiceCode: String?
    public var draft: String = ""

    @ObservationIgnored private let client: any StoryEngineClient
    @ObservationIgnored private let journal: any StoryJournalWriting
    @ObservationIgnored private let idFactory: @Sendable () -> String
    @ObservationIgnored private var expressionRequestGeneration: UInt64 = 0
    @ObservationIgnored private var currentCommittedTurnId: String?

    public init(
        client: any StoryEngineClient,
        journal: any StoryJournalWriting = StoryRequestJournal(),
        idFactory: @escaping @Sendable () -> String = { UUID().uuidString }
    ) {
        self.client = client
        self.journal = journal
        self.idFactory = idFactory
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
        guard state == .ready, let view, view.canSubmit else { return false }
        return !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// Explicit continuation is only offered when the frozen text is still local.
    public var canContinuePending: Bool {
        guard state == .pending else { return false }
        return (try? journal.load())?.frozenSubmission != nil
    }

    public var canRecover: Bool {
        switch state {
        case .recovering, .pending: return false
        case .failed: return canRetrySameRequest
        default: return false
        }
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
        state = .unavailable
        expression = nil
        expressionReadFailed = false
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
            if entry.pendingInputTurnId != nil {
                state = .pending
                return
            }
            state = .notStarted
            await recoverPendingOpen(entry: entry, attempt: attempt)
            return
        }
        updateCurrentSession(session)
        pendingInputTurnId = nil
        let record = try? journal.load()
        if let record, let frozen = record.frozenSubmission, frozen.sessionId == session.sessionId {
            if session.turn > 0 {
                clearCommittedJournal()
                state = Self.settledState(session)
                canRetrySameRequest = false
                if let turnId = currentCommittedTurnId {
                    await refreshExpression(
                        sessionId: session.sessionId,
                        turnId: turnId,
                        attempt: attempt
                    )
                }
            } else {
                await recover()
            }
            return
        }
        state = Self.settledState(session)
        if let turnId = currentCommittedTurnId {
            await refreshExpression(
                sessionId: session.sessionId,
                turnId: turnId,
                attempt: attempt
            )
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
        let frozen = StoryFrozenSubmission(
            sessionId: view.sessionId,
            inputTurnId: idFactory(),
            rawInput: trimmed,
            expectedStoryRevision: view.storyRevision,
            expectedStoreRevision: view.observedStoreRevision)
        await submit(frozen)
    }

    public func retryFrozenSubmission() async {
        guard canRetrySameRequest, let record = try? journal.load(),
              let frozen = record.frozenSubmission else { return }
        await submit(frozen)
    }

    private func submit(_ frozen: StoryFrozenSubmission) async {
        let attempt = generation
        let record = StoryRequestRecord(
            phase: .submitting,
            openRequestId: nil,
            openStoreRevision: nil,
            sessionId: frozen.sessionId,
            inputTurnId: frozen.inputTurnId,
            rawInput: frozen.rawInput,
            storyRevision: frozen.expectedStoryRevision,
            storeRevision: frozen.expectedStoreRevision)
        guard writeJournal(record) else { return }
        canRetrySameRequest = false
        state = .submitting
        do {
            let request = try StoryAdviceSubmitRequestDTO(
                sessionId: frozen.sessionId,
                inputTurnId: frozen.inputTurnId,
                rawInput: frozen.rawInput,
                expectedStoryRevision: frozen.expectedStoryRevision,
                expectedStoreRevision: frozen.expectedStoreRevision)
            let result = try await client.storySubmit(request)
            guard attempt == generation else { return }
            updateCurrentSession(result.session, committedTurnId: result.receipt.turnId)
            if let delivery = result.delivery, delivery.state == .unavailable {
                audioUnavailableReason = delivery.reason
            } else {
                audioUnavailableReason = nil
            }
            draft = ""
            try? journal.save(record.withPhase(.committed))
            lastServiceCode = nil
            state = Self.settledState(result.session)
            if result.session.canSubmit {
                // The commit is durable; only the next turn's advice is still
                // unknown, and a failed read must never rewrite committed facts.
                await refreshAdviceAfterCommit(attempt: attempt)
            } else {
                // `can_submit == false` is the Engine's closed-run signal, so the
                // last turn's advice must not stay advertised.
                supportedAdvice = []
            }
            if let turnId = currentCommittedTurnId {
                await refreshExpression(
                    sessionId: result.session.sessionId,
                    turnId: turnId,
                    attempt: attempt
                )
            }
        } catch {
            guard attempt == generation else { return }
            await handleSubmitFailure(error, frozen: frozen)
        }
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

    /// Reads the durable, player-disclosed text projection after commit or restore.
    /// It never resubmits input and treats a query failure as a read failure only.
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

    private func handleSubmitFailure(_ error: any Error, frozen: StoryFrozenSubmission) async {
        guard let service = error as? StoryControlServiceError else {
            // Unknown outcome: keep the frozen text and identity, then only read.
            state = .recovering
            canRetrySameRequest = false
            return
        }
        lastServiceCode = service.code
        switch service.code {
        case "deterministic_input_unsupported":
            try? journal.clear()
            canRetrySameRequest = false
            state = .failed(code: service.code)
        case "iteration_limit_reached":
            await refreshEntry()
        case "pending_turn_exists":
            await recover()
        case "revision_conflict", "recovery_required":
            canRetrySameRequest = false
            state = .failed(code: service.code)
        case "authorization_denied":
            canRetrySameRequest = false
            state = .failed(code: service.code)
        default:
            canRetrySameRequest = true
            if service.retryable {
                state = .recovering
                await recover()
            } else {
                state = .failed(code: service.code)
            }
        }
        _ = frozen
    }

    // MARK: - Recovery

    /// Re-read the committed session after a turn this client did not submit
    /// through `submit()` — for example a voice turn, which commits its own
    /// durable input turn id.
    public func reloadSession() async {
        guard state != .unavailable, let sessionId = view?.sessionId else { return }
        let attempt = generation
        do {
            let fetched = try await client.storySession(sessionId: sessionId)
            guard attempt == generation else { return }
            updateCurrentSession(fetched.session)
            if let turnId = currentCommittedTurnId {
                await refreshExpression(
                    sessionId: fetched.session.sessionId,
                    turnId: turnId,
                    attempt: attempt
                )
            }
        } catch {
            // A failed refresh must not invent a failure the player did not have:
            // the committed world is unchanged and the next read will catch up.
        }
    }

    public func recover() async {
        // A detached panel never queries the previous connection's Engine.
        guard state != .unavailable else { return }
        guard let record = try? journal.load(), let frozen = record.frozenSubmission else {
            if pendingInputTurnId != nil { state = .pending }
            return
        }
        let attempt = generation
        state = .recovering
        do {
            let found = try await client.storyAdvice(
                sessionId: frozen.sessionId, inputTurnId: frozen.inputTurnId)
            guard attempt == generation else { return }
            guard found.found, let receipt = found.receipt else {
                canRetrySameRequest = true
                state = .failed(code: "input_not_found")
                return
            }
            if let session = found.session { updateCurrentSession(session) }
            switch receipt.status {
            case "committed":
                try? journal.save(record.withPhase(.committed))
                canRetrySameRequest = false
                currentCommittedTurnId = receipt.turnId
                let settled = found.session ?? view
                state = settled.map(Self.settledState) ?? .completed
                await refreshExpression(
                    sessionId: frozen.sessionId,
                    turnId: receipt.turnId,
                    attempt: attempt
                )
            case "received":
                canRetrySameRequest = true
                state = .pending
            default:
                try? journal.clear()
                canRetrySameRequest = false
                state = .failed(code: "input_turn_cancelled")
            }
        } catch {
            guard attempt == generation else { return }
            fail(error)
        }
    }

    /// Explicit user continuation of an already-received request.
    public func continuePendingRequest() async {
        guard state == .pending, let record = try? journal.load(),
              let frozen = record.frozenSubmission else { return }
        await submit(frozen)
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
            expression = nil
            expressionReadFailed = false
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
            expression = nil
            expressionReadFailed = false
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
