import Foundation

/// Matches the length-prefixed UTF-8 framing limits already enforced by the Engine.
nonisolated enum IPCFrameCodec {
    static let maximumBytes = 1_048_576
    static let maximumDepth = 64

    static func encode(_ envelope: IPCEnvelope) throws -> Data {
        do {
            let body = try JSONEncoder().encode(envelope)
            try validateJSON(body)
            var length = UInt32(body.count).bigEndian
            var frame = withUnsafeBytes(of: &length) { Data($0) }
            frame.append(body)
            return frame
        } catch { throw EngineConnectionError.invalidFrame }
    }

    static func decode(_ body: Data) throws -> IPCEnvelope {
        do {
            try validateJSON(body)
            return try JSONDecoder().decode(IPCEnvelope.self, from: body)
        } catch { throw EngineConnectionError.invalidFrame }
    }

    /// JSONDecoder alone does not reject duplicate object keys. Validate the original
    /// bytes first, including escaped-key equality, UTF-8, finite numbers and depth.
    private static func validateJSON(_ body: Data) throws {
        guard !body.isEmpty, body.count <= maximumBytes,
              String(data: body, encoding: .utf8) != nil else {
            throw EngineConnectionError.invalidFrame
        }
        var scanner = JSONWireScanner(bytes: Array(body))
        try scanner.document()
    }
}

private nonisolated struct JSONWireScanner {
    let bytes: [UInt8]
    var index = 0
    private var current: UInt8? { index < bytes.count ? bytes[index] : nil }

    mutating func document() throws {
        whitespace()
        guard current == 123 else { throw EngineConnectionError.invalidFrame }
        try value(depth: 0)
        whitespace()
        guard index == bytes.count else { throw EngineConnectionError.invalidFrame }
    }

    private mutating func whitespace() {
        while let c = current, c == 32 || c == 9 || c == 10 || c == 13 { index += 1 }
    }

    private mutating func require(_ byte: UInt8) throws {
        guard current == byte else { throw EngineConnectionError.invalidFrame }
        index += 1
        whitespace()
    }

    private mutating func value(depth: Int) throws {
        whitespace()
        switch current {
        case 123, 91:
            guard depth < IPCFrameCodec.maximumDepth else { throw EngineConnectionError.invalidFrame }
            let object = current == 123
            let end: UInt8 = object ? 125 : 93
            index += 1
            whitespace()
            var keys = Set<String>()
            if current == end { index += 1; return }
            while true {
                if object {
                    let key = try string()
                    guard keys.insert(key).inserted else { throw EngineConnectionError.invalidFrame }
                    whitespace()
                    try require(58)
                }
                try value(depth: depth + 1)
                whitespace()
                if current == end { index += 1; return }
                try require(44)
            }
        case 34: _ = try string()
        case 116: try literal("true")
        case 102: try literal("false")
        case 110: try literal("null")
        default:
            let start = index
            while let c = current, (48...57).contains(c) || c == 45 || c == 43 || c == 46 || c == 101 || c == 69 {
                index += 1
            }
            guard start < index,
                  let number = Double(String(decoding: bytes[start..<index], as: UTF8.self)),
                  number.isFinite else { throw EngineConnectionError.invalidFrame }
            // Complete number grammar is subsequently checked by JSONDecoder.
        }
    }

    private mutating func literal(_ text: String) throws {
        let token = Array(text.utf8)
        guard index + token.count <= bytes.count,
              bytes[index..<(index + token.count)].elementsEqual(token) else {
            throw EngineConnectionError.invalidFrame
        }
        index += token.count
    }

    private mutating func string() throws -> String {
        guard current == 34 else { throw EngineConnectionError.invalidFrame }
        let start = index
        index += 1
        var escaped = false
        while let c = current {
            index += 1
            if escaped { escaped = false; continue }
            if c == 92 { escaped = true; continue }
            if c == 34 {
                return try JSONDecoder().decode(String.self, from: Data(bytes[start..<index]))
            }
        }
        throw EngineConnectionError.invalidFrame
    }
}
