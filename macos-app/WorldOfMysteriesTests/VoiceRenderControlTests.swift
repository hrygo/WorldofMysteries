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

/// The evidence pins let a render be attributed to the listening review that
/// authorised it. The App never chooses them — it copies them off the sealed
/// recipe and refuses anything it cannot forward whole.
@Suite("Sealed voice render evidence pins")
struct VoiceRenderEvidencePinTests {
    // Built on demand rather than stored: `[String: Any]` is not Sendable, and
    // a stored `static let` of it fails Swift 6 strict concurrency.
    private static var pins: [String: Any] {
        [
            "evidence_id": "ev_klein_1",
            "evidence_digest": String(repeating: "d", count: 64),
            "expected_model_artifact_revision": "qwen3-tts-2026-09-29",
            "expected_model_catalog_revision": String(repeating: "b", count: 40),
        ]
    }

    private static func recipeFields(
        includingPins pins: [String: Any]? = VoiceRenderEvidencePinTests.pins
    ) -> [String: Any] {
        var fields: [String: Any] = [
            "speech_unit_id": "speech-aaaa",
            "turn_id": "turn-1",
            "story_revision": 7,
            "narrative_block_id": "narrative-1",
            "segment_index": 0,
            "performance_plan_id": "perf-dddd",
            "spoken_text": "克莱恩没有开门。",
            "voice_id": "klein-approved",
            "expected_voice_revision": "voice-bbbb",
            "expected_model_revision": "model-rev-1",
            "speed": 1.0,
            "language": "zh",
        ]
        fields.merge(pins ?? [:]) { _, new in new }
        return fields
    }

    private static func decode(_ fields: [String: Any]) throws -> VoiceRenderRecipeDTO {
        try JSONDecoder().decode(
            VoiceRenderRecipeDTO.self,
            from: try JSONSerialization.data(withJSONObject: fields))
    }

    @Test("A pinned recipe is forwarded as 2.0 with every pin intact")
    func pinnedRecipeGoesOutAsV2() throws {
        let recipe = try Self.decode(Self.recipeFields())
        #expect(recipe.evidenceId == "ev_klein_1")
        #expect(recipe.expectedModelArtifactRevision == "qwen3-tts-2026-09-29")

        let request = VoiceRenderControlRequestDTO(
            recipe: recipe, mediaStreamId: "media-001", generation: 7)
        #expect(request.schemaVersion == "2.0")
        #expect(request.evidenceId == "ev_klein_1")
        #expect(request.evidenceDigest == String(repeating: "d", count: 64))
        #expect(request.expectedModelCatalogRevision == String(repeating: "b", count: 40))

        let encoded = try JSONSerialization.jsonObject(
            with: try JSONEncoder().encode(request)) as? [String: Any]
        #expect(encoded?["schema_version"] as? String == "2.0")
        #expect(encoded?["evidence_id"] as? String == "ev_klein_1")
    }

    @Test("A recipe missing any single pin is refused rather than forwarded")
    func partialPinsAreRefused() throws {
        for omitted in VoiceRenderRecipeDTO.evidencePinKeys {
            var kept = Self.pins
            kept[omitted] = nil
            #expect(throws: (any Error).self, "\(omitted) may not be dropped alone") {
                try Self.decode(Self.recipeFields(includingPins: kept.isEmpty ? nil : kept))
            }
        }
    }

    @Test("A pre-evidence recipe still replays as 1.0 and leaks no pin keys")
    func preEvidenceRecipeStaysOnV1() throws {
        let recipe = try Self.decode(Self.recipeFields(includingPins: nil))
        #expect(recipe.evidenceId == nil)

        let request = VoiceRenderControlRequestDTO(
            recipe: recipe, mediaStreamId: "media-001", generation: 7)
        #expect(request.schemaVersion == "1.0")

        // The 1.0 contract forbids additional properties, so an absent pin must
        // be absent on the wire rather than serialised as null.
        let encoded = try JSONSerialization.jsonObject(
            with: try JSONEncoder().encode(request)) as? [String: Any]
        for pin in VoiceRenderRecipeDTO.evidencePinKeys {
            #expect(encoded?[pin] == nil)
        }
    }
}
