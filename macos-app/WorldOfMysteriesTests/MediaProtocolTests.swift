import CryptoKit
import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Voice media protocol parity")
struct MediaProtocolTests {
    private var repositoryRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    @Test("Canonical media corpus accepted and rejected identically by Swift")
    func canonicalCorpus() throws {
        let url = repositoryRoot.appendingPathComponent("contracts/fixtures/media/headers.json")
        let object = try JSONSerialization.jsonObject(with: Data(contentsOf: url))
        let cases = try #require(object as? [[String: Any]])
        #expect(cases.count >= 15)

        for sample in cases {
            let id = try #require(sample["id"] as? String)
            let valid = try #require(sample["valid"] as? Bool)
            let payloadLength = try #require(sample["payload_length"] as? Int)
            let header = try #require(sample["header"] as? [String: Any])
            let headerData = try JSONSerialization.data(
                withJSONObject: header,
                options: [.sortedKeys]
            )
            let wire = rawFrame(header: headerData, payloadLength: payloadLength)
            do {
                _ = try MediaFrameCodec.decode(wire)
                #expect(valid, "Unexpected acceptance: \(id)")
            } catch {
                #expect(!valid, "Unexpected rejection: \(id) -> \(error)")
            }
        }
    }

    @Test("Frame payload remains raw PCM and roundtrips")
    func rawPCM() throws {
        let payload = Data(repeating: 0x2A, count: 1_920)
        let chunk = MediaChunkHeader(
            streamId: "tts_1",
            generation: 4,
            sequence: 0,
            offsetFrames: 0,
            frameCount: 960,
            payloadBytes: payload.count
        )
        let wire = try MediaFrameCodec.encode(.init(header: .chunk(chunk), payload: payload))
        #expect(wire.suffix(payload.count) == payload)
        let decoded = try MediaFrameCodec.decode(wire)
        #expect(decoded == MediaFrame(header: .chunk(chunk), payload: payload))
    }

    @Test("Unknown fields, duplicate keys and oversized prefixes fail closed")
    func strictHeader() throws {
        let duplicate = #"{"kind":"credit","kind":"credit","protocol_version":"1.0","stream_id":"s","generation":1,"credit_bytes":2}"#
        #expect(throws: MediaProtocolFailure.invalidHeader) {
            try MediaFrameCodec.decodeHeader(Data(duplicate.utf8))
        }

        let extra: [String: Any] = [
            "kind": "credit", "protocol_version": "1.0", "stream_id": "s",
            "generation": 1, "credit_bytes": 2, "secret": "x",
        ]
        let extraData = try JSONSerialization.data(withJSONObject: extra)
        #expect(throws: MediaProtocolFailure.invalidHeader) {
            try MediaFrameCodec.decodeHeader(extraData)
        }

        var prefix = Data()
        appendUInt32(UInt32(MediaFrameCodec.maximumHeaderBytes + 1), to: &prefix)
        appendUInt32(0, to: &prefix)
        #expect(throws: MediaProtocolFailure.headerTooLarge) {
            try MediaFrameCodec.decode(prefix)
        }
    }

    @Test("Control frames cannot carry binary payload")
    func controlPayload() throws {
        let credit = MediaCreditHeader(streamId: "s", generation: 1, creditBytes: 1024)
        #expect(throws: MediaProtocolFailure.controlPayloadForbidden) {
            try MediaFrameCodec.encode(
                .init(header: .credit(credit), payload: Data([0, 0]))
            )
        }
    }

    @Test("Credit is bounded and sender cannot exceed it")
    func creditWindow() throws {
        var credit = try MediaCreditWindow(initialBytes: 4096)
        try credit.consume(2048)
        #expect(credit.availableBytes == 2048)
        try credit.grant(1024)
        #expect(credit.availableBytes == 3072)
        #expect(throws: MediaProtocolFailure.creditExhausted) {
            try credit.consume(4096)
        }
    }

    @Test("Receive state validates identity, continuity, totals and digest")
    func receiveState() throws {
        let opened = MediaOpenHeader(
            streamId: "tts_1",
            traceId: "trace_1",
            engineEpoch: "epoch_1",
            generation: 3,
            ticket: String(repeating: "a", count: 64),
            direction: .engineToApp,
            format: .init(sampleRate: 24000),
            maxPayloadBytes: 4096,
            initialCreditBytes: 4096
        )
        var state = MediaReceiveState(opened: opened)
        let p0 = Data(repeating: 1, count: 200)
        let p1 = Data(repeating: 2, count: 100)
        try state.accept(
            MediaChunkHeader(
                streamId: "tts_1", generation: 3, sequence: 0,
                offsetFrames: 0, frameCount: 100, payloadBytes: p0.count
            ),
            payload: p0
        )
        try state.accept(
            MediaChunkHeader(
                streamId: "tts_1", generation: 3, sequence: 1,
                offsetFrames: 100, frameCount: 50, payloadBytes: p1.count
            ),
            payload: p1
        )
        let digest = SHA256.hash(data: p0 + p1).map { String(format: "%02x", $0) }.joined()
        try state.finish(
            MediaEndHeader(
                streamId: "tts_1", generation: 3,
                totalFrames: 150, totalBytes: 300, sha256: digest
            )
        )
        #expect(state.totalFrames == 150)
        #expect(state.totalBytes == 300)
    }

    @Test("Late generation and sequence gaps are rejected")
    func staleAndGap() throws {
        let opened = MediaOpenHeader(
            streamId: "tts_1",
            traceId: "trace_1",
            engineEpoch: "epoch_1",
            generation: 8,
            ticket: String(repeating: "b", count: 64),
            direction: .engineToApp,
            format: .init(sampleRate: 24000),
            maxPayloadBytes: 4096,
            initialCreditBytes: 4096
        )
        var state = MediaReceiveState(opened: opened)
        #expect(throws: MediaProtocolFailure.streamIdentityMismatch) {
            try state.accept(
                MediaChunkHeader(
                    streamId: "tts_1", generation: 7, sequence: 0,
                    offsetFrames: 0, frameCount: 1, payloadBytes: 2
                ),
                payload: Data([0, 0])
            )
        }
        #expect(throws: MediaProtocolFailure.chunkSequenceMismatch) {
            try state.accept(
                MediaChunkHeader(
                    streamId: "tts_1", generation: 8, sequence: 1,
                    offsetFrames: 0, frameCount: 1, payloadBytes: 2
                ),
                payload: Data([0, 0])
            )
        }
    }

    @Test("Authenticated media grant is strict and redacts its bearer ticket")
    func grantParsing() throws {
        let ticket = String(repeating: "a", count: 64)
        let payload: [String: AnyCodableValue] = [
            "protocol_version": .string("1.0"),
            "socket_path": .string("/tmp/private/media.sock"),
            "stream_id": .string("media_1"),
            "trace_id": .string("trace_中文"),
            "engine_epoch": .string("epoch_1"),
            "generation": .int(4),
            "ticket": .string(ticket),
            "direction": .string("engine_to_app"),
            "format": .object([
                "codec": .string("pcm_s16le"),
                "sample_rate": .int(24000),
                "channels": .int(1),
            ]),
            "max_payload_bytes": .int(65536),
            "initial_credit_bytes": .int(262144),
            "expires_in_ms": .int(10000),
        ]
        let grant = try MediaOpenGrant(payload: payload)
        #expect(grant.generation == 4)
        #expect(grant.direction == .engineToApp)
        #expect(grant.format.sampleRate == 24000)
        #expect(!grant.description.contains(ticket))
        let open = grant.makeOpenHeader()
        let encoded = try MediaFrameCodec.encode(.init(header: .open(open)))
        #expect(encoded.count > 8)

        var extra = payload
        extra["unexpected"] = .bool(true)
        #expect(throws: EngineConnectionError.invalidFrame) {
            try MediaOpenGrant(payload: extra)
        }

        var badTicket = payload
        badTicket["ticket"] = .string("secret")
        #expect(throws: EngineConnectionError.invalidFrame) {
            try MediaOpenGrant(payload: badTicket)
        }
    }

    @Test("Media errors expose only fixed diagnostics")
    func fixedDiagnostics() {
        let error = MediaProtocolFailure.invalidHeader
        #expect(error.localizedDescription == "The local media stream violated its protocol contract.")
        #expect(!error.localizedDescription.contains("ticket"))
        #expect(!error.localizedDescription.contains("/Users/"))
    }

    private func rawFrame(header: Data, payloadLength: Int) -> Data {
        var frame = Data()
        appendUInt32(UInt32(header.count), to: &frame)
        appendUInt32(UInt32(payloadLength), to: &frame)
        frame.append(header)
        frame.append(Data(repeating: 0, count: payloadLength))
        return frame
    }

    private func appendUInt32(_ value: UInt32, to data: inout Data) {
        var big = value.bigEndian
        data.append(withUnsafeBytes(of: &big) { Data($0) })
    }
}
