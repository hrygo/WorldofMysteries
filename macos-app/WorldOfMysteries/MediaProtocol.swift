import CryptoKit
import Foundation

public nonisolated enum MediaProtocolFailure: Error, Equatable, LocalizedError {
    case invalidHeader
    case headerTooLarge
    case payloadTooLarge
    case frameIncomplete
    case controlPayloadForbidden
    case payloadLengthMismatch
    case frameCountMismatch
    case streamIdentityMismatch
    case chunkSequenceMismatch
    case chunkOffsetMismatch
    case streamTotalsMismatch
    case streamDigestMismatch
    case streamTerminal
    case creditInvalid
    case creditExhausted

    public var errorDescription: String? {
        "The local media stream violated its protocol contract."
    }
}

public nonisolated enum MediaDirection: String, Codable, Sendable {
    case appToEngine = "app_to_engine"
    case engineToApp = "engine_to_app"
}

public nonisolated enum MediaCancelReason: String, Codable, Sendable {
    case userStop = "user_stop"
    case superseded
    case sessionClosed = "session_closed"
    case timeout
    case shutdown
}

public nonisolated struct MediaFormat: Codable, Sendable, Equatable {
    public let codec: String
    public let sampleRate: Int
    public let channels: Int

    public init(codec: String = "pcm_s16le", sampleRate: Int, channels: Int = 1) {
        self.codec = codec
        self.sampleRate = sampleRate
        self.channels = channels
    }

    enum CodingKeys: String, CodingKey {
        case codec
        case sampleRate = "sample_rate"
        case channels
    }
}

public nonisolated struct MediaOpenHeader: Codable, Sendable, Equatable {
    public let kind: String
    public let protocolVersion: String
    public let streamId: String
    public let traceId: String
    public let engineEpoch: String
    public let generation: Int64
    public let ticket: String
    public let direction: MediaDirection
    public let format: MediaFormat
    public let maxPayloadBytes: Int
    public let initialCreditBytes: Int

    public init(
        streamId: String,
        traceId: String,
        engineEpoch: String,
        generation: Int64,
        ticket: String,
        direction: MediaDirection,
        format: MediaFormat,
        maxPayloadBytes: Int = 64 * 1024,
        initialCreditBytes: Int = 256 * 1024
    ) {
        self.kind = "open"
        self.protocolVersion = MediaFrameCodec.protocolVersion
        self.streamId = streamId
        self.traceId = traceId
        self.engineEpoch = engineEpoch
        self.generation = generation
        self.ticket = ticket
        self.direction = direction
        self.format = format
        self.maxPayloadBytes = maxPayloadBytes
        self.initialCreditBytes = initialCreditBytes
    }

    enum CodingKeys: String, CodingKey {
        case kind
        case protocolVersion = "protocol_version"
        case streamId = "stream_id"
        case traceId = "trace_id"
        case engineEpoch = "engine_epoch"
        case generation, ticket, direction, format
        case maxPayloadBytes = "max_payload_bytes"
        case initialCreditBytes = "initial_credit_bytes"
    }
}

public nonisolated struct MediaChunkHeader: Codable, Sendable, Equatable {
    public let kind: String
    public let protocolVersion: String
    public let streamId: String
    public let generation: Int64
    public let sequence: Int64
    public let offsetFrames: Int64
    public let frameCount: Int
    public let payloadBytes: Int

    public init(
        streamId: String,
        generation: Int64,
        sequence: Int64,
        offsetFrames: Int64,
        frameCount: Int,
        payloadBytes: Int
    ) {
        self.kind = "chunk"
        self.protocolVersion = MediaFrameCodec.protocolVersion
        self.streamId = streamId
        self.generation = generation
        self.sequence = sequence
        self.offsetFrames = offsetFrames
        self.frameCount = frameCount
        self.payloadBytes = payloadBytes
    }

    enum CodingKeys: String, CodingKey {
        case kind
        case protocolVersion = "protocol_version"
        case streamId = "stream_id"
        case generation, sequence
        case offsetFrames = "offset_frames"
        case frameCount = "frame_count"
        case payloadBytes = "payload_bytes"
    }
}

public nonisolated struct MediaCreditHeader: Codable, Sendable, Equatable {
    public let kind: String
    public let protocolVersion: String
    public let streamId: String
    public let generation: Int64
    public let creditBytes: Int

    public init(streamId: String, generation: Int64, creditBytes: Int) {
        self.kind = "credit"
        self.protocolVersion = MediaFrameCodec.protocolVersion
        self.streamId = streamId
        self.generation = generation
        self.creditBytes = creditBytes
    }

    enum CodingKeys: String, CodingKey {
        case kind
        case protocolVersion = "protocol_version"
        case streamId = "stream_id"
        case generation
        case creditBytes = "credit_bytes"
    }
}

public nonisolated struct MediaEndHeader: Codable, Sendable, Equatable {
    public let kind: String
    public let protocolVersion: String
    public let streamId: String
    public let generation: Int64
    public let totalFrames: Int64
    public let totalBytes: Int64
    public let sha256: String?

    public init(
        streamId: String,
        generation: Int64,
        totalFrames: Int64,
        totalBytes: Int64,
        sha256: String? = nil
    ) {
        self.kind = "end"
        self.protocolVersion = MediaFrameCodec.protocolVersion
        self.streamId = streamId
        self.generation = generation
        self.totalFrames = totalFrames
        self.totalBytes = totalBytes
        self.sha256 = sha256
    }

    enum CodingKeys: String, CodingKey {
        case kind
        case protocolVersion = "protocol_version"
        case streamId = "stream_id"
        case generation
        case totalFrames = "total_frames"
        case totalBytes = "total_bytes"
        case sha256
    }
}

public nonisolated struct MediaCancelHeader: Codable, Sendable, Equatable {
    public let kind: String
    public let protocolVersion: String
    public let streamId: String
    public let generation: Int64
    public let reason: MediaCancelReason

    public init(streamId: String, generation: Int64, reason: MediaCancelReason) {
        self.kind = "cancel"
        self.protocolVersion = MediaFrameCodec.protocolVersion
        self.streamId = streamId
        self.generation = generation
        self.reason = reason
    }

    enum CodingKeys: String, CodingKey {
        case kind
        case protocolVersion = "protocol_version"
        case streamId = "stream_id"
        case generation, reason
    }
}

public nonisolated struct MediaErrorHeader: Codable, Sendable, Equatable {
    public let kind: String
    public let protocolVersion: String
    public let streamId: String
    public let generation: Int64
    public let code: String
    public let message: String
    public let retryable: Bool

    public init(
        streamId: String,
        generation: Int64,
        code: String,
        message: String,
        retryable: Bool
    ) {
        self.kind = "error"
        self.protocolVersion = MediaFrameCodec.protocolVersion
        self.streamId = streamId
        self.generation = generation
        self.code = code
        self.message = message
        self.retryable = retryable
    }

    enum CodingKeys: String, CodingKey {
        case kind
        case protocolVersion = "protocol_version"
        case streamId = "stream_id"
        case generation, code, message, retryable
    }
}

public nonisolated enum MediaHeader: Sendable, Equatable {
    case open(MediaOpenHeader)
    case chunk(MediaChunkHeader)
    case credit(MediaCreditHeader)
    case end(MediaEndHeader)
    case cancel(MediaCancelHeader)
    case error(MediaErrorHeader)

    fileprivate var kind: String {
        switch self {
        case .open: "open"
        case .chunk: "chunk"
        case .credit: "credit"
        case .end: "end"
        case .cancel: "cancel"
        case .error: "error"
        }
    }

    fileprivate var streamId: String {
        switch self {
        case .open(let h): h.streamId
        case .chunk(let h): h.streamId
        case .credit(let h): h.streamId
        case .end(let h): h.streamId
        case .cancel(let h): h.streamId
        case .error(let h): h.streamId
        }
    }

    fileprivate var generation: Int64 {
        switch self {
        case .open(let h): h.generation
        case .chunk(let h): h.generation
        case .credit(let h): h.generation
        case .end(let h): h.generation
        case .cancel(let h): h.generation
        case .error(let h): h.generation
        }
    }
}

public nonisolated struct MediaFrame: Sendable, Equatable {
    public let header: MediaHeader
    public let payload: Data

    public init(header: MediaHeader, payload: Data = Data()) {
        self.header = header
        self.payload = payload
    }
}

public nonisolated enum MediaFrameCodec {
    public static let protocolVersion = "1.0"
    public static let maximumHeaderBytes = 16 * 1024
    public static let maximumPayloadBytes = 256 * 1024
    public static let maximumCreditBytes = 8 * 1024 * 1024
    public static let pcm16MonoBytesPerFrame = 2
    private static let maximumDepth = 32

    private static let allowedKeys: [String: Set<String>] = [
        "open": [
            "kind", "protocol_version", "stream_id", "trace_id", "engine_epoch",
            "generation", "ticket", "direction", "format", "max_payload_bytes",
            "initial_credit_bytes",
        ],
        "chunk": [
            "kind", "protocol_version", "stream_id", "generation", "sequence",
            "offset_frames", "frame_count", "payload_bytes",
        ],
        "credit": [
            "kind", "protocol_version", "stream_id", "generation", "credit_bytes",
        ],
        "end": [
            "kind", "protocol_version", "stream_id", "generation", "total_frames",
            "total_bytes", "sha256",
        ],
        "cancel": [
            "kind", "protocol_version", "stream_id", "generation", "reason",
        ],
        "error": [
            "kind", "protocol_version", "stream_id", "generation", "code",
            "message", "retryable",
        ],
    ]

    public static func encode(_ frame: MediaFrame) throws -> Data {
        let headerData = try encodeHeader(frame.header)
        try validatePayload(frame.header, payloadLength: frame.payload.count)
        var headerLength = UInt32(headerData.count).bigEndian
        var payloadLength = UInt32(frame.payload.count).bigEndian
        var data = withUnsafeBytes(of: &headerLength) { Data($0) }
        data.append(withUnsafeBytes(of: &payloadLength) { Data($0) })
        data.append(headerData)
        data.append(frame.payload)
        return data
    }

    public static func decode(_ data: Data) throws -> MediaFrame {
        guard data.count >= 8 else { throw MediaProtocolFailure.frameIncomplete }
        let headerLength = Int(readUInt32(data.prefix(4)))
        let payloadLength = Int(readUInt32(data.dropFirst(4).prefix(4)))
        guard headerLength >= 2, headerLength <= maximumHeaderBytes else {
            throw MediaProtocolFailure.headerTooLarge
        }
        guard payloadLength <= maximumPayloadBytes else {
            throw MediaProtocolFailure.payloadTooLarge
        }
        guard data.count == 8 + headerLength + payloadLength else {
            throw MediaProtocolFailure.frameIncomplete
        }
        let headerStart = 8
        let payloadStart = headerStart + headerLength
        let header = try decodeHeader(data.subdata(in: headerStart..<payloadStart))
        try validatePayload(header, payloadLength: payloadLength)
        let payload = data.subdata(in: payloadStart..<data.count)
        return MediaFrame(header: header, payload: payload)
    }

    public static func encodeHeader(_ header: MediaHeader) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        let data: Data
        switch header {
        case .open(let h): data = try encoder.encode(h)
        case .chunk(let h): data = try encoder.encode(h)
        case .credit(let h): data = try encoder.encode(h)
        case .end(let h): data = try encoder.encode(h)
        case .cancel(let h): data = try encoder.encode(h)
        case .error(let h): data = try encoder.encode(h)
        }
        guard !data.isEmpty, data.count <= maximumHeaderBytes else {
            throw MediaProtocolFailure.headerTooLarge
        }
        _ = try decodeHeader(data)
        return data
    }

    public static func decodeHeader(_ data: Data) throws -> MediaHeader {
        guard !data.isEmpty, data.count <= maximumHeaderBytes,
              String(data: data, encoding: .utf8) != nil else {
            throw MediaProtocolFailure.invalidHeader
        }
        var scanner = MediaJSONWireScanner(bytes: Array(data))
        try scanner.document()

        let object = try JSONSerialization.jsonObject(with: data)
        guard let dictionary = object as? [String: Any],
              let kind = dictionary["kind"] as? String,
              let allowed = allowedKeys[kind],
              Set(dictionary.keys).isSubset(of: allowed) else {
            throw MediaProtocolFailure.invalidHeader
        }

        let decoder = JSONDecoder()
        do {
            let header: MediaHeader
            switch kind {
            case "open": header = .open(try decoder.decode(MediaOpenHeader.self, from: data))
            case "chunk": header = .chunk(try decoder.decode(MediaChunkHeader.self, from: data))
            case "credit": header = .credit(try decoder.decode(MediaCreditHeader.self, from: data))
            case "end": header = .end(try decoder.decode(MediaEndHeader.self, from: data))
            case "cancel": header = .cancel(try decoder.decode(MediaCancelHeader.self, from: data))
            case "error": header = .error(try decoder.decode(MediaErrorHeader.self, from: data))
            default: throw MediaProtocolFailure.invalidHeader
            }
            try validateHeader(header)
            return header
        } catch let error as MediaProtocolFailure {
            throw error
        } catch {
            throw MediaProtocolFailure.invalidHeader
        }
    }

    private static func readUInt32(_ bytes: Data.SubSequence) -> UInt32 {
        bytes.reduce(0) { ($0 << 8) | UInt32($1) }
    }

    private static func validateHeader(_ header: MediaHeader) throws {
        guard !header.streamId.isEmpty, header.streamId.count <= 128,
              header.generation >= 0 else {
            throw MediaProtocolFailure.invalidHeader
        }
        switch header {
        case .open(let h):
            guard h.kind == "open", h.protocolVersion == protocolVersion,
                  !h.traceId.isEmpty, h.traceId.count <= 128,
                  !h.engineEpoch.isEmpty, h.engineEpoch.count <= 128,
                  h.ticket.count == 64,
                  h.ticket.allSatisfy({ $0.isASCIIHexLowercase }),
                  h.format.codec == "pcm_s16le",
                  [16000, 24000, 48000].contains(h.format.sampleRate),
                  h.format.channels == 1,
                  isEvenInRange(h.maxPayloadBytes, min: 2, max: maximumPayloadBytes),
                  h.initialCreditBytes >= 0,
                  h.initialCreditBytes <= maximumCreditBytes,
                  h.initialCreditBytes.isMultiple(of: 2) else {
                throw MediaProtocolFailure.invalidHeader
            }
        case .chunk(let h):
            guard h.kind == "chunk", h.protocolVersion == protocolVersion,
                  h.sequence >= 0, h.offsetFrames >= 0,
                  (1...131072).contains(h.frameCount),
                  isEvenInRange(h.payloadBytes, min: 2, max: maximumPayloadBytes) else {
                throw MediaProtocolFailure.invalidHeader
            }
        case .credit(let h):
            guard h.kind == "credit", h.protocolVersion == protocolVersion,
                  isEvenInRange(h.creditBytes, min: 2, max: maximumCreditBytes) else {
                throw MediaProtocolFailure.invalidHeader
            }
        case .end(let h):
            guard h.kind == "end", h.protocolVersion == protocolVersion,
                  h.totalFrames >= 0, h.totalBytes >= 0,
                  h.totalBytes.isMultiple(of: 2),
                  h.sha256 == nil || (
                    h.sha256?.count == 64
                    && h.sha256?.allSatisfy({ $0.isASCIIHexLowercase }) == true
                  ) else {
                throw MediaProtocolFailure.invalidHeader
            }
        case .cancel(let h):
            guard h.kind == "cancel", h.protocolVersion == protocolVersion else {
                throw MediaProtocolFailure.invalidHeader
            }
        case .error(let h):
            guard h.kind == "error", h.protocolVersion == protocolVersion,
                  !h.code.isEmpty, h.code.count <= 128,
                  h.message.count <= 512 else {
                throw MediaProtocolFailure.invalidHeader
            }
        }
    }

    private static func validatePayload(_ header: MediaHeader, payloadLength: Int) throws {
        guard payloadLength >= 0, payloadLength <= maximumPayloadBytes else {
            throw MediaProtocolFailure.payloadTooLarge
        }
        switch header {
        case .chunk(let h):
            guard payloadLength == h.payloadBytes else {
                throw MediaProtocolFailure.payloadLengthMismatch
            }
            guard payloadLength == h.frameCount * pcm16MonoBytesPerFrame else {
                throw MediaProtocolFailure.frameCountMismatch
            }
        default:
            guard payloadLength == 0 else {
                throw MediaProtocolFailure.controlPayloadForbidden
            }
        }
    }

    private static func isEvenInRange(_ value: Int, min: Int, max: Int) -> Bool {
        value >= min && value <= max && value.isMultiple(of: 2)
    }
}

public nonisolated struct MediaCreditWindow: Sendable, Equatable {
    public private(set) var availableBytes: Int

    public init(initialBytes: Int) throws {
        guard initialBytes >= 0,
              initialBytes <= MediaFrameCodec.maximumCreditBytes,
              initialBytes.isMultiple(of: 2) else {
            throw MediaProtocolFailure.creditInvalid
        }
        self.availableBytes = initialBytes
    }

    public mutating func grant(_ bytes: Int) throws {
        guard bytes > 0, bytes.isMultiple(of: 2),
              bytes <= MediaFrameCodec.maximumCreditBytes,
              availableBytes + bytes <= MediaFrameCodec.maximumCreditBytes else {
            throw MediaProtocolFailure.creditInvalid
        }
        availableBytes += bytes
    }

    public mutating func consume(_ bytes: Int) throws {
        guard bytes > 0, bytes.isMultiple(of: 2) else {
            throw MediaProtocolFailure.creditInvalid
        }
        guard bytes <= availableBytes else {
            throw MediaProtocolFailure.creditExhausted
        }
        availableBytes -= bytes
    }
}

public nonisolated struct MediaReceiveState {
    private let streamId: String
    private let generation: Int64
    private let maxPayloadBytes: Int
    private var expectedSequence: Int64 = 0
    private var expectedOffsetFrames: Int64 = 0
    private var byteCount: Int64 = 0
    private var hasher = SHA256()
    private var ended = false

    public init(opened: MediaOpenHeader) {
        streamId = opened.streamId
        generation = opened.generation
        maxPayloadBytes = opened.maxPayloadBytes
    }

    public var totalFrames: Int64 { expectedOffsetFrames }
    public var totalBytes: Int64 { byteCount }

    public mutating func accept(_ header: MediaChunkHeader, payload: Data) throws {
        guard !ended else { throw MediaProtocolFailure.streamTerminal }
        guard header.streamId == streamId, header.generation == generation else {
            throw MediaProtocolFailure.streamIdentityMismatch
        }
        guard header.sequence == expectedSequence else {
            throw MediaProtocolFailure.chunkSequenceMismatch
        }
        guard header.offsetFrames == expectedOffsetFrames else {
            throw MediaProtocolFailure.chunkOffsetMismatch
        }
        guard header.payloadBytes <= maxPayloadBytes else {
            throw MediaProtocolFailure.payloadTooLarge
        }
        _ = try MediaFrameCodec.encode(.init(header: .chunk(header), payload: payload))

        expectedSequence += 1
        expectedOffsetFrames += Int64(header.frameCount)
        byteCount += Int64(payload.count)
        hasher.update(data: payload)
    }

    public mutating func finish(_ header: MediaEndHeader) throws {
        guard !ended else { throw MediaProtocolFailure.streamTerminal }
        guard header.streamId == streamId, header.generation == generation else {
            throw MediaProtocolFailure.streamIdentityMismatch
        }
        guard header.totalFrames == expectedOffsetFrames,
              header.totalBytes == byteCount,
              header.totalBytes == header.totalFrames * Int64(MediaFrameCodec.pcm16MonoBytesPerFrame)
        else {
            throw MediaProtocolFailure.streamTotalsMismatch
        }
        let digest = hasher.finalize().map { String(format: "%02x", $0) }.joined()
        if let expected = header.sha256, expected != digest {
            throw MediaProtocolFailure.streamDigestMismatch
        }
        ended = true
    }
}

private extension Character {
    var isASCIIHexLowercase: Bool {
        guard let scalar = unicodeScalars.first, unicodeScalars.count == 1 else { return false }
        return (48...57).contains(scalar.value) || (97...102).contains(scalar.value)
    }
}

private nonisolated struct MediaJSONWireScanner {
    let bytes: [UInt8]
    var index = 0
    private var current: UInt8? { index < bytes.count ? bytes[index] : nil }

    mutating func document() throws {
        whitespace()
        guard current == 123 else { throw MediaProtocolFailure.invalidHeader }
        try value(depth: 0)
        whitespace()
        guard index == bytes.count else { throw MediaProtocolFailure.invalidHeader }
    }

    private mutating func whitespace() {
        while let c = current, c == 32 || c == 9 || c == 10 || c == 13 { index += 1 }
    }

    private mutating func require(_ byte: UInt8) throws {
        guard current == byte else { throw MediaProtocolFailure.invalidHeader }
        index += 1
        whitespace()
    }

    private mutating func value(depth: Int) throws {
        whitespace()
        switch current {
        case 123, 91:
            guard depth < MediaFrameCodec.maximumDepthForScanner else {
                throw MediaProtocolFailure.invalidHeader
            }
            let object = current == 123
            let end: UInt8 = object ? 125 : 93
            index += 1
            whitespace()
            var keys = Set<String>()
            if current == end { index += 1; return }
            while true {
                if object {
                    let key = try string()
                    guard keys.insert(key).inserted else {
                        throw MediaProtocolFailure.invalidHeader
                    }
                    whitespace()
                    try require(58)
                }
                try value(depth: depth + 1)
                whitespace()
                if current == end { index += 1; return }
                try require(44)
            }
        case 34:
            _ = try string()
        case 116:
            try literal("true")
        case 102:
            try literal("false")
        case 110:
            try literal("null")
        default:
            let start = index
            while let c = current,
                  (48...57).contains(c) || c == 45 || c == 43 || c == 46 || c == 101 || c == 69 {
                index += 1
            }
            guard start < index,
                  let number = Double(String(decoding: bytes[start..<index], as: UTF8.self)),
                  number.isFinite else {
                throw MediaProtocolFailure.invalidHeader
            }
        }
    }

    private mutating func literal(_ text: String) throws {
        let token = Array(text.utf8)
        guard index + token.count <= bytes.count,
              bytes[index..<(index + token.count)].elementsEqual(token) else {
            throw MediaProtocolFailure.invalidHeader
        }
        index += token.count
    }

    private mutating func string() throws -> String {
        guard current == 34 else { throw MediaProtocolFailure.invalidHeader }
        let start = index
        index += 1
        var escaped = false
        while let c = current {
            index += 1
            if escaped { escaped = false; continue }
            if c == 92 { escaped = true; continue }
            if c == 34 {
                do {
                    return try JSONDecoder().decode(String.self, from: Data(bytes[start..<index]))
                } catch {
                    throw MediaProtocolFailure.invalidHeader
                }
            }
        }
        throw MediaProtocolFailure.invalidHeader
    }
}

private extension MediaFrameCodec {
    static var maximumDepthForScanner: Int { maximumDepth }
}
