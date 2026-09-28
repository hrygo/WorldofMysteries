import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Story expression query contracts")
struct StoryExpressionControlTests {
    @Test("Expression request has the exact read-only wire shape")
    func requestWireShapeIsStrict() throws {
        let request = try StoryExpressionGetRequestDTO(
            sessionId: "session_1",
            turnId: "turn_1"
        )
        let encoded = try JSONEncoder().encode(request)
        let object = try JSONSerialization.jsonObject(with: encoded) as? [String: Any]
        #expect(object?.keys.sorted() == ["schema_version", "session_id", "turn_id"])
        #expect(object?["schema_version"] as? String == "1.0")

        let unknownField = """
        {
          "schema_version": "1.0",
          "session_id": "session_1",
          "turn_id": "turn_1",
          "include_hidden_context": true
        }
        """
        #expect(throws: (any Error).self) {
            _ = try JSONDecoder().decode(
                StoryExpressionGetRequestDTO.self,
                from: Data(unknownField.utf8)
            )
        }
    }

    @Test("Ready expression requires disclosed segments and preserves their types")
    func readyExpressionContainsTypedSegments() throws {
        let json = """
        {
          "schema_version": "1.0",
          "session_id": "session_1",
          "turn_id": "turn_1",
          "narrative_state": "ready",
          "segments": [
            {"type": "narration", "text": "雨停了。"},
            {"type": "character", "speaker_display_name": "伊芙琳", "text": "我明白了。"}
          ]
        }
        """
        let value = try JSONDecoder().decode(
            StoryExpressionGetResponseDTO.self,
            from: Data(json.utf8)
        )
        #expect(value.segments.map(\.type) == [.narration, .character])
        #expect(value.segments[1].speakerDisplayName == "伊芙琳")
        #expect(value.segments.map(\.text) == ["雨停了。", "我明白了。"])
    }

    @Test("Unknown response and segment fields are rejected")
    func unknownFieldsAreRejected() {
        let topLevel = """
        {
          "schema_version": "1.0",
          "session_id": "session_1",
          "turn_id": "turn_1",
          "narrative_state": "pending",
          "segments": [],
          "internal_debug": "must not cross the wire"
        }
        """
        let segmentField = """
        {
          "schema_version": "1.0",
          "session_id": "session_1",
          "turn_id": "turn_1",
          "narrative_state": "ready",
          "segments": [
            {"type": "character", "text": "你好。", "speaker_id": "secret_character_id"}
          ]
        }
        """
        #expect(throws: (any Error).self) {
            _ = try JSONDecoder().decode(
                StoryExpressionGetResponseDTO.self,
                from: Data(topLevel.utf8)
            )
        }
        #expect(throws: (any Error).self) {
            _ = try JSONDecoder().decode(
                StoryExpressionGetResponseDTO.self,
                from: Data(segmentField.utf8)
            )
        }
    }

    @Test("Narrative state and segment shape must agree")
    func stateAndSegmentsAreJointlyValidated() {
        let invalidResponses = [
            """
            {"schema_version":"1.0","session_id":"session_1","turn_id":"turn_1",
             "narrative_state":"ready","segments":[]}
            """,
            """
            {"schema_version":"1.0","session_id":"session_1","turn_id":"turn_1",
             "narrative_state":"pending","segments":[{"type":"narration","text":"等待"}]}
            """,
            """
            {"schema_version":"1.0","session_id":"session_1","turn_id":"turn_1",
             "narrative_state":"pending","segments":[],"reason":"no_failure"}
            """,
            """
            {"schema_version":"1.0","session_id":"session_1","turn_id":"turn_1",
             "narrative_state":"unavailable","segments":[]}
            """,
            """
            {"schema_version":"1.0","session_id":"session_1","turn_id":"turn_1",
             "narrative_state":"unavailable","segments":[{"type":"character","text":"你好"}],
             "reason":"expression_unavailable"}
            """,
            """
            {"schema_version":"1.0","session_id":"session_1","turn_id":"turn_1",
             "narrative_state":"ready","segments":[{"type":"narration","text":"雨停了"}],
             "reason":"unexpected"}
            """,
            """
            {"schema_version":"1.0","session_id":"session_1","turn_id":"turn_1",
             "narrative_state":"ready","segments":[
               {"type":"narration","speaker_display_name":"伊芙琳","text":"雨停了"}
             ]}
            """
        ]

        for json in invalidResponses {
            #expect(throws: (any Error).self) {
                _ = try JSONDecoder().decode(
                    StoryExpressionGetResponseDTO.self,
                    from: Data(json.utf8)
                )
            }
        }
    }

    @Test("Only unavailable expression state carries a bounded reason")
    func unavailableReasonIsStrict() throws {
        let unavailable = """
        {
          "schema_version": "1.0",
          "session_id": "session_1",
          "turn_id": "turn_1",
          "narrative_state": "unavailable",
          "segments": [],
          "reason": "expression_unavailable"
        }
        """
        let value = try JSONDecoder().decode(
            StoryExpressionGetResponseDTO.self,
            from: Data(unavailable.utf8)
        )
        #expect(value.narrativeState == .unavailable)
        #expect(value.reason == "expression_unavailable")
    }
}
