import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("World of Mysteries App Core Tests")
struct WorldOfMysteriesTests {
    @Test("IPCEnvelope serialization roundtrip")
    func testEnvelopeRoundtrip() throws {
        let envelope = IPCEnvelope(
            kind: "request",
            protocolVersion: "1.0",
            traceId: "trace_core_001",
            requestId: "req_001",
            method: "system.handshake"
        )
        let data = try JSONEncoder().encode(envelope)
        let decoded = try JSONDecoder().decode(IPCEnvelope.self, from: data)
        #expect(decoded.kind == "request")
        #expect(decoded.traceId == "trace_core_001")
        #expect(decoded.protocolVersion == "1.0")
        #expect(decoded.requestId == "req_001")
    }

    @Test("IPCEnvelope error payload roundtrip")
    func testEnvelopeErrorRoundtrip() throws {
        let errorPayload = IPCErrorPayload(code: "revision_conflict", message: "Story revision conflict", retryable: false)
        let envelope = IPCEnvelope(
            kind: "response",
            protocolVersion: "1.0",
            traceId: "trace_err_001",
            requestId: "req_err_001",
            status: "error",
            error: errorPayload
        )
        let data = try JSONEncoder().encode(envelope)
        let decoded = try JSONDecoder().decode(IPCEnvelope.self, from: data)
        #expect(decoded.status == "error")
        #expect(decoded.error?.code == "revision_conflict")
        #expect(decoded.error?.retryable == false)
    }

    @Test("IPCEnvelope event stream roundtrip")
    func testEnvelopeEventStreamRoundtrip() throws {
        let envelope = IPCEnvelope(
            kind: "event",
            protocolVersion: "1.0",
            traceId: "trace_stream_001",
            streamId: "stream_session_01",
            sequence: 42,
            event: "story.narrative_ready"
        )
        let data = try JSONEncoder().encode(envelope)
        let decoded = try JSONDecoder().decode(IPCEnvelope.self, from: data)
        #expect(decoded.kind == "event")
        #expect(decoded.streamId == "stream_session_01")
        #expect(decoded.sequence == 42)
        #expect(decoded.event == "story.narrative_ready")
    }

    @Test("CharacterDTO decoding from Golden 001 JSON")
    func testCharacterDTODecoding() throws {
        let jsonString = """
        {
          "schema_version": "1.0",
          "id": "char_evelyn_gray",
          "kind": "original",
          "identity": {
            "display_name": "伊芙琳·格雷",
            "age": 26,
            "occupation": "private_occult_consultant",
            "pathway_id": "pathway.fool",
            "sequence": 9
          },
          "canon_anchor": null,
          "core": {
            "traits": { "observant": "high" },
            "decision_style": ["observe_before_acting"],
            "values": { "protect_innocents": "high" },
            "hard_boundaries": ["avoids_revealing_beyonder_identity"]
          },
          "state": {
            "location_id": "loc_morris_clinic",
            "goals": { "immediate": "find_missing_patient" }
          },
          "revision": 27
        }
        """
        let data = jsonString.data(using: .utf8)!
        let character = try JSONDecoder().decode(CharacterDTO.self, from: data)
        #expect(character.id == "char_evelyn_gray")
        #expect(character.identity.displayName == "伊芙琳·格雷")
        #expect(character.identity.sequence == 9)
        #expect(character.revision == 27)
    }

    @Test("PlayerAdviceDTO decoding from Golden 001 Turn 1")
    func testPlayerAdviceDTODecoding() throws {
        let jsonString = """
        {
          "schema_version": "1.0",
          "id": "advice_g001_t01",
          "turn_id": "turn_g001_01",
          "raw_input": "先别问医生病人的事，我想看看他的反应。",
          "input_mode": "voice",
          "primary_intent": "observe",
          "proposed_actions": ["observe_morris"],
          "confidence": 0.97
        }
        """
        let data = jsonString.data(using: .utf8)!
        let advice = try JSONDecoder().decode(PlayerAdviceDTO.self, from: data)
        #expect(advice.id == "advice_g001_t01")
        #expect(advice.primaryIntent == "observe")
        #expect(advice.confidence == 0.97)
    }

    @Test("EngineIPCClient actor isolation")
    func testClientActor() async throws {
        let client = EngineIPCClient()
        let initialStatus = await client.isConnected
        #expect(initialStatus == false)
    }

    @Test("IPCEnvelope decodePayload generic helper")
    func testEnvelopeGenericPayloadDecoding() throws {
        let envelope = IPCEnvelope(
            kind: "request",
            protocolVersion: "1.0",
            traceId: "trace_payload_001",
            method: "story.submit_advice",
            payload: [
                "schema_version": .string("1.0"),
                "id": .string("advice_test_01"),
                "raw_input": .string("观察医生的反应"),
                "input_mode": .string("text"),
                "primary_intent": .string("observe")
            ]
        )

        let advice = try envelope.decodePayload(as: PlayerAdviceDTO.self)
        #expect(advice != nil)
        #expect(advice?.id == "advice_test_01")
        #expect(advice?.rawInput == "观察医生的反应")
        #expect(advice?.primaryIntent == "observe")
    }

    @Test("AppState never claims a live engine while the IPC transport is a scaffold")
    @MainActor
    func testAppStateLifecycle() async throws {
        let appState = AppState()
        #expect(appState.connectionState == .idle)
        #expect(appState.isEngineReady == false)
        #expect(appState.isShowingDemoData == true)

        await appState.startAndConnect()
        // 传输层仍是骨架通道（EngineIPCClient.isScaffoldOnly）：握手只是本地回显，
        // 因此状态必须停在 scaffoldPreview，界面不得显示「已就绪 · IPC 活跃」。
        #expect(appState.connectionState == .scaffoldPreview)
        #expect(appState.isEngineReady == false)
        #expect(appState.isShowingDemoData == true)
        #expect(appState.connectionError == nil)

        await appState.shutdown()
        #expect(appState.connectionState == .idle)
        #expect(appState.isEngineReady == false)
    }
}
