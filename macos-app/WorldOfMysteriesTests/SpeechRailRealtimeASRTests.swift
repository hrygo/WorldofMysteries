import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("SpeechRail Realtime ASR input turn assembly")
struct SpeechRailRealtimeASRTests {
    private let session = SpeechRailRealtimeSessionConfiguration(
        model: "gpt-4o-transcribe",
        language: "zh"
    )

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

    private func assembler(
        epoch: UUID,
        startingSequence: Int64 = 0,
        expected: SpeechRailRealtimeSessionConfiguration? = nil
    ) -> InputTurnAssembler {
        InputTurnAssembler(
            connectionEpoch: epoch,
            startingSequence: startingSequence,
            expectedSession: expected ?? session
        )
    }

    private func hypothesis(
        utterance: String = "u1",
        revision: Int,
        text: String
    ) -> SpeechRailASRServerEvent {
        .hypothesis(
            SpeechRailASHypothesis(
                taskID: "task-1",
                epoch: 0,
                utteranceID: utterance,
                revision: revision,
                text: text,
                stablePrefixCodepoints: 0
            )
        )
    }

    // MARK: - Barrier

    @Test("Finals without any committed or cleared event still assemble in first-seen order")
    func finalsWithoutCommittedEvents() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)
        try turn.beginFinalization()

        turn.observe(envelope(1, .partial(itemID: "a", delta: "先观")), connectionEpoch: epoch)
        turn.observe(envelope(2, .completed(itemID: "a", transcript: "先观察")), connectionEpoch: epoch)
        turn.observe(envelope(3, .partial(itemID: "b", delta: "再敲")), connectionEpoch: epoch)
        turn.observe(envelope(4, .completed(itemID: "b", transcript: "再敲门")), connectionEpoch: epoch)
        turn.observe(envelope(5, .completed(itemID: "tail", transcript: "")), connectionEpoch: epoch)
        #expect(turn.terminalResult == nil, "Finals alone must not end the turn")

        turn.observe(envelope(6, .sessionUpdated(session)), connectionEpoch: epoch)

        guard case .transcript(let final)? = turn.terminalResult else {
            Issue.record("Expected one final transcript")
            return
        }
        #expect(final.text == "先观察再敲门")
        #expect(final.segments.map(\.itemID) == ["a", "b"])
    }

    @Test("A rollover final that arrives early does not complete the turn")
    func earlyRolloverFinalDoesNotComplete() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)
        try turn.beginFinalization()

        turn.observe(envelope(1, .completed(itemID: "a", transcript: "前段")), connectionEpoch: epoch)
        #expect(turn.terminalResult == nil)

        turn.observe(envelope(2, .partial(itemID: "b", delta: "后段")), connectionEpoch: epoch)
        #expect(turn.terminalResult == nil)

        turn.observe(envelope(3, .sessionUpdated(session)), connectionEpoch: epoch)
        #expect(turn.terminalResult == .failed(.itemNotTerminal(itemIDs: ["b"])))
    }

    @Test("An update that arrives before finalization cannot end the turn")
    func updateBeforeFinalizationIsNotABarrier() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)

        turn.observe(envelope(1, .completed(itemID: "a", transcript: "先观察")), connectionEpoch: epoch)
        turn.observe(envelope(2, .sessionUpdated(session)), connectionEpoch: epoch)
        #expect(turn.terminalResult == nil)

        try turn.beginFinalization()
        #expect(turn.terminalResult == nil, "beginFinalization must not self-complete")
        turn.observe(envelope(3, .sessionUpdated(session)), connectionEpoch: epoch)
        guard case .transcript(let final)? = turn.terminalResult else {
            Issue.record("Expected a transcript after the barrier")
            return
        }
        #expect(final.text == "先观察")
    }

    @Test("A barrier whose configuration drifted fails closed")
    func barrierConfigurationDriftFailsClosed() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)
        try turn.beginFinalization()
        turn.observe(envelope(1, .completed(itemID: "a", transcript: "先观察")), connectionEpoch: epoch)

        let drifted = SpeechRailRealtimeSessionConfiguration(
            model: "whisper-1",
            language: "zh"
        )
        turn.observe(envelope(2, .sessionUpdated(drifted)), connectionEpoch: epoch)
        #expect(turn.terminalResult == .failed(.sessionConfigurationMismatch))
    }

    @Test("A barrier with an item that never finalized fails closed")
    func missingTerminalFailsClosed() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)
        try turn.beginFinalization()
        turn.observe(envelope(1, .completed(itemID: "a", transcript: "前段")), connectionEpoch: epoch)
        turn.observe(envelope(2, .partial(itemID: "b", delta: "后")), connectionEpoch: epoch)
        turn.observe(envelope(3, .sessionUpdated(session)), connectionEpoch: epoch)

        #expect(turn.terminalResult == .failed(.itemNotTerminal(itemIDs: ["b"])))
    }

    // MARK: - Item ordering and finals

    @Test("Async final arrival order never changes first-seen order")
    func finalArrivalOrder() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch, startingSequence: 10)
        try turn.beginFinalization()

        turn.observe(envelope(11, .partial(itemID: "a", delta: "前")), connectionEpoch: epoch)
        turn.observe(envelope(12, .partial(itemID: "b", delta: "后")), connectionEpoch: epoch)
        turn.observe(envelope(13, .completed(itemID: "b", transcript: "后段")), connectionEpoch: epoch)
        turn.observe(envelope(14, .completed(itemID: "a", transcript: "前段")), connectionEpoch: epoch)
        turn.observe(envelope(15, .sessionUpdated(session)), connectionEpoch: epoch)

        guard case .transcript(let final)? = turn.terminalResult else {
            Issue.record("Expected one final transcript")
            return
        }
        #expect(final.text == "前段后段")
        #expect(final.segments.map(\.itemID) == ["a", "b"])
    }

    @Test("A completed item may arrive before any of its deltas")
    func completedBeforeDeltas() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)
        try turn.beginFinalization()

        turn.observe(envelope(1, .completed(itemID: "a", transcript: "完整文本")), connectionEpoch: epoch)
        turn.observe(envelope(2, .partial(itemID: "a", delta: "过时增量")), connectionEpoch: epoch)
        #expect(turn.latestDraftText == "完整文本", "A late delta must not extend a final")

        turn.observe(envelope(3, .sessionUpdated(session)), connectionEpoch: epoch)
        guard case .transcript(let final)? = turn.terminalResult else {
            Issue.record("Expected a transcript")
            return
        }
        #expect(final.text == "完整文本")
    }

    @Test("A repeated identical final is idempotent")
    func repeatedIdenticalFinal() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)
        try turn.beginFinalization()

        turn.observe(envelope(1, .completed(itemID: "a", transcript: "好")), connectionEpoch: epoch)
        turn.observe(envelope(2, .completed(itemID: "a", transcript: "好"), eventID: "other"), connectionEpoch: epoch)
        turn.observe(envelope(3, .sessionUpdated(session)), connectionEpoch: epoch)

        guard case .transcript(let final)? = turn.terminalResult else {
            Issue.record("Expected a transcript")
            return
        }
        #expect(final.segments.count == 1)
    }

    @Test("A contradictory final for the same item fails the turn")
    func conflictingFinalFailsClosed() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)
        try turn.beginFinalization()

        turn.observe(envelope(1, .completed(itemID: "a", transcript: "好")), connectionEpoch: epoch)
        turn.observe(envelope(2, .completed(itemID: "a", transcript: "好吧"), eventID: "other"), connectionEpoch: epoch)
        #expect(turn.terminalResult == .failed(.conflictingFinal(itemID: "a")))
    }

    @Test("Equal text in distinct items is not deduplicated")
    func repeatedTextIsNotDeduplicated() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)
        try turn.beginFinalization()
        turn.observe(envelope(1, .completed(itemID: "a", transcript: "好")), connectionEpoch: epoch)
        turn.observe(envelope(2, .completed(itemID: "b", transcript: "好")), connectionEpoch: epoch)
        turn.observe(envelope(3, .sessionUpdated(session)), connectionEpoch: epoch)

        guard case .transcript(let final)? = turn.terminalResult else {
            Issue.record("Expected a transcript")
            return
        }
        #expect(final.text == "好好")
        #expect(final.segments.count == 2)
    }

    @Test("An item failure never washes into success")
    func failedItemStaysFailed() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)
        try turn.beginFinalization()
        turn.observe(envelope(1, .completed(itemID: "a", transcript: "前段")), connectionEpoch: epoch)
        turn.observe(envelope(2, .failed(itemID: "b", code: "backend_timeout")), connectionEpoch: epoch)

        #expect(turn.terminalResult == .failed(.itemFailed(itemID: "b", code: "backend_timeout")))
    }

    @Test("A server error fails the turn even when every item finalized")
    func serverErrorFailsClosed() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)
        try turn.beginFinalization()
        turn.observe(envelope(1, .completed(itemID: "a", transcript: "前段")), connectionEpoch: epoch)
        turn.observe(envelope(2, .error(code: "backend_busy", triggerEventID: "x")), connectionEpoch: epoch)
        #expect(turn.terminalResult == .failed(.serverError(code: "backend_busy")))
    }

    @Test("A whitespace-only turn aggregates to empty rather than a blank Advice")
    func emptyTurn() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)
        try turn.beginFinalization()
        turn.observe(envelope(1, .completed(itemID: "a", transcript: "   ")), connectionEpoch: epoch)
        turn.observe(envelope(2, .sessionUpdated(session)), connectionEpoch: epoch)
        #expect(turn.terminalResult == .empty)
    }

    // MARK: - Hypothesis

    @Test("A hypothesis is a revocable draft and never enters the transcript")
    func hypothesisIsDraftOnly() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)
        try turn.beginFinalization()

        turn.observe(envelope(1, hypothesis(revision: 0, text: "你先观")), connectionEpoch: epoch)
        #expect(turn.latestDraftText.isEmpty, "A hypothesis must not join the item draft")
        #expect(turn.transientHypothesisText == "你先观")

        // A newer revision replaces the draft outright.
        turn.observe(envelope(2, hypothesis(revision: 1, text: "先观察再敲")), connectionEpoch: epoch)
        #expect(turn.transientHypothesisText == "先观察再敲")

        // A stale revision must not resurrect older text.
        turn.observe(envelope(3, hypothesis(revision: 0, text: "旧草稿"), eventID: "stale"), connectionEpoch: epoch)
        #expect(turn.transientHypothesisText == "先观察再敲")

        turn.observe(envelope(4, .completed(itemID: "a", transcript: "先观察再敲门。")), connectionEpoch: epoch)
        turn.observe(envelope(5, .sessionUpdated(session)), connectionEpoch: epoch)

        guard case .transcript(let final)? = turn.terminalResult else {
            Issue.record("Expected a transcript")
            return
        }
        #expect(final.text == "先观察再敲门。")
        #expect(turn.transientHypothesisText == nil, "Item text supersedes the hypothesis draft")
    }

    @Test("Alignment and diarization events cannot change the text terminal")
    func auxiliaryEventsAreInert() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)
        try turn.beginFinalization()
        turn.observe(envelope(1, .completed(itemID: "a", transcript: "先观察")), connectionEpoch: epoch)
        turn.observe(envelope(2, .auxiliary(type: "speechrail.alignment.done")), connectionEpoch: epoch)
        turn.observe(envelope(3, .auxiliary(type: "speechrail.diarization.updated")), connectionEpoch: epoch)
        #expect(turn.terminalResult == nil)
        turn.observe(envelope(4, .sessionUpdated(session)), connectionEpoch: epoch)

        guard case .transcript(let final)? = turn.terminalResult else {
            Issue.record("Expected a transcript")
            return
        }
        #expect(final.text == "先观察")
    }

    // MARK: - Envelope integrity

    @Test("A server sequence gap invalidates the whole input turn")
    func sequenceGapFailsClosed() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch, startingSequence: 40)
        try turn.beginFinalization()
        turn.observe(envelope(42, .completed(itemID: "a", transcript: "先观察")), connectionEpoch: epoch)

        #expect(turn.terminalResult == .failed(.sequenceGap(expected: 41, actual: 42)))
    }

    @Test("An unknown event type cannot be used to skip the sequence check")
    func unknownEventStillConsumesASequence() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch, startingSequence: 0)
        try turn.beginFinalization()

        turn.observe(envelope(1, .other(type: "speechrail.future.event")), connectionEpoch: epoch)
        #expect(turn.terminalResult == nil)
        turn.observe(envelope(3, .completed(itemID: "a", transcript: "先观察")), connectionEpoch: epoch)
        #expect(turn.terminalResult == .failed(.sequenceGap(expected: 2, actual: 3)))
    }

    @Test("A repeated event id with different content is a conflict")
    func duplicateEventConflict() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)
        try turn.beginFinalization()

        turn.observe(
            envelope(1, .partial(itemID: "a", delta: "先"), eventID: "dup"),
            connectionEpoch: epoch
        )
        turn.observe(
            envelope(2, .partial(itemID: "a", delta: "后"), eventID: "dup"),
            connectionEpoch: epoch
        )
        #expect(turn.terminalResult == .failed(.duplicateEventConflict(eventID: "dup")))
    }

    @Test("Events from an old connection epoch cannot contaminate the new turn")
    func oldEpochIsIgnored() throws {
        let epoch = UUID()
        let oldEpoch = UUID()
        var turn = assembler(epoch: epoch)
        try turn.beginFinalization()

        turn.observe(envelope(1, .completed(itemID: "old", transcript: "旧的")), connectionEpoch: oldEpoch)
        #expect(turn.terminalResult == nil)
        #expect(turn.latestDraftText.isEmpty)

        turn.observe(envelope(1, .completed(itemID: "new", transcript: "新的")), connectionEpoch: epoch)
        turn.observe(envelope(2, .sessionUpdated(session)), connectionEpoch: epoch)

        guard case .transcript(let final)? = turn.terminalResult else {
            Issue.record("Expected current-epoch transcript")
            return
        }
        #expect(final.text == "新的")
    }

    @Test("Cancellation never publishes a FinalTranscript")
    func cancellation() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)
        turn.cancel()
        turn.observe(envelope(1, .sessionUpdated(session)), connectionEpoch: epoch)
        #expect(turn.terminalResult == .cancelled)
    }

    @Test("Partial text is UI-only and completed text replaces it")
    func partialIsOnlyDraft() throws {
        let epoch = UUID()
        var turn = assembler(epoch: epoch)
        try turn.beginFinalization()
        turn.observe(envelope(1, .partial(itemID: "a", delta: "先观")), connectionEpoch: epoch)
        turn.observe(envelope(2, .partial(itemID: "a", delta: "察")), connectionEpoch: epoch)
        #expect(turn.latestDraftText == "先观察")
        #expect(turn.terminalResult == nil)

        turn.observe(envelope(3, .completed(itemID: "a", transcript: "先观察。")), connectionEpoch: epoch)
        turn.observe(envelope(4, .sessionUpdated(session)), connectionEpoch: epoch)
        guard case .transcript(let final)? = turn.terminalResult else {
            Issue.record("Expected final transcript")
            return
        }
        #expect(final.text == "先观察。")
    }

    // MARK: - Decoding

    @Test("Envelope decoder keeps unknown event types while preserving service sequence")
    func decoderKeepsUnknownEvents() throws {
        let json = #"{"type":"speechrail.future.event","event_id":"e1","session_id":"s1","sequence":7,"private":"ignored"}"#
        let envelope = try SpeechRailASRServerEnvelope.decode(Data(json.utf8))
        #expect(envelope.sequence == 7)
        #expect(envelope.event == .other(type: "speechrail.future.event"))
    }

    @Test("Envelope decoder accepts a schema-legal sequence of 0")
    func decoderAcceptsZeroSequence() throws {
        let json = #"{"type":"speechrail.future.event","event_id":"e1","session_id":"s1","sequence":0}"#
        let envelope = try SpeechRailASRServerEnvelope.decode(Data(json.utf8))
        #expect(envelope.sequence == 0)
    }

    @Test("Envelope decoder refuses a negative sequence")
    func decoderRejectsNegativeSequence() {
        let json = #"{"type":"speechrail.future.event","event_id":"e1","session_id":"s1","sequence":-1}"#
        #expect(throws: SpeechRailRealtimeASRFailure.invalidEnvelope) {
            try SpeechRailASRServerEnvelope.decode(Data(json.utf8))
        }
    }

    @Test("Envelope decoder reads the SpeechRail 4.0 transcription, hypothesis and error shapes")
    func decoderReadsKnownShapes() throws {
        let delta = try SpeechRailASRServerEnvelope.decode(
            Data(
                #"{"type":"conversation.item.input_audio_transcription.delta","event_id":"e1","session_id":"s1","sequence":7,"item_id":"i1","content_index":0,"delta":"你"}"#.utf8
            )
        )
        #expect(delta.event == .partial(itemID: "i1", delta: "你"))

        let completed = try SpeechRailASRServerEnvelope.decode(
            Data(
                #"{"type":"conversation.item.input_audio_transcription.completed","event_id":"e2","session_id":"s1","sequence":8,"item_id":"i1","content_index":0,"transcript":"你好"}"#.utf8
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

    @Test("Envelope decoder reads a hypothesis as a revocable draft")
    func decoderReadsHypothesis() throws {
        let json = #"{"type":"speechrail.transcription.hypothesis","event_id":"e4","session_id":"s1","sequence":10,"task_id":"t1","epoch":0,"utterance_id":"u1","revision":2,"text":"先观察","sample_span":{"start":0,"end":4800}}"#
        let envelope = try SpeechRailASRServerEnvelope.decode(Data(json.utf8))
        #expect(
            envelope.event == .hypothesis(
                SpeechRailASHypothesis(
                    taskID: "t1",
                    epoch: 0,
                    utteranceID: "u1",
                    revision: 2,
                    text: "先观察",
                    stablePrefixCodepoints: 0
                )
            )
        )
    }

    @Test("Envelope decoder refuses a hypothesis with an inverted sample span")
    func decoderRejectsInvertedSpan() {
        let json = #"{"type":"speechrail.transcription.hypothesis","event_id":"e4","session_id":"s1","sequence":10,"task_id":"t1","epoch":0,"utterance_id":"u1","revision":2,"text":"x","sample_span":{"start":100,"end":10}}"#
        #expect(throws: SpeechRailRealtimeASRFailure.invalidEnvelope) {
            try SpeechRailASRServerEnvelope.decode(Data(json.utf8))
        }
    }
}
