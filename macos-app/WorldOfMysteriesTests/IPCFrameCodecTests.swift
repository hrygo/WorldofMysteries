import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Production IPC wire framing")
struct IPCFrameCodecTests {
    @Test("Length prefix counts UTF-8 bytes, not Swift characters")
    func utf8Length() throws {
        let request = IPCEnvelope(kind: "request", traceId: "t", requestId: "r", method: "test", payload: ["text": .string("诡秘世界")])
        let frame = try IPCFrameCodec.encode(request)
        let size = frame.prefix(4).reduce(0) { ($0 << 8) | Int($1) }
        #expect(size == frame.count - 4)
        let decoded = try IPCFrameCodec.decode(Data(frame.dropFirst(4)))
        #expect(decoded.payload?["text"] == .string("诡秘世界"))
    }

    @Test("Malformed original JSON is rejected before dictionary normalization", arguments: [
        #"{"kind":"request","kind":"request","protocol_version":"1.0","trace_id":"t","request_id":"r","method":"m","payload":{}}"#,
        #"{"kind":"request","protocol_version":"1.0","trace_id":"t","request_id":"r","method":"m","payload":{"x":1,"\u0078":2}}"#,
        #"{"kind":"request","protocol_version":"1.0","trace_id":"t","request_id":"r","method":"m","payload":{"x":NaN}}"#,
        #"{"kind":"request","protocol_version":"1.0","trace_id":"t","request_id":"r","method":"m","payload":{"x":1e999}}"#,
        #"{"kind":"request","protocol_version":"1.0","trace_id":"t","request_id":"r","method":"m","payload":{"x":01}}"#,
        "[]", "null", "{}{}", ""
    ])
    func malformed(_ text: String) {
        #expect(throws: EngineConnectionError.invalidFrame) { try IPCFrameCodec.decode(Data(text.utf8)) }
    }

    @Test("Oversized, non-UTF-8 and excessively nested frames fail closed")
    func bounds() {
        #expect(throws: EngineConnectionError.invalidFrame) { try IPCFrameCodec.decode(Data([255])) }
        #expect(throws: EngineConnectionError.invalidFrame) { try IPCFrameCodec.decode(Data(repeating: 32, count: IPCFrameCodec.maximumBytes + 1)) }
        let deep = #"{"kind":"request","protocol_version":"1.0","trace_id":"t","request_id":"r","method":"m","payload":{"x":"#
            + String(repeating: "[", count: 65) + "0" + String(repeating: "]", count: 65) + "}}"
        #expect(throws: EngineConnectionError.invalidFrame) { try IPCFrameCodec.decode(Data(deep.utf8)) }
    }

    @Test("Protocol diagnostics never contain payloads or credentials")
    func fixedDiagnostics() {
        for error in [EngineConnectionError.authenticationFailed, .invalidFrame, .correlationMismatch, .timedOut] {
            #expect(error.errorDescription != nil)
            #expect(!error.localizedDescription.contains("session_token"))
            #expect(!error.localizedDescription.contains("/Users/"))
        }
    }
}
