import Foundation

/// Standard IPC Envelope representing message transfer over UDS.
public struct IPCEnvelope: Codable, Sendable {
    public let kind: String
    public let protocolVersion: String
    public let traceId: String
    public let requestId: String?
    public let method: String?
    public let status: String?
    public let errorCode: String?
    public let errorMessage: String?

    public init(
        kind: String,
        protocolVersion: String = "1.0",
        traceId: String,
        requestId: String? = nil,
        method: String? = nil,
        status: String? = nil,
        errorCode: String? = nil,
        errorMessage: String? = nil
    ) {
        self.kind = kind
        self.protocolVersion = protocolVersion
        self.traceId = traceId
        self.requestId = requestId
        self.method = method
        self.status = status
        self.errorCode = errorCode
        self.errorMessage = errorMessage
    }

    enum CodingKeys: String, CodingKey {
        case kind
        case protocolVersion = "protocol_version"
        case traceId = "trace_id"
        case requestId = "request_id"
        case method
        case status
        case errorCode = "error_code"
        case errorMessage = "error_message"
    }
}
