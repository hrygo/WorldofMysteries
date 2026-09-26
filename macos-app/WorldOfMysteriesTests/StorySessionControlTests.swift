import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Trusted first-turn story control contracts")
struct StorySessionControlTests {
    struct Corpus: Decodable {
        let supportedAdvice: String
        let cases: [Case]

        enum CodingKeys: String, CodingKey {
            case supportedAdvice = "supported_advice"
            case cases
        }
    }

    struct Case: Decodable {
        let id: String
        let shape: String
        let valid: Bool
        let value: AnyCodableValue
    }

    static func corpus() throws -> Corpus {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let url = root.appendingPathComponent("contracts/fixtures/ipc/story_session_control.json")
        return try JSONDecoder().decode(Corpus.self, from: Data(contentsOf: url))
    }

    static func decode(shape: String, value: AnyCodableValue) throws {
        let data = try JSONEncoder().encode(value)
        let decoder = JSONDecoder()
        switch shape {
        case "entry_get_request":
            _ = try decoder.decode(StoryEntryRequestDTO.self, from: data)
        case "session_open_request":
            _ = try decoder.decode(StorySessionOpenRequestDTO.self, from: data)
        case "session_get_request":
            _ = try decoder.decode(StorySessionGetRequestDTO.self, from: data)
        case "advice_submit_request":
            _ = try decoder.decode(StoryAdviceSubmitRequestDTO.self, from: data)
        case "advice_get_request":
            _ = try decoder.decode(StoryAdviceGetRequestDTO.self, from: data)
        case "entry_get_response":
            _ = try decoder.decode(StoryEntryViewDTO.self, from: data)
        case "session_open_response":
            _ = try decoder.decode(StoryOpenViewDTO.self, from: data)
        case "session_get_response":
            _ = try decoder.decode(StorySessionGetViewDTO.self, from: data)
        case "advice_submit_response":
            _ = try decoder.decode(StoryAdviceSubmitViewDTO.self, from: data)
        case "advice_get_response":
            _ = try decoder.decode(StoryAdviceGetViewDTO.self, from: data)
        case "public_story_session_view":
            _ = try decoder.decode(StoryPublicViewDTO.self, from: data)
        case "receipt":
            _ = try decoder.decode(StoryReceiptViewDTO.self, from: data)
        default:
            throw StoryControlError.invalidPayload
        }
    }

    @Test("Shared fixture is accepted and rejected identically by the Swift DTOs")
    func sharedFixtureParity() throws {
        let corpus = try Self.corpus()
        #expect(!corpus.supportedAdvice.isEmpty)
        #expect(corpus.cases.count >= 20)
        for sample in corpus.cases {
            do {
                try Self.decode(shape: sample.shape, value: sample.value)
                #expect(sample.valid, "Unexpected acceptance: \(sample.id)")
            } catch {
                #expect(!sample.valid, "Unexpected rejection: \(sample.id)")
            }
        }
    }

    @Test("Round-tripping a valid view keeps every allowlisted field")
    func roundTripPreservesAllowlistedView() throws {
        let corpus = try Self.corpus()
        guard let sample = corpus.cases.first(where: { $0.id == "session_get_response_after_commit_valid" })
        else {
            Issue.record("fixture case missing")
            return
        }
        let data = try JSONEncoder().encode(sample.value)
        let view = try JSONDecoder().decode(StorySessionGetViewDTO.self, from: data)
        #expect(view.session.turn == 1)
        #expect(view.session.storyRevision == 1)
        #expect(view.session.canSubmit == false)
        #expect(view.session.discoveredClues.map(\.id) == ["clue_doctor_pause"])
        #expect(view.session.discoveredClues.first?.displayName == "医生的停顿")
        #expect(view.session.lastCommittedTurnId == "turn_first_001")

        let encoded = try JSONEncoder().encode(view)
        let decoded = try JSONDecoder().decode(StorySessionGetViewDTO.self, from: encoded)
        #expect(decoded == view)
        let text = String(decoding: encoded, as: UTF8.self)
        #expect(!text.contains("secret_"))
        #expect(!text.contains("hidden_truth"))
    }

    @Test("Identity mismatches are rejected before any service call")
    func rejectsIdentityMismatch() throws {
        let receiptMismatch = """
        {
          "schema_version": "1.0",
          "receipt": {
            "input_turn_id": "input_turn_1",
            "session_id": "session_b",
            "turn_id": "turn_0001",
            "status": "committed",
            "committed_store_revision": 2,
            "committed_story_revision": 1
          },
          "session": {
            "schema_version": "1.0",
            "scenario_id": "golden_001",
            "session_id": "session_a",
            "mode": "golden_deterministic",
            "status": "active",
            "story_revision": 1,
            "turn": 1,
            "observed_store_revision": 2,
            "world_time": "1899-03-01T08:00:00Z",
            "protagonist": {"id": "char_evelyn_gray", "display_name": "伊芙琳·格雷"},
            "scene": {"id": "consultation_room", "location_id": "harvey_clinic", "display_name": "哈维诊所 · 诊室"},
            "discovered_clues": [],
            "can_submit": false
          },
          "replayed": false
        }
        """
        #expect(throws: (any Error).self) {
            _ = try JSONDecoder().decode(
                StoryAdviceSubmitViewDTO.self, from: Data(receiptMismatch.utf8))
        }
    }

    @Test("Request DTOs never emit nulls or unknown fields")
    func requestsEncodeStrictShapes() throws {
        let request = try StorySessionOpenRequestDTO(
            openRequestId: "open_first_001", expectedStoreRevision: 0)
        let data = try JSONEncoder().encode(request)
        let object = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        #expect(object?.keys.sorted() == ["expected_store_revision", "open_request_id",
                                          "scenario_id", "schema_version"])
        #expect(throws: (any Error).self) {
            _ = try StorySessionOpenRequestDTO(
                openRequestId: "   ", expectedStoreRevision: 0)
        }
        #expect(throws: (any Error).self) {
            _ = try StoryAdviceSubmitRequestDTO(
                sessionId: "session_a", inputTurnId: "input_turn_1", rawInput: "",
                expectedStoryRevision: 0, expectedStoreRevision: 1)
        }
    }
}
