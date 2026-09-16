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
            method: "system.handshake"
        )
        let data = try JSONEncoder().encode(envelope)
        let decoded = try JSONDecoder().decode(IPCEnvelope.self, from: data)
        #expect(decoded.kind == "request")
        #expect(decoded.traceId == "trace_core_001")
        #expect(decoded.protocolVersion == "1.0")
    }

    @Test("EngineIPCClient actor isolation")
    func testClientActor() async throws {
        let client = EngineIPCClient()
        let initialStatus = await client.isConnected
        #expect(initialStatus == false)
    }
}
