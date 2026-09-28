import Foundation
import Observation

/// The shared mutation and recovery boundary for typed advice and ASR input.
///
/// The journal is written before either wire method is called. Once a request
/// may have reached the Engine, this coordinator only queries that same identity
/// until the player explicitly continues a `received` or `notFound` request.
public protocol StorySubmissionClient: Sendable {
    func storySubmit(_ request: StoryAdviceSubmitRequestDTO) async throws -> StoryAdviceSubmitViewDTO
    func storyTurnSubmit(_ request: StoryTurnSubmitRequestDTO) async throws -> StoryAdviceSubmitViewDTO
    func storyAdvice(sessionId: String, inputTurnId: String) async throws -> StoryAdviceGetViewDTO
}

public extension StorySubmissionClient {
    /// Keeps older story test doubles source-compatible. Production clients
    /// implement the live-turn method in their typed IPC adapter.
    func storyTurnSubmit(
        _ request: StoryTurnSubmitRequestDTO
    ) async throws -> StoryAdviceSubmitViewDTO {
        _ = request
        throw EngineConnectionError.methodUnavailable
    }
}

@Observable
@MainActor
public final class StorySubmissionCoordinator {
    public enum State: Equatable, Sendable {
        case idle
        case submitting
        case committed
        case outcomeUnknown
        case querying
        case received
        case notFound
        case blocked(code: String)
    }

    public private(set) var state: State = .idle
    public private(set) var frozenSubmission: StoryFrozenSubmission?
    public private(set) var latestResult: StoryAdviceSubmitViewDTO?
    public private(set) var latestReceipt: StoryReceiptViewDTO?
    public private(set) var latestSession: StoryPublicViewDTO?

    @ObservationIgnored private let client: any StorySubmissionClient
    @ObservationIgnored private let journal: any StoryJournalWriting
    @ObservationIgnored private let idFactory: @Sendable () -> String
    @ObservationIgnored private var generation: UInt64 = 0

    public init(
        client: any StorySubmissionClient,
        journal: any StoryJournalWriting = StoryRequestJournal(),
        idFactory: @escaping @Sendable () -> String = { UUID().uuidString }
    ) {
        self.client = client
        self.journal = journal
        self.idFactory = idFactory
    }

    /// A single operation slot is shared by typed and voice input.
    public var canAcceptNewInput: Bool {
        switch state {
        case .idle, .committed:
            return true
        case .blocked(code: "deterministic_input_unsupported"):
            return true
        case .submitting, .outcomeUnknown, .querying, .received, .notFound, .blocked:
            return false
        }
    }

    public var statusText: String? {
        switch state {
        case .idle:
            return nil
        case .submitting, .outcomeUnknown, .querying:
            return "结果待确认"
        case .received, .notFound:
            return "已记录未提交"
        case .committed:
            return "已保存"
        case .blocked:
            return "无法恢复"
        }
    }

    /// Validates all caller-controlled input before allocating the one request ID.
    /// For voice, `rawInput` is the final transcript byte-for-byte.
    @discardableResult
    public func submit(
        rawInput: String,
        inputMode: StoryInputMode,
        sessionId: String,
        expectedStoryRevision: Int,
        expectedStoreRevision: Int
    ) async -> StoryFrozenSubmission? {
        guard canAcceptNewInput else { return nil }

        do {
            _ = try StoryControl.identifier(sessionId)
            _ = try StoryControl.rawInput(rawInput)
            _ = try StoryControl.revision(expectedStoryRevision, expected: true)
            _ = try StoryControl.revision(expectedStoreRevision, expected: true)
        } catch {
            return nil
        }

        do {
            try ensureExistingJournalIsSettled()
        } catch CoordinatorGuardError.unsettledJournal {
            return nil
        } catch {
            state = .blocked(code: Self.journalErrorCode(error))
            return nil
        }

        let method: StorySubmissionMethod = inputMode == .voice
            ? .storyTurnSubmit
            : .storyAdviceSubmit
        let inputTurnId = idFactory()
        do {
            _ = try StoryControl.identifier(inputTurnId)
        } catch {
            state = .blocked(code: "invalid_identity")
            return nil
        }
        let frozen = StoryFrozenSubmission(
            sessionId: sessionId,
            inputTurnId: inputTurnId,
            rawInput: rawInput,
            expectedStoryRevision: expectedStoryRevision,
            expectedStoreRevision: expectedStoreRevision,
            inputMode: inputMode,
            submissionMethod: method
        )
        let record = Self.record(for: frozen, phase: .submitting)
        do {
            try journal.save(record)
        } catch {
            state = .blocked(code: "journal_unavailable")
            return nil
        }

        frozenSubmission = frozen
        latestResult = nil
        latestReceipt = nil
        latestSession = nil
        state = .submitting
        let attempt = generation
        await send(frozen, attempt: attempt)
        return frozen
    }

    /// Reads the server receipt for the journaled identity. It never resends.
    public func recover(expectedSessionId: String? = nil) async {
        guard state != .submitting, state != .querying else { return }
        let record: StoryRequestRecord
        do {
            guard let loaded = try journal.load() else {
                frozenSubmission = nil
                state = .idle
                return
            }
            record = loaded
        } catch {
            state = .blocked(code: Self.journalErrorCode(error))
            return
        }
        guard let frozen = record.frozenSubmission else {
            state = .idle
            return
        }
        if let expectedSessionId, frozen.sessionId != expectedSessionId {
            frozenSubmission = frozen
            state = .blocked(code: "session_mismatch")
            return
        }
        frozenSubmission = frozen
        latestResult = nil
        latestReceipt = nil
        latestSession = nil
        let attempt = generation
        await query(frozen, record: record, attempt: attempt)
    }

    /// The only resend path. It reuses every frozen field and requires an
    /// explicit user action after the Engine reports `received` or `notFound`.
    public func continuePendingRequest() async {
        guard state == .received || state == .notFound,
              let frozen = frozenSubmission else {
            return
        }
        do {
            try journal.save(Self.record(for: frozen, phase: .submitting))
        } catch {
            state = .blocked(code: "journal_unavailable")
            return
        }
        state = .submitting
        latestResult = nil
        latestReceipt = nil
        latestSession = nil
        let attempt = generation
        await send(frozen, attempt: attempt)
    }

    /// Invalidates callbacks from an old transport while retaining the journal.
    public func detachForConnectionChange() {
        generation &+= 1
        switch state {
        case .submitting, .querying:
            state = .outcomeUnknown
        case .idle, .committed, .outcomeUnknown, .received, .notFound, .blocked:
            break
        }
    }

    /// Used by the session facade when server state proves a local journal is
    /// missing or incompatible. It never deletes the record.
    public func block(code: String) {
        state = .blocked(code: code)
    }

    private func ensureExistingJournalIsSettled() throws {
        guard let existing = try journal.load(),
              let frozen = existing.frozenSubmission else {
            return
        }
        guard state == .committed,
              frozenSubmission?.inputTurnId == frozen.inputTurnId,
              existing.phase == .committed else {
            frozenSubmission = frozen
            state = .blocked(code: "recovery_required")
            throw CoordinatorGuardError.unsettledJournal
        }
    }

    private func send(_ frozen: StoryFrozenSubmission, attempt: UInt64) async {
        do {
            let response: StoryAdviceSubmitViewDTO
            switch frozen.submissionMethod {
            case .storyAdviceSubmit:
                response = try await client.storySubmit(
                    StoryAdviceSubmitRequestDTO(
                        sessionId: frozen.sessionId,
                        inputTurnId: frozen.inputTurnId,
                        rawInput: frozen.rawInput,
                        expectedStoryRevision: frozen.expectedStoryRevision,
                        expectedStoreRevision: frozen.expectedStoreRevision
                    )
                )
            case .storyTurnSubmit:
                response = try await client.storyTurnSubmit(
                    StoryTurnSubmitRequestDTO(
                        sessionId: frozen.sessionId,
                        inputTurnId: frozen.inputTurnId,
                        rawInput: frozen.rawInput,
                        inputMode: frozen.inputMode,
                        expectedStoryRevision: frozen.expectedStoryRevision,
                        expectedStoreRevision: frozen.expectedStoreRevision
                    )
                )
            }
            guard attempt == generation else { return }
            guard response.receipt.sessionId == frozen.sessionId,
                  response.receipt.inputTurnId == frozen.inputTurnId,
                  response.receipt.status == "committed" else {
                state = .blocked(code: "identity_mismatch")
                return
            }
            latestResult = response
            latestReceipt = response.receipt
            latestSession = response.session
            state = .committed
            try? journal.save(
                Self.record(for: frozen, phase: .committed).upgradedForNextSave()
            )
        } catch {
            guard attempt == generation else { return }
            if let service = error as? StoryControlServiceError {
                switch service.code {
                case "deterministic_input_unsupported":
                    try? journal.clear()
                    frozenSubmission = nil
                    state = .blocked(code: service.code)
                    return
                case "revision_conflict", "recovery_required", "authorization_denied",
                     "schema_invalid", "identity_conflict", "identity_mismatch":
                    state = .blocked(code: service.code)
                    return
                case "input_not_found":
                    state = .notFound
                    return
                default:
                    if !service.retryable {
                        state = .blocked(code: service.code)
                        return
                    }
                }
            }
            state = .outcomeUnknown
            guard let record = try? journal.load() else { return }
            await query(frozen, record: record, attempt: attempt)
        }
    }

    private func query(
        _ frozen: StoryFrozenSubmission,
        record: StoryRequestRecord,
        attempt: UInt64
    ) async {
        state = .querying
        do {
            let found = try await client.storyAdvice(
                sessionId: frozen.sessionId,
                inputTurnId: frozen.inputTurnId
            )
            guard attempt == generation else { return }
            guard found.found else {
                state = .notFound
                return
            }
            guard let receipt = found.receipt,
                  receipt.sessionId == frozen.sessionId,
                  receipt.inputTurnId == frozen.inputTurnId else {
                state = .blocked(code: "identity_mismatch")
                return
            }
            latestReceipt = receipt
            latestSession = found.session
            switch receipt.status {
            case "committed":
                state = .committed
                try? journal.save(
                    Self.record(for: frozen, phase: .committed).upgradedForNextSave()
                )
            case "received":
                do {
                    try journal.save(
                        Self.record(for: frozen, phase: .submitting).upgradedForNextSave()
                    )
                    state = .received
                } catch {
                    state = .blocked(code: "journal_unavailable")
                }
            default:
                state = .blocked(code: "input_turn_cancelled")
            }
        } catch {
            guard attempt == generation else { return }
            if let service = error as? StoryControlServiceError, !service.retryable {
                state = .blocked(code: service.code)
            } else {
                state = .outcomeUnknown
            }
        }
    }

    private static func record(
        for frozen: StoryFrozenSubmission,
        phase: StoryRequestRecord.Phase
    ) -> StoryRequestRecord {
        StoryRequestRecord(
            phase: phase,
            recordVersion: StoryRequestRecord.currentRecordVersion,
            inputMode: frozen.inputMode,
            submissionMethod: frozen.submissionMethod,
            sessionId: frozen.sessionId,
            inputTurnId: frozen.inputTurnId,
            rawInput: frozen.rawInput,
            storyRevision: frozen.expectedStoryRevision,
            storeRevision: frozen.expectedStoreRevision
        )
    }

    private static func journalErrorCode(_ error: any Error) -> String {
        if error is StoryRequestJournalError || error is DecodingError {
            return "journal_unreadable"
        }
        return "journal_unavailable"
    }

    private enum CoordinatorGuardError: Error {
        case unsettledJournal
    }
}
