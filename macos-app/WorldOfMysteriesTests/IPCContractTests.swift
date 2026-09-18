import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Strict IPC contract corpus")
struct IPCContractTests {
    @Test("Schema corpus accepted and rejected identically by Swift")
    func testCanonicalCorpus() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
        let url = root.appendingPathComponent("contracts/fixtures/ipc/envelopes.json")
        let cases = try JSONDecoder().decode([IPCFixtureCase].self, from: Data(contentsOf: url))
        #expect(cases.count >= 80)
        for sample in cases {
            let bytes = try JSONEncoder().encode(sample.envelope)
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
}
