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
