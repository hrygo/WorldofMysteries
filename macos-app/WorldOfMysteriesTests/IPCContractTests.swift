import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Strict IPC contract corpus")
struct IPCContractTests {
    @Test("Schema corpus accepted and rejected identically by Swift")
    func testCanonicalCorpus() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let cases = try ["envelopes", "numeric_wire"].flatMap { name in
            let url = root.appendingPathComponent("contracts/fixtures/ipc/\(name).json")
            return try JSONDecoder().decode([IPCFixtureCase].self, from: Data(contentsOf: url))
        }
        #expect(cases.count >= 80)
        for sample in cases {
            let bytes = try sample.rawWire.map { Data($0.utf8) } ?? JSONEncoder().encode(sample.envelope)
            do {
                let envelope = try JSONDecoder().decode(IPCEnvelope.self, from: bytes)
                #expect(sample.valid, "Unexpected acceptance: \(sample.id)")
                let encoded = try JSONEncoder().encode(envelope)
                let decoded = try JSONDecoder().decode(IPCEnvelope.self, from: encoded)
                #expect(decoded.kind == envelope.kind)
                #expect(decoded.traceId == envelope.traceId)
            } catch {
                #expect(!sample.valid, "Unexpected rejection: \(sample.id)")
            }
        }
    }

    @Test("Empty business payload stays absent and malformed nonempty payload still fails")
    func testMissingBusinessPayload() throws {
        struct BusinessResult: Decodable { let requestID: String }
        let empty = IPCEnvelope(kind: "response", traceId: "trace", requestId: "req", status: "ok")
        #expect(try empty.decodePayload(as: BusinessResult.self) == nil)
        let malformed = IPCEnvelope(kind: "response", traceId: "trace", requestId: "req",
                                    status: "ok", payload: ["wrongKey": .string("value")])
        #expect(throws: (any Error).self) { try malformed.decodePayload(as: BusinessResult.self) }
    }

    @Test("A constructed invalid envelope cannot be serialized")
    func testInvalidConstructedEnvelope() {
        let invalid = IPCEnvelope(kind: "request", traceId: "trace", method: "system.health")
        #expect(throws: (any Error).self) { try JSONEncoder().encode(invalid) }
    }
}

private struct IPCFixtureCase: Decodable {
    let id: String
    let valid: Bool
    let envelope: AnyCodableValue
    let rawWire: String?
}

/// `voice_render_recipe` declares `expected_model_revision` and `language` as
/// required keys whose value may be JSON `null`. The Swift DTO models both as
/// optionals, so a strict "no null anywhere" key check makes those two branches
/// unreachable and rejects any turn whose sealed unit pins no model revision
/// or no language.
@Suite("Voice render recipe nullable wire fields")
struct VoiceRenderRecipeWireTests {
    private static let canonicalKeys: Set<String> = [
        "speech_unit_id", "turn_id", "story_revision", "narrative_block_id",
        "segment_index", "performance_plan_id", "spoken_text", "voice_id",
        "expected_voice_revision", "expected_model_revision", "speed", "language",
    ]

    private static func recipeFields(
        modelRevision: String? = "model-rev-1",
        language: String? = "zh-CN"
    ) -> [String: Any] {
        [
            "speech_unit_id": "speech-aaaa",
            "turn_id": "turn-1",
            "story_revision": 7,
            "narrative_block_id": "narrative-1",
            "segment_index": 0,
            "performance_plan_id": "perf-dddd",
            "spoken_text": "克莱恩没有开门。",
            "voice_id": "klein-approved",
            "expected_voice_revision": "voice-bbbb",
            "expected_model_revision": modelRevision ?? NSNull(),
            "speed": 1.0,
            "language": language ?? NSNull(),
        ]
    }

    private static func decode(_ fields: [String: Any]) throws -> VoiceRenderRecipeDTO {
        try JSONDecoder().decode(
            VoiceRenderRecipeDTO.self,
            from: try JSONSerialization.data(withJSONObject: fields))
    }

    @Test("Both nullable fields decode as nil when the contract sends null")
    func testNullableFieldsAcceptJSONNull() throws {
        let recipe = try Self.decode(Self.recipeFields(modelRevision: nil, language: nil))
        #expect(recipe.expectedModelRevision == nil)
        #expect(recipe.language == nil)
        #expect(recipe.turnId == "turn-1")
    }

    @Test("Present string values still decode unchanged")
    func testNullableFieldsKeepStringValues() throws {
        let recipe = try Self.decode(Self.recipeFields())
        #expect(recipe.expectedModelRevision == "model-rev-1")
        #expect(recipe.language == "zh-CN")
    }

    @Test("The two nullable fields are independent of each other")
    func testNullableFieldsAreIndependent() throws {
        let withoutModel = try Self.decode(Self.recipeFields(modelRevision: nil))
        #expect(withoutModel.expectedModelRevision == nil)
        #expect(withoutModel.language == "zh-CN")

        let withoutLanguage = try Self.decode(Self.recipeFields(language: nil))
        #expect(withoutLanguage.expectedModelRevision == "model-rev-1")
        #expect(withoutLanguage.language == nil)
    }

    @Test("A missing required key is still rejected: null is not absence")
    func testMissingRequiredKeyStillRejected() {
        for field in ["expected_model_revision", "language"] {
            var fields = Self.recipeFields()
            fields.removeValue(forKey: field)
            #expect(throws: (any Error).self, "omitting \(field) must stay rejected") {
                try Self.decode(fields)
            }
        }
    }

    @Test("A null in any other field is still rejected")
    func testOtherNullFieldsStillRejected() {
        for field in ["voice_id", "expected_voice_revision", "spoken_text", "turn_id"] {
            var fields = Self.recipeFields()
            fields[field] = NSNull()
            #expect(throws: (any Error).self, "null \(field) must stay rejected") {
                try Self.decode(fields)
            }
        }
    }

    @Test("The Swift key set stays pinned to the canonical schema")
    func testKeySetMatchesCanonicalSchema() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let url = root.appendingPathComponent(
            "contracts/protocol/story_session_control.schema.json")
        let schema = try JSONSerialization.jsonObject(
            with: Data(contentsOf: url)) as? [String: Any] ?? [:]
        let recipe = ((schema["$defs"] as? [String: Any])?["voice_render_recipe"]
            as? [String: Any]) ?? [:]
        let required = Set((recipe["required"] as? [String]) ?? [])
        #expect(required == Self.canonicalKeys)
        let properties = (recipe["properties"] as? [String: Any]) ?? [:]
        for field in ["expected_model_revision", "language"] {
            let type = (properties[field] as? [String: Any])?["type"]
            #expect((type as? [String])?.contains("null") == true,
                    "\(field) must remain nullable in the canonical schema")
        }
    }
}
