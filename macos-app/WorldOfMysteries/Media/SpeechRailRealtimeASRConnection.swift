import Foundation

public nonisolated protocol SpeechRailRealtimeASRTransport: Sendable {
    func open(_ request: URLRequest) async throws
    func sendText(_ text: String) async throws
    func receiveData() async throws -> Data
    func close() async
}

public actor URLSessionSpeechRailRealtimeASRTransport: SpeechRailRealtimeASRTransport {
    private var session: URLSession?
    private var task: URLSessionWebSocketTask?

    public init() {}

    public func open(_ request: URLRequest) async throws {
        guard task == nil else {
            throw SpeechRailRealtimeASRFailure.invalidState
        }
        let configuration = URLSessionConfiguration.ephemeral
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.urlCache = nil
        let session = URLSession(configuration: configuration)
        let task = session.webSocketTask(with: request)
        self.session = session
        self.task = task
        task.resume()
    }

    public func sendText(_ text: String) async throws {
        guard let task else {
            throw SpeechRailRealtimeASRFailure.notConnected
        }
        try await task.send(.string(text))
    }

    public func receiveData() async throws -> Data {
        guard let task else {
            throw SpeechRailRealtimeASRFailure.notConnected
        }
        switch try await task.receive() {
        case .string(let text):
            return Data(text.utf8)
        case .data:
            throw SpeechRailRealtimeASRFailure.unsupportedMessage
        @unknown default:
            throw SpeechRailRealtimeASRFailure.unsupportedMessage
        }
    }

    public func close() async {
        task?.cancel(with: .normalClosure, reason: nil)
        task = nil
        session?.invalidateAndCancel()
        session = nil
    }
}

public nonisolated struct SpeechRailRealtimeASRConfiguration: Sendable, Equatable, CustomStringConvertible {
    public let baseURL: URL
    public let model: String
    public let sampleRate: Int
    public let language: String?
    public let prompt: String?
    public let keywords: [String]
    public let allowRemote: Bool
    fileprivate let apiKey: String?

    public init(
        baseURL: URL = URL(string: "http://127.0.0.1:8201/v1")!,
        apiKey: String? = nil,
        model: String = "whisper-1",
        sampleRate: Int = 24_000,
        language: String? = "zh",
        prompt: String? = nil,
        keywords: [String] = [],
        allowRemote: Bool = false
    ) {
        self.baseURL = baseURL
        self.apiKey = apiKey?.trimmingCharacters(in: .whitespacesAndNewlines)
        self.model = model
        self.sampleRate = sampleRate
        self.language = language
        self.prompt = prompt
        self.keywords = keywords
        self.allowRemote = allowRemote
    }

    public var description: String {
        "SpeechRailRealtimeASRConfiguration(baseURL: \(baseURL.absoluteString), model: \(model), sampleRate: \(sampleRate), apiKey: <redacted>)"
    }

    fileprivate func makeRequest() throws -> URLRequest {
        guard [16_000, 24_000].contains(sampleRate),
              !model.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              prompt.map({ $0.count <= 2_000 }) ?? true,
              keywords.count <= 128,
              keywords.allSatisfy({
                  !$0.isEmpty && $0.count <= 256
              }),
              var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false),
              let originalScheme = components.scheme?.lowercased(),
              originalScheme == "http" || originalScheme == "https",
              let host = components.host?.lowercased(),
              components.user == nil,
              components.password == nil,
              components.query == nil,
              components.fragment == nil
        else {
            throw SpeechRailRealtimeASRFailure.invalidConfiguration
        }

        let loopbackHosts: Set<String> = ["127.0.0.1", "localhost", "::1"]
        if !allowRemote, !loopbackHosts.contains(host) {
            throw SpeechRailRealtimeASRFailure.invalidConfiguration
        }
        if allowRemote, !loopbackHosts.contains(host), originalScheme != "https" {
            throw SpeechRailRealtimeASRFailure.invalidConfiguration
        }

        var basePath = components.path
        while basePath.count > 1, basePath.hasSuffix("/") {
            basePath.removeLast()
        }
        guard basePath.hasSuffix("/v1") else {
            throw SpeechRailRealtimeASRFailure.invalidConfiguration
        }

        components.scheme = originalScheme == "https" ? "wss" : "ws"
        components.path = basePath + "/realtime"
        components.queryItems = [URLQueryItem(name: "model", value: model)]

        guard let url = components.url else {
            throw SpeechRailRealtimeASRFailure.invalidConfiguration
        }
        var request = URLRequest(url: url)
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.timeoutInterval = 10
        if let apiKey, !apiKey.isEmpty {
            request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    fileprivate func sessionUpdateText(eventID: String) throws -> String {
        var transcription: [String: Any] = ["model": model]
        if let language, !language.isEmpty {
            transcription["language"] = language
        }
        if let prompt, !prompt.isEmpty {
            transcription["prompt"] = prompt
        }
        if !keywords.isEmpty {
            transcription["keywords"] = keywords
        }
        let payload: [String: Any] = [
            "type": "session.update",
            "event_id": eventID,
            "session": [
                "type": "transcription",
                "audio": [
                    "input": [
                        "format": [
                            "type": "audio/pcm",
                            "rate": sampleRate,
                        ],
                        "transcription": transcription,
                        "turn_detection": NSNull(),
                    ]
                ],
            ],
        ]
        return try Self.encodeJSONObject(payload)
    }

    fileprivate static func encodeJSONObject(_ object: [String: Any]) throws -> String {
        guard JSONSerialization.isValidJSONObject(object) else {
            throw SpeechRailRealtimeASRFailure.invalidConfiguration
        }
        let data = try JSONSerialization.data(
            withJSONObject: object,
            options: [.sortedKeys, .withoutEscapingSlashes]
        )
        guard let text = String(data: data, encoding: .utf8) else {
            throw SpeechRailRealtimeASRFailure.invalidConfiguration
        }
        return text
    }
}

public nonisolated struct SpeechRailRealtimeASRConnectionInfo: Sendable, Equatable {
    public let connectionEpoch: UUID
    public let serviceSessionID: String
    public let lastServerSequence: Int64
    public let sampleRate: Int
}

public actor SpeechRailRealtimeASRConnection {
    public static let maximumAppendBytes = 64 * 1024

    private let configuration: SpeechRailRealtimeASRConfiguration
    private let transport: any SpeechRailRealtimeASRTransport
    private var connectionEpoch = UUID()
    private var serviceSessionID: String?
    private var lastServerSequence: Int64 = 0
    private var ready = false

    public init(
        configuration: SpeechRailRealtimeASRConfiguration = .init(),
        transport: (any SpeechRailRealtimeASRTransport)? = nil
    ) {
        self.configuration = configuration
        self.transport = transport ?? URLSessionSpeechRailRealtimeASRTransport()
    }

    public func connect() async throws -> SpeechRailRealtimeASRConnectionInfo {
        guard !ready else {
            throw SpeechRailRealtimeASRFailure.invalidState
        }
        let request = try configuration.makeRequest()
        try await transport.open(request)

        connectionEpoch = UUID()
        serviceSessionID = nil
        lastServerSequence = 0

        do {
            let created = try await receiveValidated()
            guard created.event == .sessionCreated else {
                if case .error(let code, _) = created.event {
                    throw SpeechRailRealtimeASRFailure.sessionRejected(code: code)
                }
                throw SpeechRailRealtimeASRFailure.invalidEnvelope
            }

            let conversation = try await receiveValidated()
            guard conversation.event == .conversationCreated else {
                if case .error(let code, _) = conversation.event {
                    throw SpeechRailRealtimeASRFailure.sessionRejected(code: code)
                }
                throw SpeechRailRealtimeASRFailure.invalidEnvelope
            }

            let updateID = "wom-session-\(UUID().uuidString)"
            try await transport.sendText(
                configuration.sessionUpdateText(eventID: updateID)
            )
            let updated = try await receiveValidated()
            guard updated.event == .sessionUpdated else {
                if case .error(let code, _) = updated.event {
                    throw SpeechRailRealtimeASRFailure.sessionRejected(code: code)
                }
                throw SpeechRailRealtimeASRFailure.invalidEnvelope
            }

            ready = true
            guard let serviceSessionID else {
                throw SpeechRailRealtimeASRFailure.invalidEnvelope
            }
            return SpeechRailRealtimeASRConnectionInfo(
                connectionEpoch: connectionEpoch,
                serviceSessionID: serviceSessionID,
                lastServerSequence: lastServerSequence,
                sampleRate: configuration.sampleRate
            )
        } catch {
            await transport.close()
            serviceSessionID = nil
            lastServerSequence = 0
            ready = false
            throw error
        }
    }

    @discardableResult
    public func appendPCM16(_ pcm16: Data) async throws -> String {
        guard ready else {
            throw SpeechRailRealtimeASRFailure.notConnected
        }
        guard !pcm16.isEmpty,
              pcm16.count.isMultiple(of: 2),
              pcm16.count <= Self.maximumAppendBytes
        else {
            throw SpeechRailRealtimeASRFailure.audioFrameInvalid
        }
        let eventID = "wom-append-\(UUID().uuidString)"
        try await send([
            "type": "input_audio_buffer.append",
            "event_id": eventID,
            "audio": pcm16.base64EncodedString(),
        ])
        return eventID
    }

    @discardableResult
    public func commit() async throws -> String {
        guard ready else {
            throw SpeechRailRealtimeASRFailure.notConnected
        }
        let eventID = "wom-commit-\(UUID().uuidString)"
        try await send([
            "type": "input_audio_buffer.commit",
            "event_id": eventID,
        ])
        return eventID
    }

    @discardableResult
    public func clear() async throws -> String {
        guard ready else {
            throw SpeechRailRealtimeASRFailure.notConnected
        }
        let eventID = "wom-clear-\(UUID().uuidString)"
        try await send([
            "type": "input_audio_buffer.clear",
            "event_id": eventID,
        ])
        return eventID
    }

    public func receiveEnvelope() async throws -> SpeechRailASRServerEnvelope {
        guard ready else {
            throw SpeechRailRealtimeASRFailure.notConnected
        }
        return try await receiveValidated()
    }

    public func currentInfo() throws -> SpeechRailRealtimeASRConnectionInfo {
        guard ready, let serviceSessionID else {
            throw SpeechRailRealtimeASRFailure.notConnected
        }
        return SpeechRailRealtimeASRConnectionInfo(
            connectionEpoch: connectionEpoch,
            serviceSessionID: serviceSessionID,
            lastServerSequence: lastServerSequence,
            sampleRate: configuration.sampleRate
        )
    }

    public func close() async {
        ready = false
        serviceSessionID = nil
        lastServerSequence = 0
        connectionEpoch = UUID()
        await transport.close()
    }

    private func send(_ object: [String: Any]) async throws {
        let text = try SpeechRailRealtimeASRConfiguration.encodeJSONObject(object)
        try await transport.sendText(text)
    }

    private func receiveValidated() async throws -> SpeechRailASRServerEnvelope {
        let envelope: SpeechRailASRServerEnvelope
        do {
            envelope = try SpeechRailASRServerEnvelope.decode(
                try await transport.receiveData()
            )
        } catch let failure as SpeechRailRealtimeASRFailure {
            throw failure
        } catch {
            throw SpeechRailRealtimeASRFailure.connectionClosed
        }

        let expected = lastServerSequence + 1
        guard envelope.sequence == expected else {
            throw SpeechRailRealtimeASRFailure.sequenceGap(
                expected: expected,
                actual: envelope.sequence
            )
        }
        if let serviceSessionID {
            guard serviceSessionID == envelope.sessionID else {
                throw SpeechRailRealtimeASRFailure.invalidEnvelope
            }
        } else {
            serviceSessionID = envelope.sessionID
        }
        lastServerSequence = envelope.sequence
        return envelope
    }
}
