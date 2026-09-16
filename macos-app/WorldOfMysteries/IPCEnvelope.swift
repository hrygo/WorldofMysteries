import Foundation

/// Structured error payload for IPC communications.
public nonisolated struct IPCErrorPayload: Codable, Sendable, Equatable {
    public let code: String
    public let message: String
    public let retryable: Bool

    public init(code: String, message: String, retryable: Bool = false) {
        self.code = code
        self.message = message
        self.retryable = retryable
    }
}

/// Type-erased Codable and Sendable JSON representation.
public nonisolated enum AnyCodableValue: Codable, Sendable, Equatable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case object([String: AnyCodableValue])
    case array([AnyCodableValue])
    case null

    public init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let b = try? container.decode(Bool.self) {
            self = .bool(b)
        } else if let i = try? container.decode(Int.self) {
            self = .int(i)
        } else if let d = try? container.decode(Double.self) {
            self = .double(d)
        } else if let s = try? container.decode(String.self) {
            self = .string(s)
        } else if let arr = try? container.decode([AnyCodableValue].self) {
            self = .array(arr)
        } else if let dict = try? container.decode([String: AnyCodableValue].self) {
            self = .object(dict)
        } else {
            throw DecodingError.dataCorrupted(
                DecodingError.Context(codingPath: decoder.codingPath, debugDescription: "Unknown JSON value")
            )
        }
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let s):
            try container.encode(s)
        case .int(let i):
            try container.encode(i)
        case .double(let d):
            try container.encode(d)
        case .bool(let b):
            try container.encode(b)
        case .object(let dict):
            try container.encode(dict)
        case .array(let arr):
            try container.encode(arr)
        case .null:
            try container.encodeNil()
        }
    }
}

/// Standard IPC Envelope representing message transfer over UDS between macOS App and Engine.
public nonisolated struct IPCEnvelope: Codable, Sendable {
    public let kind: String
    public let protocolVersion: String
    public let traceId: String
    public let requestId: String?
    public let streamId: String?
    public let sequence: Int?
    public let idempotencyKey: String?
    public let method: String?
    public let event: String?
    public let status: String?
    public let error: IPCErrorPayload?
    public let payload: [String: AnyCodableValue]?

    public init(
        kind: String,
        protocolVersion: String = "1.0",
        traceId: String,
        requestId: String? = nil,
        streamId: String? = nil,
        sequence: Int? = nil,
        idempotencyKey: String? = nil,
        method: String? = nil,
        event: String? = nil,
        status: String? = nil,
        error: IPCErrorPayload? = nil,
        payload: [String: AnyCodableValue]? = nil
    ) {
        self.kind = kind
        self.protocolVersion = protocolVersion
        self.traceId = traceId
        self.requestId = requestId
        self.streamId = streamId
        self.sequence = sequence
        self.idempotencyKey = idempotencyKey
        self.method = method
        self.event = event
        self.status = status
        self.error = error
        self.payload = payload
    }

    enum CodingKeys: String, CodingKey {
        case kind
        case protocolVersion = "protocol_version"
        case traceId = "trace_id"
        case requestId = "request_id"
        case streamId = "stream_id"
        case sequence
        case idempotencyKey = "idempotency_key"
        case method
        case event
        case status
        case error
        case payload
    }

    /// Convenience helper to decode the dictionary payload into a typed Decodable struct.
    public func decodePayload<T: Decodable>(as type: T.Type, using decoder: JSONDecoder = JSONDecoder()) throws -> T? {
        guard let payload else { return nil }
        let data = try JSONEncoder().encode(payload)
        return try decoder.decode(type, from: data)
    }
}

