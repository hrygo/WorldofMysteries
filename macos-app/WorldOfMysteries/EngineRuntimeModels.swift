import Foundation

/// Fixed, user-safe failures. Never include socket paths, payloads or launch credentials.
public nonisolated enum EngineConnectionError: Error, LocalizedError, Sendable, Equatable {
    case runtimeUnavailable, invalidConfiguration, launchFailed, notConnected
    case authenticationFailed, connectionFailed, timedOut, disconnected
    case invalidFrame, correlationMismatch, capacityExceeded, methodUnavailable

    public var errorDescription: String? {
        switch self {
        case .runtimeUnavailable: "此构建尚未包含本地引擎，当前展示示例数据。"
        case .invalidConfiguration: "本地引擎运行环境无效。"
        case .launchFailed: "本地引擎未能启动。"
        case .authenticationFailed: "本地引擎连接验证失败。"
        case .timedOut: "本地引擎响应超时，尚未确认的操作不会自动重发。"
        case .invalidFrame, .correlationMismatch: "本地引擎响应无效，已断开连接。"
        case .capacityExceeded: "本地引擎连接已达到安全容量限制。"
        case .methodUnavailable: "本地引擎尚未提供此功能。"
        case .connectionFailed, .notConnected, .disconnected: "本地引擎连接已断开。"
        }
    }
}

/// Derived from the canonical handshake payload, not a status=ok shortcut.
public nonisolated struct EngineHandshake: Sendable, Equatable {
    public let engineVersion: String
    public let pythonVersion: String
    public let capabilities: Set<String>

    init(payload: [String: AnyCodableValue]) throws {
        let names: Set<String> = ["engine_version", "engine_build", "python_version", "protocol_version", "capabilities"]
        guard Set(payload.keys) == names,
              case .string(let version) = payload["engine_version"], !version.isEmpty,
              case .string(let build) = payload["engine_build"], !build.isEmpty,
              case .string(let python) = payload["python_version"], !python.isEmpty,
              payload["protocol_version"] == .string("1.0"),
              case .array(let items) = payload["capabilities"] else {
            throw EngineConnectionError.authenticationFailed
        }
        var methods = Set<String>()
        for item in items {
            guard case .string(let name) = item, !name.isEmpty, methods.insert(name).inserted else {
                throw EngineConnectionError.authenticationFailed
            }
        }
        engineVersion = version
        pythonVersion = python
        capabilities = methods
    }
}

public nonisolated struct EngineHealth: Sendable, Equatable {
    public let transportReady: Bool
    public let worldReady: Bool
    public let modelReady: Bool
    public let voiceReady: Bool

    init(payload: [String: AnyCodableValue]) throws {
        guard Set(payload.keys) == ["transport_ready", "world_ready", "model_ready", "voice_ready"],
              case .bool(let transport) = payload["transport_ready"],
              case .bool(let world) = payload["world_ready"],
              case .bool(let model) = payload["model_ready"],
              case .bool(let voice) = payload["voice_ready"] else {
            throw EngineConnectionError.invalidFrame
        }
        transportReady = transport
        worldReady = world
        modelReady = model
        voiceReady = voice
    }
}
