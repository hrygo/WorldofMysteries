import Foundation

public nonisolated enum SpeechRailRealtimeASRFailure: Error, Sendable, Equatable, LocalizedError {
    case invalidEnvelope
    case sequenceGap(expected: Int64, actual: Int64)
    case duplicateEventConflict(eventID: String)
    case duplicateCommittedItem(itemID: String)
    case terminalBeforeCommit(itemID: String)
    case itemFailed(itemID: String, code: String?)
    case serverError(code: String)
    case clearedBeforeAllItemsTerminal(missingItemIDs: [String])
    case clearedWithoutCommittedItem
    case connectionClosed
    case invalidState

    public var errorDescription: String? {
        "The realtime speech input turn could not be proven complete."
    }
}

public nonisolated enum SpeechRailASRServerEvent: Sendable, Equatable {
    case sessionCreated
    case conversationCreated
    case sessionUpdated
    case committed(itemID: String)
    case itemCreated(itemID: String?)
    case partial(itemID: String, delta: String)
    case completed(itemID: String, transcript: String)
    case failed(itemID: String, code: String?)
    case cleared
    case error(code: String, triggerEventID: String?)
    case other(type: String)

    fileprivate var typeName: String {
        switch self {
        case .sessionCreated: "session.created"
        case .conversationCreated: "conversation.created"
        case .sessionUpdated: "session.updated"
        case .committed: "input_audio_buffer.committed"
        case .itemCreated: "conversation.item.created"
        case .partial: "conversation.item.input_audio_transcription.delta"
        case .completed: "conversation.item.input_audio_transcription.completed"
        case .failed: "conversation.item.input_audio_transcription.failed"
        case .cleared: "input_audio_buffer.cleared"
        case .error: "error"
        case .other(let type): type
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
              base.sequence > 0
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

        let event: SpeechRailASRServerEvent
        switch base.type {
        case "session.created":
            event = .sessionCreated
        case "conversation.created":
            event = .conversationCreated
        case "session.updated":
            event = .sessionUpdated
        case "input_audio_buffer.committed":
            event = .committed(itemID: try requiredString("item_id"))
        case "conversation.item.created":
            let itemID = ((object["item"] as? [String: Any])?["id"] as? String)
            event = .itemCreated(itemID: itemID)
        case "conversation.item.input_audio_transcription.delta":
            event = .partial(
                itemID: try requiredString("item_id"),
                delta: object["delta"] as? String ?? ""
            )
        case "conversation.item.input_audio_transcription.completed":
            event = .completed(
                itemID: try requiredString("item_id"),
                transcript: object["transcript"] as? String ?? ""
            )
        case "conversation.item.input_audio_transcription.failed":
            let nested = object["error"] as? [String: Any]
            event = .failed(
                itemID: try requiredString("item_id"),
                code: nested?["code"] as? String
            )
        case "input_audio_buffer.cleared":
            event = .cleared
        case "error":
            guard let nested = object["error"] as? [String: Any],
                  let code = nested["code"] as? String,
                  !code.isEmpty
            else {
                throw SpeechRailRealtimeASRFailure.invalidEnvelope
            }
            event = .error(code: code, triggerEventID: nested["event_id"] as? String)
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

    public let inputTurnID: UUID
    public let connectionEpoch: UUID

    private var serviceSessionID: String?
    private var lastSequence: Int64
    private var seenEvents: [String: SeenEvent] = [:]
    private var committedOrder: [String] = []
    private var committedItems: Set<String> = []
    private var terminals: [String: ItemTerminal] = [:]
    private var partials: [String: String] = [:]
    private var finalizationRequested = false
    private var clearedSeen = false
    private var terminalResultStorage: InputTurnTerminalResult?

    public init(
        inputTurnID: UUID = UUID(),
        connectionEpoch: UUID,
        startingSequence: Int64
    ) {
        self.inputTurnID = inputTurnID
        self.connectionEpoch = connectionEpoch
        self.lastSequence = startingSequence
    }

    public var terminalResult: InputTurnTerminalResult? {
        terminalResultStorage
    }

    public var isTerminal: Bool {
        terminalResultStorage != nil
    }

    public var latestDraftText: String {
        committedOrder.map { itemID in
            switch terminals[itemID] {
            case .completed(let transcript):
                transcript
            case .failed:
                ""
            case nil:
                partials[itemID] ?? ""
            }
        }.joined()
    }

    public mutating func beginFinalization() throws {
        guard terminalResultStorage == nil, !finalizationRequested else {
            throw SpeechRailRealtimeASRFailure.invalidState
        }
        finalizationRequested = true
        evaluateIfPossible()
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
        case .committed(let itemID):
            guard committedItems.insert(itemID).inserted else {
                fail(.duplicateCommittedItem(itemID: itemID))
                return
            }
            committedOrder.append(itemID)

        case .partial(let itemID, let delta):
            guard committedItems.contains(itemID) else {
                fail(.terminalBeforeCommit(itemID: itemID))
                return
            }
            partials[itemID, default: ""].append(delta)

        case .completed(let itemID, let transcript):
            guard committedItems.contains(itemID) else {
                fail(.terminalBeforeCommit(itemID: itemID))
                return
            }
            terminals[itemID] = .completed(transcript)

        case .failed(let itemID, let code):
            guard committedItems.contains(itemID) else {
                fail(.terminalBeforeCommit(itemID: itemID))
                return
            }
            terminals[itemID] = .failed(code)
            fail(.itemFailed(itemID: itemID, code: code))
            return

        case .cleared:
            clearedSeen = true

        case .error(let code, _):
            fail(.serverError(code: code))
            return

        case .sessionCreated,
             .conversationCreated,
             .sessionUpdated,
             .itemCreated,
             .other:
            break
        }

        evaluateIfPossible()
    }

    private mutating func evaluateIfPossible() {
        guard terminalResultStorage == nil,
              finalizationRequested,
              clearedSeen
        else {
            return
        }

        guard !committedOrder.isEmpty else {
            fail(.clearedWithoutCommittedItem)
            return
        }

        let missing = committedOrder.filter { terminals[$0] == nil }
        guard missing.isEmpty else {
            fail(.clearedBeforeAllItemsTerminal(missingItemIDs: missing))
            return
        }

        var segments: [FinalTranscript.Segment] = []
        for itemID in committedOrder {
            guard case .completed(let transcript)? = terminals[itemID] else {
                fail(.itemFailed(itemID: itemID, code: nil))
                return
            }
            if !transcript.isEmpty {
                segments.append(.init(itemID: itemID, text: transcript))
            }
        }

        guard !segments.allSatisfy({ $0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) else {
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
