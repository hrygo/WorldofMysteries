import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Versioned story request journal")
struct StoryRequestJournalTests {
    private func makeJournal() throws -> (StoryRequestJournal, URL) {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("story-journal-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        return (StoryRequestJournal(root: root), root)
    }

    private func readSavedRecord(in root: URL) throws -> [String: Any] {
        let data = try Data(
            contentsOf: fileURL(in: root)
        )
        return try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    private func fileURL(in root: URL) -> URL {
        root.appendingPathComponent(StoryRequestJournal.fileName, isDirectory: false)
    }

    @Test("A legacy journal reads as v1 text advice and upgrades on its next save")
    func legacyJournalUpgradesOnSave() throws {
        let (journal, root) = try makeJournal()
        defer { try? FileManager.default.removeItem(at: root) }
        let legacy = """
        {
          "phase": "submitting",
          "scenarioId": "golden_001",
          "sessionId": "session_1",
          "inputTurnId": "input_turn_1",
          "rawInput": "先看看医生的反应。",
          "storyRevision": 0,
          "storeRevision": 1
        }
        """
        try Data(legacy.utf8).write(to: fileURL(in: root))

        let loaded = try journal.load()
        let record = try #require(loaded)
        #expect(record.recordVersion == 1)
        #expect(record.inputMode == .text)
        #expect(record.submissionMethod == .storyAdviceSubmit)
        #expect(record.frozenSubmission?.rawInput == "先看看医生的反应。")

        try journal.save(record)
        let saved = try readSavedRecord(in: root)
        #expect(saved["recordVersion"] as? Int == 2)
        #expect(saved["inputMode"] as? String == "text")
        #expect(saved["submissionMethod"] as? String == "story.advice.submit")
    }

    @Test("A v2 voice record roundtrips its mode, method, identity and raw transcript")
    func voiceRecordRoundtripsWithoutChangingFrozenInput() throws {
        let (journal, root) = try makeJournal()
        defer { try? FileManager.default.removeItem(at: root) }
        let voiceRecord = """
        {
          "recordVersion": 2,
          "inputMode": "voice",
          "submissionMethod": "story.turn.submit",
          "phase": "submitting",
          "scenarioId": "golden_001",
          "sessionId": "session_1",
          "inputTurnId": "input_turn_1",
          "rawInput": "  原样保留的 ASR 转写  ",
          "storyRevision": 0,
          "storeRevision": 1
        }
        """
        try Data(voiceRecord.utf8).write(to: fileURL(in: root))

        let loaded = try journal.load()
        let record = try #require(loaded)
        #expect(record.recordVersion == 2)
        #expect(record.inputMode == .voice)
        #expect(record.submissionMethod == .storyTurnSubmit)
        #expect(record.frozenSubmission?.rawInput == "  原样保留的 ASR 转写  ")

        try journal.save(record)
        let saved = try readSavedRecord(in: root)
        #expect(saved["recordVersion"] as? Int == 2)
        #expect(saved["inputMode"] as? String == "voice")
        #expect(saved["submissionMethod"] as? String == "story.turn.submit")
        #expect(saved["rawInput"] as? String == "  原样保留的 ASR 转写  ")
    }

    @Test("Corrupt and unknown-version journals throw instead of looking absent")
    func corruptAndUnknownVersionJournalsFailClosed() throws {
        let (journal, root) = try makeJournal()
        defer { try? FileManager.default.removeItem(at: root) }

        try Data("{".utf8).write(to: fileURL(in: root))
        #expect(throws: (any Error).self) {
            _ = try journal.load()
        }

        let unknown = """
        {
          "recordVersion": 99,
          "inputMode": "text",
          "submissionMethod": "story.advice.submit",
          "phase": "submitting",
          "scenarioId": "golden_001",
          "sessionId": "session_1",
          "inputTurnId": "input_turn_1",
          "rawInput": "先看看医生的反应。",
          "storyRevision": 0,
          "storeRevision": 1
        }
        """
        try Data(unknown.utf8).write(to: fileURL(in: root))
        #expect(throws: (any Error).self) {
            _ = try journal.load()
        }
    }

    @Test("A v2 record cannot pair voice input with the text-only advice method")
    func illegalModeAndMethodCombinationFailsClosed() throws {
        let (journal, root) = try makeJournal()
        defer { try? FileManager.default.removeItem(at: root) }
        let invalid = """
        {
          "recordVersion": 2,
          "inputMode": "voice",
          "submissionMethod": "story.advice.submit",
          "phase": "submitting",
          "scenarioId": "golden_001",
          "sessionId": "session_1",
          "inputTurnId": "input_turn_1",
          "rawInput": "转写内容",
          "storyRevision": 0,
          "storeRevision": 1
        }
        """
        try Data(invalid.utf8).write(to: fileURL(in: root))

        #expect(throws: (any Error).self) {
            _ = try journal.load()
        }
    }
}
