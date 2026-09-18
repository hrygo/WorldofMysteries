import Foundation

private nonisolated struct IPCWireKey: CodingKey {
    let stringValue: String
    let intValue: Int? = nil
    init?(stringValue: String) { self.stringValue = stringValue }
    init?(intValue: Int) { return nil }
}

/// Protocol errors intentionally contain no incoming payload or authentication token.
public nonisolated enum IPCContractError: Error { case invalidEnvelope }

private nonisolated func checkWireKeys(
    _ decoder: any Decoder, allowed: Set<String>, required: Set<String>
) throws {
    let values = try decoder.container(keyedBy: IPCWireKey.self)
    let keys = Set(values.allKeys.map(\.stringValue))
    guard required.isSubset(of: keys), keys.isSubset(of: allowed) else {
        throw IPCContractError.invalidEnvelope
    }
    for key in values.allKeys where try values.decodeNil(forKey: key) {
        throw IPCContractError.invalidEnvelope
    }
}

/// Structured error shared with the canonical IPC schema.
public nonisolated struct IPCErrorPayload: Codable, Sendable, Equatable {
    public let code: String
    public let message: String
    public let retryable: Bool
    public let details: [String: AnyCodableValue]

    public init(code: String, message: String, retryable: Bool = false,
                details: [String: AnyCodableValue] = [:]) {
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details
    }

    enum CodingKeys: String, CodingKey { case code, message, retryable, details }

    public init(from decoder: any Decoder) throws {
        try checkWireKeys(decoder, allowed: ["code", "message", "retryable", "details"],
                          required: ["code", "message", "retryable"])
        let c = try decoder.container(keyedBy: CodingKeys.self)
        code = try c.decode(String.self, forKey: .code)
        message = try c.decode(String.self, forKey: .message)
        retryable = try c.decode(Bool.self, forKey: .retryable)
        details = try c.decodeIfPresent([String: AnyCodableValue].self, forKey: .details) ?? [:]
        guard !code.isEmpty else { throw IPCContractError.invalidEnvelope }
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

/// IPC v1.0 envelope. Wire encoding and decoding both enforce kind-specific invariants.
/// The nonthrowing convenience initializer remains source-compatible for preview call sites;
/// invalid constructed values cannot be encoded onto the wire.
public nonisolated struct IPCEnvelope: Codable, Sendable {
    public let kind: String
    public let protocolVersion: String
    public let traceId: String
    public let requestId: String?
    public let streamId: String?
    public let sequence: Int?
    public let storyRevision: Int?
    public let turnId: String?
    public let idempotencyKey: String?
    public let method: String?
    public let event: String?
    public let status: String?
    public let error: IPCErrorPayload?
    public let payload: [String: AnyCodableValue]?

    public init(
        kind: String, protocolVersion: String = "1.0", traceId: String,
        requestId: String? = nil, streamId: String? = nil, sequence: Int? = nil,
        storyRevision: Int? = nil, turnId: String? = nil, idempotencyKey: String? = nil,
        method: String? = nil, event: String? = nil, status: String? = nil,
        error: IPCErrorPayload? = nil, payload: [String: AnyCodableValue]? = nil
    ) {
        self.kind = kind
        self.protocolVersion = protocolVersion
        self.traceId = traceId
        self.requestId = requestId
        self.streamId = streamId
        self.sequence = sequence
        self.storyRevision = storyRevision
        self.turnId = turnId
        self.idempotencyKey = idempotencyKey
        self.method = method
        self.event = event
        self.status = status
        self.error = error
        self.payload = payload ?? ((kind == "request" || kind == "event" || status == "ok") ? [:] : nil)
    }

    enum CodingKeys: String, CodingKey {
        case kind, sequence, method, event, status, error, payload
        case protocolVersion = "protocol_version"
        case traceId = "trace_id"
        case requestId = "request_id"
        case streamId = "stream_id"
        case storyRevision = "story_revision"
        case turnId = "turn_id"
        case idempotencyKey = "idempotency_key"
    }

    public init(from decoder: any Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        kind = try c.decode(String.self, forKey: .kind)
        let common: Set<String> = ["kind", "protocol_version", "trace_id"]
        let required: Set<String>
        let allowed: Set<String>
        switch kind {
        case "request":
            required = common.union(["request_id", "method", "payload"])
            allowed = required.union(["idempotency_key"])
        case "response":
            required = common.union(["request_id", "status"])
            allowed = required.union(["payload", "error"])
        case "event":
            required = common.union(["stream_id", "sequence", "event", "payload"])
            allowed = required.union(["story_revision", "turn_id"])
        default:
            throw IPCContractError.invalidEnvelope
        }
        try checkWireKeys(decoder, allowed: allowed, required: required)
        protocolVersion = try c.decode(String.self, forKey: .protocolVersion)
        traceId = try c.decode(String.self, forKey: .traceId)
        requestId = try c.decodeIfPresent(String.self, forKey: .requestId)
        streamId = try c.decodeIfPresent(String.self, forKey: .streamId)
        sequence = try c.decodeIfPresent(Int.self, forKey: .sequence)
        storyRevision = try c.decodeIfPresent(Int.self, forKey: .storyRevision)
        turnId = try c.decodeIfPresent(String.self, forKey: .turnId)
        idempotencyKey = try c.decodeIfPresent(String.self, forKey: .idempotencyKey)
        method = try c.decodeIfPresent(String.self, forKey: .method)
        event = try c.decodeIfPresent(String.self, forKey: .event)
        status = try c.decodeIfPresent(String.self, forKey: .status)
        error = try c.decodeIfPresent(IPCErrorPayload.self, forKey: .error)
        payload = try c.decodeIfPresent([String: AnyCodableValue].self, forKey: .payload)
        try validate()
    }

    private func validate() throws {
        guard protocolVersion == "1.0", !traceId.isEmpty,
              [requestId, streamId, turnId, idempotencyKey, method, event].allSatisfy({ $0 == nil || !$0!.isEmpty }),
              sequence == nil || sequence! >= 0,
              storyRevision == nil || storyRevision! >= 0 else {
            throw IPCContractError.invalidEnvelope
        }
        switch kind {
        case "request":
            guard requestId != nil, method != nil, payload != nil, status == nil, error == nil,
                  streamId == nil, sequence == nil, storyRevision == nil, turnId == nil, event == nil else {
                throw IPCContractError.invalidEnvelope
            }
        case "response":
            guard requestId != nil, method == nil, idempotencyKey == nil,
                  streamId == nil, sequence == nil, storyRevision == nil, turnId == nil, event == nil else {
                throw IPCContractError.invalidEnvelope
            }
            switch status {
            case "ok":
                guard payload != nil, error == nil else { throw IPCContractError.invalidEnvelope }
            case "error":
                guard payload == nil, let error, !error.code.isEmpty else { throw IPCContractError.invalidEnvelope }
            default:
                throw IPCContractError.invalidEnvelope
            }
        case "event":
            guard streamId != nil, sequence != nil, event != nil, payload != nil,
                  requestId == nil, method == nil, idempotencyKey == nil, status == nil, error == nil else {
                throw IPCContractError.invalidEnvelope
            }
        default:
            throw IPCContractError.invalidEnvelope
        }
    }

    public func encode(to encoder: any Encoder) throws {
        try validate()
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(kind, forKey: .kind)
        try c.encode(protocolVersion, forKey: .protocolVersion)
        try c.encode(traceId, forKey: .traceId)
        try c.encodeIfPresent(requestId, forKey: .requestId)
        try c.encodeIfPresent(streamId, forKey: .streamId)
        try c.encodeIfPresent(sequence, forKey: .sequence)
        try c.encodeIfPresent(storyRevision, forKey: .storyRevision)
        try c.encodeIfPresent(turnId, forKey: .turnId)
        try c.encodeIfPresent(idempotencyKey, forKey: .idempotencyKey)
        try c.encodeIfPresent(method, forKey: .method)
        try c.encodeIfPresent(event, forKey: .event)
        try c.encodeIfPresent(status, forKey: .status)
        try c.encodeIfPresent(error, forKey: .error)
        try c.encodeIfPresent(payload, forKey: .payload)
    }

    public func decodePayload<T: Decodable>(as type: T.Type, using decoder: JSONDecoder = JSONDecoder()) throws -> T? {
        guard let payload else { return nil }
        return try decoder.decode(type, from: JSONEncoder().encode(payload))
    }
}
