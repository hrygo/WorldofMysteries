import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("SpeechRail Realtime ASR input turn assembly")
struct SpeechRailRealtimeASRTests {
    private func envelope(
        _ sequence: Int64,
        _ event: SpeechRailASRServerEvent,
        eventID: String? = nil,
        sessionID: String = "sess-1"
    ) -> SpeechRailASRServerEnvelope {
        SpeechRailASRServerEnvelope(
            eventID: eventID ?? "evt-\(sequence)",
            sessionID: sessionID,
            sequence: sequence,
            event: event
        )
    }

    @Test("Rollover items assemble once in committed order and ignore an empty tail")
    func rolloverAssembly() throws {
        let epoch = UUID()
        var turn = InputTurnAssembler(connectionEpoch: epoch, startingSequence: 0)
        try turn.beginFinalization()

        turn.observe(envelope(1, .committed(itemID: "a")), connectionEpoch: epoch)
        turn.observe(envelope(2, .completed(itemID: "a", transcript: "先观察")), connectionEpoch: epoch)
        turn.observe(envelope(3, .committed(itemID: "b")), connectionEpoch: epoch)
        turn.observe(envelope(4, .completed(itemID: "b", transcript: "再敲门")), connectionEpoch: epoch)
        turn.observe(envelope(5, .committed(itemID: "tail")), connectionEpoch: epoch)
        turn.observe(envelope(6, .completed(itemID: "tail", transcript: "")), connectionEpoch: epoch)
        turn.observe(envelope(7, .cleared), connectionEpoch: epoch)

        guard case .transcript(let final)? = turn.terminalResult else {
            Issue.record("Expected one final transcript")
            return
        }
        #expect(final.text == "先观察再敲门")
        #expect(final.segments.map(\.itemID) == ["a", "b"])
    }

    @Test("Async final arrival order never changes committed order")
    func finalArrivalOrder() throws {
        let epoch = UUID()
        var turn = InputTurnAssembler(connectionEpoch: epoch, startingSequence: 10)
        try turn.beginFinalization()

        turn.observe(envelope(11, .committed(itemID: "a")), connectionEpoch: epoch)
        turn.observe(envelope(12, .committed(itemID: "b")), connectionEpoch: epoch)
        turn.observe(envelope(13, .completed(itemID: "b", transcript: "后段")), connectionEpoch: epoch)
        turn.observe(envelope(14, .completed(itemID: "a", transcript: "前段")), connectionEpoch: epoch)
        turn.observe(envelope(15, .cleared), connectionEpoch: epoch)

        guard case .transcript(let final)? = turn.terminalResult else {
            Issue.record("Expected one final transcript")
            return
        }
        #expect(final.text == "前段后段")
        #expect(final.segments.map(\.itemID) == ["a", "b"])
    }

    @Test("Equal text in distinct committed items is not deduplicated")
    func repeatedTextIsNotDeduplicated() throws {
        let epoch = UUID()
        var turn = InputTurnAssembler(connectionEpoch: epoch, startingSequence: 0)
        try turn.beginFinalization()
        turn.observe(envelope(1, .committed(itemID: "a")), connectionEpoch: epoch)
        turn.observe(envelope(2, .completed(itemID: "a", transcript: "好")), connectionEpoch: epoch)
        turn.observe(envelope(3, .committed(itemID: "b")), connectionEpoch: epoch)
        turn.observe(envelope(4, .completed(itemID: "b", transcript: "好")), connectionEpoch: epoch)
        turn.observe(envelope(5, .cleared), connectionEpoch: epoch)

        guard case .transcript(let final)? = turn.terminalResult else {
            Issue.record("Expected a transcript")
            return
        }
        #expect(final.text == "好好")
        #expect(final.segments.count == 2)
    }

    @Test("Cleared never washes an item failure into success")
    func failedItemStaysFailed() throws {
        let epoch = UUID()
        var turn = InputTurnAssembler(connectionEpoch: epoch, startingSequence: 0)
        try turn.beginFinalization()
        turn.observe(envelope(1, .committed(itemID: "a")), connectionEpoch: epoch)
        turn.observe(envelope(2, .completed(itemID: "a", transcript: "前段")), connectionEpoch: epoch)
        turn.observe(envelope(3, .committed(itemID: "b")), connectionEpoch: epoch)
        turn.observe(envelope(4, .failed(itemID: "b", code: "backend_timeout")), connectionEpoch: epoch)
        turn.observe(envelope(5, .cleared), connectionEpoch: epoch)

        #expect(turn.terminalResult == .failed(.itemFailed(itemID: "b", code: "backend_timeout")))
    }

    @Test("Cleared with a missing item terminal fails closed")
    func missingTerminalFailsClosed() throws {
        let epoch = UUID()
        var turn = InputTurnAssembler(connectionEpoch: epoch, startingSequence: 0)
        try turn.beginFinalization()
        turn.observe(envelope(1, .committed(itemID: "a")), connectionEpoch: epoch)
        turn.observe(envelope(2, .completed(itemID: "a", transcript: "前段")), connectionEpoch: epoch)
        turn.observe(envelope(3, .committed(itemID: "b")), connectionEpoch: epoch)
        turn.observe(envelope(4, .cleared), connectionEpoch: epoch)

        #expect(
            turn.terminalResult
                == .failed(.clearedBeforeAllItemsTerminal(missingItemIDs: ["b"]))
        )
    }

    @Test("A server sequence gap invalidates the whole input turn")
    func sequenceGapFailsClosed() throws {
        let epoch = UUID()
        var turn = InputTurnAssembler(connectionEpoch: epoch, startingSequence: 40)
        try turn.beginFinalization()
        turn.observe(envelope(42, .committed(itemID: "a")), connectionEpoch: epoch)

        #expect(turn.terminalResult == .failed(.sequenceGap(expected: 41, actual: 42)))
    }

    @Test("Events from an old connection epoch cannot contaminate the new turn")
    func oldEpochIsIgnored() throws {
        let epoch = UUID()
        let oldEpoch = UUID()
        var turn = InputTurnAssembler(connectionEpoch: epoch, startingSequence: 0)
        try turn.beginFinalization()

        turn.observe(envelope(1, .committed(itemID: "old")), connectionEpoch: oldEpoch)
        #expect(turn.terminalResult == nil)
        #expect(turn.latestDraftText.isEmpty)

        turn.observe(envelope(1, .committed(itemID: "new")), connectionEpoch: epoch)
        turn.observe(envelope(2, .completed(itemID: "new", transcript: "新的")), connectionEpoch: epoch)
        turn.observe(envelope(3, .cleared), connectionEpoch: epoch)

        guard case .transcript(let final)? = turn.terminalResult else {
            Issue.record("Expected current-epoch transcript")
            return
        }
        #expect(final.text == "新的")
    }

    @Test("Cancellation never publishes a FinalTranscript")
    func cancellation() throws {
        let epoch = UUID()
        var turn = InputTurnAssembler(connectionEpoch: epoch, startingSequence: 0)
        turn.cancel()
        turn.observe(envelope(1, .cleared), connectionEpoch: epoch)
        #expect(turn.terminalResult == .cancelled)
    }

    @Test("Partial text is UI-only and completed text replaces it")
    func partialIsOnlyDraft() throws {
        let epoch = UUID()
        var turn = InputTurnAssembler(connectionEpoch: epoch, startingSequence: 0)
        try turn.beginFinalization()
        turn.observe(envelope(1, .committed(itemID: "a")), connectionEpoch: epoch)
        turn.observe(envelope(2, .partial(itemID: "a", delta: "先观")), connectionEpoch: epoch)
        turn.observe(envelope(3, .partial(itemID: "a", delta: "察")), connectionEpoch: epoch)
        #expect(turn.latestDraftText == "先观察")
        #expect(turn.terminalResult == nil)

        turn.observe(envelope(4, .completed(itemID: "a", transcript: "先观察。")), connectionEpoch: epoch)
        turn.observe(envelope(5, .cleared), connectionEpoch: epoch)
        guard case .transcript(let final)? = turn.terminalResult else {
            Issue.record("Expected final transcript")
            return
        }
        #expect(final.text == "先观察。")
    }

    @Test("Empty committed turn produces no Advice payload")
    func emptyTurn() throws {
        let epoch = UUID()
        var turn = InputTurnAssembler(connectionEpoch: epoch, startingSequence: 0)
        try turn.beginFinalization()
        turn.observe(envelope(1, .committed(itemID: "a")), connectionEpoch: epoch)
        turn.observe(envelope(2, .completed(itemID: "a", transcript: "   ")), connectionEpoch: epoch)
        turn.observe(envelope(3, .cleared), connectionEpoch: epoch)
        #expect(turn.terminalResult == .empty)
    }

    @Test("Envelope decoder keeps unknown event types while preserving service sequence")
    func decoderKeepsUnknownEvents() throws {
        let json = #"{"type":"speechrail.future.event","event_id":"e1","session_id":"s1","sequence":7,"private":"ignored"}"#
        let envelope = try SpeechRailASRServerEnvelope.decode(Data(json.utf8))
        #expect(envelope.sequence == 7)
        #expect(envelope.event == .other(type: "speechrail.future.event"))
    }

    @Test("Envelope decoder reads current SpeechRail completed and error shapes")
    func decoderReadsKnownShapes() throws {
        let completed = try SpeechRailASRServerEnvelope.decode(
            Data(
                #"{"type":"conversation.item.input_audio_transcription.completed","event_id":"e2","session_id":"s1","sequence":8,"item_id":"i1","transcript":"你好"}"#.utf8
            )
        )
        #expect(completed.event == .completed(itemID: "i1", transcript: "你好"))

        let error = try SpeechRailASRServerEnvelope.decode(
            Data(
                #"{"type":"error","event_id":"e3","session_id":"s1","sequence":9,"error":{"code":"backend_busy","event_id":"client-append-1"}}"#.utf8
            )
        )
        #expect(error.event == .error(code: "backend_busy", triggerEventID: "client-append-1"))
    }
}
