import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Story post-COMMIT work contracts")
struct StoryPostCommitControlTests {
    @Test("Public state and work kind literals exactly match the wire schema")
    func enumLiteralsMatchSchema() throws {
        let settlementValues = try schemaEnum(
            "story_post_commit_control.schema.json",
            definition: "settlement_state"
        )
        let narrativeValues = try schemaEnum(
            "story_post_commit_control.schema.json",
            definition: "narrative_state"
        )
        let audioValues = try schemaEnum(
            "story_post_commit_control.schema.json",
            definition: "audio_state"
        )
        let workKindValues = try schemaEnum(
            "story_post_commit_control.schema.json",
            definition: "work_kind"
        )
        #expect(
            StoryTurnSettlementState.allCases.map(\.rawValue) == settlementValues
        )
        #expect(
            StoryTurnNarrativeState.allCases.map(\.rawValue) == narrativeValues
        )
        #expect(
            StoryTurnAudioState.allCases.map(\.rawValue) == audioValues
        )
        #expect(
            StoryTurnWorkKind.allCases.map(\.rawValue) == workKindValues
        )
    }

    @Test("Work get request and retry request preserve the exact wire keys")
    func requestWireShapesAreStrict() throws {
        let get = try StoryTurnWorkGetRequestDTO(sessionId: "session_1", turnId: "turn_1")
        let getObject = try jsonObject(JSONEncoder().encode(get))
        #expect(getObject.keys.sorted() == ["schema_version", "session_id", "turn_id"])

        let retry = try StoryTurnWorkRetryRequestDTO(
            sessionId: "session_1",
            turnId: "turn_1",
            kind: .audioPrepare,
            retryRequestId: "retry_1"
        )
        let retryObject = try jsonObject(JSONEncoder().encode(retry))
        #expect(
            retryObject.keys.sorted()
                == ["kind", "retry_request_id", "schema_version", "session_id", "turn_id"]
        )
        #expect(retryObject["kind"] as? String == "audio_prepare")
    }

    @Test("Ready narrative requires segments and forbids a narrative reason")
    func readyNarrativeConditionalIsValidated() throws {
        let valid = try workGetData(narrativeState: "ready", narrativeSegments: narration)
        #expect(throws: Never.self) {
            try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: valid)
        }

        let emptySegments = try workGetData(narrativeState: "ready", narrativeSegments: [])
        #expect(throws: (any Error).self) {
            try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: emptySegments)
        }

        let unexpectedReason = try workGetData(
            narrativeState: "ready",
            narrativeSegments: narration,
            narrativeReason: "unexpected_reason"
        )
        #expect(throws: (any Error).self) {
            try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: unexpectedReason)
        }
    }

    @Test("Pending, running, and blocked narrative conditions match the schema")
    func nonReadyNarrativeConditionalsAreValidated() throws {
        for state in ["pending", "running"] {
            let valid = try workGetData(narrativeState: state, narrativeSegments: [])
            #expect(throws: Never.self) {
                try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: valid)
            }

            let withSegments = try workGetData(narrativeState: state, narrativeSegments: narration)
            #expect(throws: (any Error).self) {
                try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: withSegments)
            }

            let withReason = try workGetData(
                narrativeState: state,
                narrativeSegments: [],
                narrativeReason: "unexpected_reason"
            )
            #expect(throws: (any Error).self) {
                try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: withReason)
            }
        }

        let blocked = try workGetData(
            narrativeState: "blocked",
            narrativeSegments: [],
            narrativeReason: "narrative_blocked"
        )
        #expect(throws: Never.self) {
            try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: blocked)
        }

        let blockedWithoutReason = try workGetData(
            narrativeState: "blocked",
            narrativeSegments: []
        )
        #expect(throws: (any Error).self) {
            try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: blockedWithoutReason)
        }

        let blockedWithSegments = try workGetData(
            narrativeState: "blocked",
            narrativeSegments: narration,
            narrativeReason: "narrative_blocked"
        )
        #expect(throws: (any Error).self) {
            try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: blockedWithSegments)
        }
    }

    @Test("Settlement reason presence follows each public state")
    func settlementConditionalsAreValidated() throws {
        let cases: [(String, String?)] = [
            ("not_required", nil),
            ("pending", nil),
            ("running", nil),
            ("blocked", "settlement_blocked"),
            ("succeeded", nil),
        ]

        for (state, reason) in cases {
            let valid = try workGetData(settlementState: state, settlementReason: reason)
            #expect(throws: Never.self) {
                try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: valid)
            }

            var invalidReason = reason
            if state == "blocked" {
                invalidReason = nil
            } else {
                invalidReason = "unexpected_reason"
            }
            let invalid = try workGetData(
                settlementState: state,
                settlementReason: invalidReason
            )
            #expect(throws: (any Error).self) {
                try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: invalid)
            }
        }
    }

    @Test("Unavailable audio requires a reason and excludes delivery")
    func unavailableAudioConditionalIsValidated() throws {
        let valid = try workGetData(audioState: "unavailable", audioReason: "handoff_expired")
        #expect(throws: Never.self) {
            try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: valid)
        }

        let missingReason = try workGetData(audioState: "unavailable")
        #expect(throws: (any Error).self) {
            try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: missingReason)
        }

        let withDelivery = try workGetData(
            audioState: "unavailable",
            audioReason: "handoff_expired",
            delivery: readyDelivery
        )
        #expect(throws: (any Error).self) {
            try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: withDelivery)
        }
    }

    @Test("Ready audio requires a ready delivery and excludes an audio reason")
    func readyAudioConditionalIsValidated() throws {
        let valid = try workGetData(audioState: "ready", delivery: readyDelivery)
        let response = try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: valid)
        #expect(response.delivery?.state == .ready)

        let missingDelivery = try workGetData(audioState: "ready")
        #expect(throws: (any Error).self) {
            try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: missingDelivery)
        }

        var unavailableDelivery = readyDelivery
        unavailableDelivery["state"] = "unavailable"
        unavailableDelivery["reason"] = "handoff_expired"
        unavailableDelivery.removeValue(forKey: "narrative_block_id")
        unavailableDelivery.removeValue(forKey: "speech_unit_id")
        unavailableDelivery.removeValue(forKey: "spoken_text")
        unavailableDelivery.removeValue(forKey: "render_recipe")
        let invalidDelivery = try workGetData(
            audioState: "ready",
            delivery: unavailableDelivery
        )
        #expect(throws: (any Error).self) {
            try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: invalidDelivery)
        }

        let withReason = try workGetData(
            audioState: "ready",
            audioReason: "unexpected_reason",
            delivery: readyDelivery
        )
        #expect(throws: (any Error).self) {
            try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: withReason)
        }
    }

    @Test("Pending and running audio exclude reasons and delivery")
    func pendingAudioConditionalsAreValidated() throws {
        for state in ["pending", "running"] {
            let valid = try workGetData(audioState: state)
            #expect(throws: Never.self) {
                try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: valid)
            }

            let withReason = try workGetData(audioState: state, audioReason: "unexpected_reason")
            #expect(throws: (any Error).self) {
                try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: withReason)
            }

            let withDelivery = try workGetData(audioState: state, delivery: readyDelivery)
            #expect(throws: (any Error).self) {
                try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: withDelivery)
            }
        }
    }

    @Test("Settlement, narrative, and audio states remain independent")
    func postCommitStatesAreIndependent() throws {
        let data = try workGetData(
            settlementState: "succeeded",
            narrativeState: "ready",
            narrativeSegments: narration,
            audioState: "unavailable",
            audioReason: "handoff_expired"
        )
        let response = try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: data)
        #expect(response.settlementState == .succeeded)
        #expect(response.narrativeState == .ready)
        #expect(response.audioState == .unavailable)
    }

    @Test("Only stable public reason codes are accepted")
    func reasonRejectsFreeFormInternalErrors() throws {
        let stableCode = try workGetData(
            audioState: "unavailable",
            audioReason: "handoff_expired"
        )
        #expect(throws: Never.self) {
            try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: stableCode)
        }

        for reason in ["RuntimeError: private failure", "ValueError", "error at /private/path"] {
            let internalError = try workGetData(
                audioState: "unavailable",
                audioReason: reason
            )
            #expect(throws: (any Error).self) {
                try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: internalError)
            }
        }
    }

    @Test("Lease, owner, generation, and unknown identity fields are rejected")
    func internalIdentityFieldsAreRejected() throws {
        for key in ["lease_id", "owner", "generation", "internal_error"] {
            var object = baseWorkGetObject()
            object[key] = "must_not_cross_the_wire"
            let data = try JSONSerialization.data(withJSONObject: object)
            #expect(throws: (any Error).self) {
                try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: data)
            }
        }

        var delivery = readyDelivery
        delivery["owner"] = "internal-owner"
        let nestedIdentity = try workGetData(audioState: "ready", delivery: delivery)
        #expect(throws: (any Error).self) {
            try JSONDecoder().decode(StoryTurnWorkGetResponseDTO.self, from: nestedIdentity)
        }
    }

    @Test("Retry response is correlated and accepts only the schema's acknowledgement")
    func retryResponseIsStrictAndCorrelated() throws {
        let json = """
        {
          "schema_version": "1.0",
          "session_id": "session_1",
          "turn_id": "turn_1",
          "kind": "audio_prepare",
          "retry_request_id": "retry_1",
          "accepted": true,
          "replayed": false
        }
        """
        let response = try JSONDecoder().decode(
            StoryTurnWorkRetryResponseDTO.self,
            from: Data(json.utf8)
        )
        #expect(response.accepted)
        #expect(response.replayed == false)

        let notAccepted = json.replacingOccurrences(of: "\"accepted\": true", with: "\"accepted\": false")
        #expect(throws: (any Error).self) {
            try JSONDecoder().decode(
                StoryTurnWorkRetryResponseDTO.self,
                from: Data(notAccepted.utf8)
            )
        }

        let extraField = json.replacingOccurrences(
            of: "\"replayed\": false",
            with: "\"replayed\": false, \"lease_id\": \"private\""
        )
        #expect(throws: (any Error).self) {
            try JSONDecoder().decode(
                StoryTurnWorkRetryResponseDTO.self,
                from: Data(extraField.utf8)
            )
        }
    }

    @Test("Post-COMMIT method capabilities exactly match the engine IPC schema")
    func methodCapabilitiesMatchSchema() throws {
        let capabilities = try schemaEnum(
            "engine_ipc.schema.json",
            definition: "story_post_commit_method_capability"
        )
        #expect(
            StoryPostCommitMethodCapability.allCases.map(\.rawValue) == capabilities
        )
    }

    private var narration: [[String: Any]] {
        [["type": "narration", "text": "雨停了。"]]
    }

    private var readyDelivery: [String: Any] {
        [
            "state": "ready",
            "narrative_block_id": "block_1",
            "speech_unit_id": "speech_1",
            "spoken_text": "雨停了。",
            "render_recipe": [
                "speech_unit_id": "speech_1",
                "turn_id": "turn_1",
                "story_revision": 1,
                "narrative_block_id": "block_1",
                "segment_index": 0,
                "performance_plan_id": "performance_1",
                "spoken_text": "雨停了。",
                "voice_id": "voice_1",
                "expected_voice_revision": "voice_revision_1",
                "expected_model_revision": "model_revision_1",
                "speed": 1.0,
                "language": "zh-CN",
            ],
        ]
    }

    private func baseWorkGetObject() -> [String: Any] {
        [
            "schema_version": "1.0",
            "session_id": "session_1",
            "turn_id": "turn_1",
            "settlement_state": "succeeded",
            "narrative_state": "pending",
            "narrative_segments": [],
            "audio_state": "pending",
        ]
    }

    private func workGetData(
        settlementState: String = "succeeded",
        settlementReason: String? = nil,
        narrativeState: String = "pending",
        narrativeSegments: [[String: Any]] = [],
        narrativeReason: String? = nil,
        audioState: String = "pending",
        audioReason: String? = nil,
        delivery: [String: Any]? = nil
    ) throws -> Data {
        var object: [String: Any] = [
            "schema_version": "1.0",
            "session_id": "session_1",
            "turn_id": "turn_1",
            "settlement_state": settlementState,
            "narrative_state": narrativeState,
            "narrative_segments": narrativeSegments,
            "audio_state": audioState,
        ]
        if let settlementReason { object["settlement_reason"] = settlementReason }
        if let narrativeReason { object["narrative_reason"] = narrativeReason }
        if let audioReason { object["audio_reason"] = audioReason }
        if let delivery { object["delivery"] = delivery }
        return try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    }

    private func schemaEnum(_ filename: String, definition: String) throws -> [String] {
        let url = repositoryRoot.appendingPathComponent("contracts/protocol/\(filename)")
        let object = try JSONSerialization.jsonObject(with: Data(contentsOf: url))
        guard
            let schema = object as? [String: Any],
            let definitions = schema["$defs"] as? [String: Any],
            let typeDefinition = definitions[definition] as? [String: Any],
            let values = typeDefinition["enum"] as? [String]
        else {
            throw TestFixtureError.invalidSchema(filename, definition)
        }
        return values
    }

    private func jsonObject(_ data: Data) throws -> [String: Any] {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw TestFixtureError.invalidObject
        }
        return object
    }

    private var repositoryRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }
}

private enum TestFixtureError: Error {
    case invalidSchema(String, String)
    case invalidObject
}
