import Foundation

public nonisolated enum SpeechRailRealtimeASRFailure: Error, Sendable, Equatable, LocalizedError {
    case invalidConfiguration
    case notConnected
    case unsupportedMessage
    case sessionRejected(code: String)
    case sessionConfigurationMismatch
    /// The upgrade was refused before the WebSocket close handshake existed.
    /// The HTTP status is diagnostic only and may be absent, because
    /// `URLSessionWebSocketTask` does not always surface it.
    case handshakeRejected(httpStatus: Int?)
    /// A policy-violation close (1008) is the only close code that is evidence
    /// of a rejected credential.
    case authenticationFailed
    case serviceBusy
    case audioFrameInvalid
    case captureFailure
    case transportFailure
    case finalizationTimedOut
    case invalidEnvelope
    case sequenceGap(expected: Int64, actual: Int64)
    case duplicateEventConflict(eventID: String)
    case conflictingFinal(itemID: String)
    case itemNotTerminal(itemIDs: [String])
    case itemFailed(itemID: String, code: String?)
    case serverError(code: String)
    case connectionClosed
    case invalidState

    public var errorDescription: String? {
        "The realtime speech input turn could not be proven complete."
    }
}

/// A revocable partial recognition result.
///
/// A hypothesis is keyed by utterance and revision and may be replaced or
/// withdrawn. It is a display-only draft: it is never spliced into the final
/// transcript, which is built only from `completed` texts.
public nonisolated struct SpeechRailASHypothesis: Sendable, Equatable {
    public let taskID: String
    public let epoch: Int
    public let utteranceID: String
    public let revision: Int
    public let text: String
    public let stablePrefixCodepoints: Int

    public init(
        taskID: String,
        epoch: Int,
        utteranceID: String,
        revision: Int,
        text: String,
        stablePrefixCodepoints: Int
    ) {
        self.taskID = taskID
        self.epoch = epoch
        self.utteranceID = utteranceID
        self.revision = revision
        self.text = text
        self.stablePrefixCodepoints = stablePrefixCodepoints
    }
}

public nonisolated enum SpeechRailASRServerEvent: Sendable, Equatable {
    case sessionCreated(SpeechRailRealtimeSessionConfiguration)
    case sessionUpdated(SpeechRailRealtimeSessionConfiguration)
    case partial(itemID: String, delta: String)
    case completed(itemID: String, transcript: String)
    case failed(itemID: String, code: String?)
    case hypothesis(SpeechRailASHypothesis)
    /// Alignment and diarization are disabled for this iteration. They are
    /// recognised so they cannot slip past the envelope checks, and ignored so
    /// they cannot influence the text terminal.
    case auxiliary(type: String)
    case error(code: String, triggerEventID: String?)
    case other(type: String)

    fileprivate var typeName: String {
        switch self {
        case .sessionCreated: "session.created"
        case .sessionUpdated: "session.updated"
        case .partial: "conversation.item.input_audio_transcription.delta"
        case .completed: "conversation.item.input_audio_transcription.completed"
        case .failed: "conversation.item.input_audio_transcription.failed"
        case .hypothesis: "speechrail.transcription.hypothesis"
        case .error: "error"
        case .auxiliary(let type), .other(let type): type
        }
    }
}

public nonisolated struct SpeechRailASRServerEnvelope: Sendable, Equatable {
    public let eventID: String
    public let sessionID: String
    public let sequence: Int64
    public let event: SpeechRailASRServerEvent

    public init(
        eventID: String,
        sessionID: String,
        sequence: Int64,
        event: SpeechRailASRServerEvent
    ) {
        self.eventID = eventID
        self.sessionID = sessionID
        self.sequence = sequence
        self.event = event
    }

    public static func decode(_ data: Data) throws -> Self {
        struct Base: Decodable {
            let type: String
            let event_id: String
            let session_id: String
            let sequence: Int64
        }

        let decoder = JSONDecoder()
        let base: Base
        do {
            base = try decoder.decode(Base.self, from: data)
        } catch {
            throw SpeechRailRealtimeASRFailure.invalidEnvelope
        }

        guard !base.type.isEmpty,
              !base.event_id.isEmpty,
              !base.session_id.isEmpty,
              base.sequence >= 0
        else {
            throw SpeechRailRealtimeASRFailure.invalidEnvelope
        }

        let object: [String: Any]
        do {
            guard let parsed = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
                throw SpeechRailRealtimeASRFailure.invalidEnvelope
            }
            object = parsed
        } catch let error as SpeechRailRealtimeASRFailure {
            throw error
        } catch {
            throw SpeechRailRealtimeASRFailure.invalidEnvelope
        }

        func requiredString(_ key: String) throws -> String {
            guard let value = object[key] as? String, !value.isEmpty else {
                throw SpeechRailRealtimeASRFailure.invalidEnvelope
            }
            return value
        }

        // content_index is a schema constant, not a field we may ignore: a
        // non-zero index means we are not reading the content we think we are.
        func requirePrimaryContentIndex() throws {
            guard let index = object["content_index"] as? NSNumber,
                  index.intValue == 0
            else {
                throw SpeechRailRealtimeASRFailure.invalidEnvelope
            }
        }

        let event: SpeechRailASRServerEvent
        switch base.type {
        case "session.created":
            // The service reports its own defaults here, before this client
            // has sent anything, so the task is not the one we will request.
            event = .sessionCreated(
                try SpeechRailRealtimeSessionConfiguration.parse(
                    object["session"],
                    requiringTask: nil
                )
            )
        case "session.updated":
            event = .sessionUpdated(
                try SpeechRailRealtimeSessionConfiguration.parse(
                    object["session"],
                    requiringTask: SpeechRailRealtimeSessionConfiguration.requestedTask
                )
            )
        case "conversation.item.input_audio_transcription.delta":
            try requirePrimaryContentIndex()
            event = .partial(
                itemID: try requiredString("item_id"),
                delta: object["delta"] as? String ?? ""
            )
        case "conversation.item.input_audio_transcription.completed":
            try requirePrimaryContentIndex()
            event = .completed(
                itemID: try requiredString("item_id"),
                transcript: object["transcript"] as? String ?? ""
            )
        case "conversation.item.input_audio_transcription.failed":
            try requirePrimaryContentIndex()
            let nested = object["error"] as? [String: Any]
            event = .failed(
                itemID: try requiredString("item_id"),
                code: nested?["code"] as? String
            )
        case "speechrail.transcription.hypothesis":
            let span = object["sample_span"] as? [String: Any]
            guard let start = (span?["start"] as? NSNumber)?.intValue,
                  let end = (span?["end"] as? NSNumber)?.intValue,
                  start >= 0, end >= start,
                  let epoch = (object["epoch"] as? NSNumber)?.intValue, epoch >= 0,
                  let revision = (object["revision"] as? NSNumber)?.intValue, revision >= 0
            else {
                throw SpeechRailRealtimeASRFailure.invalidEnvelope
            }
            event = .hypothesis(
                SpeechRailASHypothesis(
                    taskID: try requiredString("task_id"),
                    epoch: epoch,
                    utteranceID: try requiredString("utterance_id"),
                    revision: revision,
                    text: object["text"] as? String ?? "",
                    stablePrefixCodepoints:
                        (object["stable_prefix_codepoints"] as? NSNumber)?.intValue ?? 0
                )
            )
        case "error":
            guard let nested = object["error"] as? [String: Any],
                  let code = nested["code"] as? String,
                  !code.isEmpty
            else {
                throw SpeechRailRealtimeASRFailure.invalidEnvelope
            }
            event = .error(code: code, triggerEventID: nested["event_id"] as? String)
        case "speechrail.alignment.done",
             "speechrail.alignment.failed",
             "speechrail.diarization.updated",
             "speechrail.diarization.done",
             "speechrail.diarization.failed":
            event = .auxiliary(type: base.type)
        default:
            event = .other(type: base.type)
        }

        return Self(
            eventID: base.event_id,
            sessionID: base.session_id,
            sequence: base.sequence,
            event: event
        )
    }
}

public nonisolated struct FinalTranscript: Sendable, Equatable {
    public struct Segment: Sendable, Equatable {
        public let itemID: String
        public let text: String

        public init(itemID: String, text: String) {
            self.itemID = itemID
            self.text = text
        }
    }

    public let inputTurnID: UUID
    public let connectionEpoch: UUID
    public let serviceSessionID: String
    public let segments: [Segment]

    public var text: String {
        segments.map(\.text).joined()
    }

    public init(
        inputTurnID: UUID,
        connectionEpoch: UUID,
        serviceSessionID: String,
        segments: [Segment]
    ) {
        self.inputTurnID = inputTurnID
        self.connectionEpoch = connectionEpoch
        self.serviceSessionID = serviceSessionID
        self.segments = segments
    }
}

public nonisolated enum InputTurnTerminalResult: Sendable, Equatable {
    case transcript(FinalTranscript)
    case empty
    case failed(SpeechRailRealtimeASRFailure)
    case cancelled
}

public nonisolated struct InputTurnAssembler: Sendable {
    private struct SeenEvent: Sendable, Equatable {
        let sequence: Int64
        let type: String
    }

    private enum ItemTerminal: Sendable, Equatable {
        case completed(String)
        case failed(String?)
    }

    private struct ItemState: Sendable {
        var draft: String = ""
        var terminal: ItemTerminal?

        init(draft: String = "", terminal: ItemTerminal? = nil) {
            self.draft = draft
            self.terminal = terminal
        }
    }

    public let inputTurnID: UUID
    public let connectionEpoch: UUID
    /// The configuration the barrier update must echo back unchanged.
    public let expectedSession: SpeechRailRealtimeSessionConfiguration

    private var serviceSessionID: String?
    private var lastSequence: Int64
    private var seenEvents: [String: SeenEvent] = [:]
    private var itemOrder: [String] = []
    private var items: [String: ItemState] = [:]
    private var hypothesis: SpeechRailASHypothesis?
    private var finalizationRequested = false
    private var terminalResultStorage: InputTurnTerminalResult?

    public init(
        inputTurnID: UUID = UUID(),
        connectionEpoch: UUID,
        startingSequence: Int64,
        expectedSession: SpeechRailRealtimeSessionConfiguration
    ) {
        self.inputTurnID = inputTurnID
        self.connectionEpoch = connectionEpoch
        self.lastSequence = startingSequence
        self.expectedSession = expectedSession
    }

    public var terminalResult: InputTurnTerminalResult? {
        terminalResultStorage
    }

    public var isTerminal: Bool {
        terminalResultStorage != nil
    }

    /// Ordered per-item draft text. A `completed` text replaces the draft of
    /// its own item rather than being appended to it.
    public var latestDraftText: String {
        itemOrder.map { itemID in
            switch items[itemID]?.terminal {
            case .completed(let transcript):
                transcript
            case .failed:
                ""
            case nil:
                items[itemID]?.draft ?? ""
            }
        }.joined()
    }

    /// A hypothesis is shown only while no item text is available yet. It is
    /// never merged into the draft, because it may be revised or withdrawn.
    public var transientHypothesisText: String? {
        guard latestDraftText.isEmpty else { return nil }
        guard let hypothesis, !hypothesis.text.isEmpty else { return nil }
        return hypothesis.text
    }

    public mutating func beginFinalization() throws {
        guard terminalResultStorage == nil, !finalizationRequested else {
            throw SpeechRailRealtimeASRFailure.invalidState
        }
        finalizationRequested = true
    }

    public mutating func cancel() {
        guard terminalResultStorage == nil else { return }
        terminalResultStorage = .cancelled
    }

    public mutating func connectionClosed() {
        guard terminalResultStorage == nil else { return }
        terminalResultStorage = .failed(.connectionClosed)
    }

    public mutating func observe(
        _ envelope: SpeechRailASRServerEnvelope,
        connectionEpoch observedEpoch: UUID
    ) {
        guard observedEpoch == connectionEpoch else {
            return
        }
        guard terminalResultStorage == nil else {
            return
        }

        if let existing = seenEvents[envelope.eventID] {
            let candidate = SeenEvent(
                sequence: envelope.sequence,
                type: envelope.event.typeName
            )
            if existing != candidate {
                fail(.duplicateEventConflict(eventID: envelope.eventID))
            }
            return
        }

        let expected = lastSequence + 1
        guard envelope.sequence == expected else {
            fail(.sequenceGap(expected: expected, actual: envelope.sequence))
            return
        }
        lastSequence = envelope.sequence
        seenEvents[envelope.eventID] = SeenEvent(
            sequence: envelope.sequence,
            type: envelope.event.typeName
        )

        if let current = serviceSessionID {
            guard current == envelope.sessionID else {
                fail(.invalidEnvelope)
                return
            }
        } else {
            serviceSessionID = envelope.sessionID
        }

        switch envelope.event {
        case .partial(let itemID, let delta):
            // Deltas for an already final item are stale; the final text wins.
            let key = register(itemID)
            if items[key]?.terminal == nil {
                var state = items[key] ?? ItemState()
                state.draft.append(delta)
                items[key] = state
            }

        case .completed(let itemID, let transcript):
            let key = register(itemID)
            if case .completed(let existing) = items[key]?.terminal {
                // A repeated identical final is idempotent; a different one is
                // a contradiction we cannot resolve.
                guard existing == transcript else {
                    fail(.conflictingFinal(itemID: itemID))
                    return
                }
                return
            }
            guard items[key]?.terminal == nil else {
                fail(.conflictingFinal(itemID: itemID))
                return
            }
            items[key] = ItemState(terminal: .completed(transcript))

        case .failed(let itemID, let code):
            items[register(itemID)] = ItemState(terminal: .failed(code))
            fail(.itemFailed(itemID: itemID, code: code))
            return

        case .hypothesis(let candidate):
            // Revisions are monotonic per utterance; an older one is stale.
            if let current = hypothesis,
               current.utteranceID == candidate.utteranceID,
               current.revision > candidate.revision {
                break
            }
            hypothesis = candidate

        case .error(let code, _):
            fail(.serverError(code: code))
            return

        case .sessionUpdated(let session):
            // The only event that can complete a turn is the update the client
            // itself sent as the barrier. A spontaneous update cannot end a
            // turn that has not asked for one.
            if finalizationRequested {
                evaluateBarrier(session)
            }

        case .sessionCreated,
             .auxiliary,
             .other:
            break
        }
    }

    /// Register first-seen order for an item. SpeechRail 4.0 does not emit a
    /// per-item creation event, so the first delta/completed/failed defines
    /// both membership and transcript ordering.
    private mutating func register(_ itemID: String) -> String {
        if items[itemID] == nil {
            items[itemID] = ItemState()
            itemOrder.append(itemID)
        }
        return itemID
    }

    private mutating func evaluateBarrier(_ session: SpeechRailRealtimeSessionConfiguration) {
        guard terminalResultStorage == nil,
              finalizationRequested
        else {
            return
        }

        // The barrier is only proof if the service is still running the
        // configuration this turn depends on.
        guard session == expectedSession else {
            fail(.sessionConfigurationMismatch)
            return
        }

        let missing = itemOrder.filter { items[$0]?.terminal == nil }
        guard missing.isEmpty else {
            fail(.itemNotTerminal(itemIDs: missing))
            return
        }

        var segments: [FinalTranscript.Segment] = []
        for itemID in itemOrder {
            guard case .completed(let transcript)? = items[itemID]?.terminal else {
                fail(.itemFailed(itemID: itemID, code: nil))
                return
            }
            if !transcript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                segments.append(.init(itemID: itemID, text: transcript))
            }
        }

        guard !segments.isEmpty else {
            terminalResultStorage = .empty
            return
        }
        guard let serviceSessionID else {
            fail(.invalidEnvelope)
            return
        }

        terminalResultStorage = .transcript(
            FinalTranscript(
                inputTurnID: inputTurnID,
                connectionEpoch: connectionEpoch,
                serviceSessionID: serviceSessionID,
                segments: segments
            )
        )
    }

    private mutating func fail(_ failure: SpeechRailRealtimeASRFailure) {
        terminalResultStorage = .failed(failure)
    }
}
