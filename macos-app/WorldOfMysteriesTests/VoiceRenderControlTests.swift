import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Sealed voice render control DTO")
struct VoiceRenderControlTests {
    @Test("Request preserves committed speech and provider pins")
    func requestRoundTrip() throws {
        let data = Data(#"""
        {
          "schema_version":"1.0",
          "speech_unit_id":"speech_001",
          "turn_id":"turn_001",
          "story_revision":42,
          "narrative_block_id":"narrative_001",
          "segment_index":0,
          "performance_plan_id":"perf_001",
          "spoken_text":"雾中的脚步声停在了门外。",
          "voice_id":"narrator_mystic",
          "expected_voice_revision":"vr_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "expected_model_revision":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
          "media_stream_id":"media_001",
          "generation":7,
          "speed":1.0,
          "language":"zh"
        }
        """#.utf8)

        let decoded = try JSONDecoder().decode(VoiceRenderControlRequestDTO.self, from: data)
        #expect(decoded.schemaVersion == "1.0")
        #expect(decoded.speechUnitId == "speech_001")
        #expect(decoded.turnId == "turn_001")
        #expect(decoded.storyRevision == 42)
        #expect(decoded.performancePlanId == "perf_001")
        #expect(decoded.spokenText == "雾中的脚步声停在了门外。")
        #expect(decoded.expectedVoiceRevision.hasPrefix("vr_"))
        #expect(decoded.expectedModelRevision?.count == 40)
        #expect(decoded.mediaStreamId == "media_001")
        #expect(decoded.generation == 7)

        let encoded = try JSONEncoder().encode(decoded)
        #expect(try JSONDecoder().decode(VoiceRenderControlRequestDTO.self, from: encoded) == decoded)
    }

    @Test("Accepted payload keeps render and media generation correlated")
    func acceptedRoundTrip() throws {
        let data = Data(#"""
        {
          "schema_version":"1.0",
          "render_id":"render_001",
          "speech_unit_id":"speech_001",
          "media_stream_id":"media_001",
          "generation":7,
          "state":"accepted"
        }
        """#.utf8)

        let decoded = try JSONDecoder().decode(VoiceRenderAcceptedDTO.self, from: data)
        #expect(decoded.renderId == "render_001")
        #expect(decoded.speechUnitId == "speech_001")
        #expect(decoded.mediaStreamId == "media_001")
        #expect(decoded.generation == 7)
        #expect(decoded.state == "accepted")
    }
}
