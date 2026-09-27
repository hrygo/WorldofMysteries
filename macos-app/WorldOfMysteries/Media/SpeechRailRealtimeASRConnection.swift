import Foundation

/// Wire facts shared by every SpeechRail Realtime producer in the app.
///
/// SpeechRail 4.0 accepts exactly one wire PCM format. Keeping the number in one
/// place stops the microphone, the push-to-talk fence, the duplex graph and the
/// ASR session configuration from drifting apart.
public nonisolated enum SpeechRailRealtimeWire {
    public static let sampleRate = 24_000
    public static let pcmFormatType = "audio/pcm"
}

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
        do {
            switch try await task.receive() {
            case .string(let text):
                return Data(text.utf8)
            case .data:
                throw SpeechRailRealtimeASRFailure.unsupportedMessage
            @unknown default:
                throw SpeechRailRealtimeASRFailure.unsupportedMessage
            }
        } catch let failure as SpeechRailRealtimeASRFailure {
            throw failure
        } catch {
            throw Self.classifyTransportFailure(error, task: task)
        }
    }

    public func close() async {
        task?.cancel(with: .normalClosure, reason: nil)
        task = nil
        session?.invalidateAndCancel()
        session = nil
    }

    /// Turn a transport error into a structured failure.
    ///
    /// A rejection that happens before the upgrade completes never produces a
    /// WebSocket close code, so it is reported as `handshakeRejected` with no
    /// invented cause. `URLSessionWebSocketTask` does not expose the HTTP
    /// response of a failed upgrade, so the status stays absent rather than
    /// being guessed. Only 1008 is treated as evidence about credentials.
    private static func classifyTransportFailure(
        _ error: Error,
        task: URLSessionWebSocketTask
    ) -> SpeechRailRealtimeASRFailure {
        switch task.closeCode {
        case .policyViolation:
            return .authenticationFailed
        default:
            // 1012 (service restart) and 1013 (try again later) are overload
            // signals. Foundation does not name them, so match the wire values.
            if task.closeCode.rawValue == 1012 || task.closeCode.rawValue == 1013 {
                return .serviceBusy
            }
        }

        let nsError = error as NSError
        if nsError.domain == NSURLErrorDomain,
           nsError.code == NSURLErrorBadServerResponse {
            return .handshakeRejected(httpStatus: nil)
        }
        return .transportFailure
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
        sampleRate: Int = SpeechRailRealtimeWire.sampleRate,
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
        guard sampleRate == SpeechRailRealtimeWire.sampleRate,
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

    /// The one effective session configuration this client ever asks for.
    ///
    /// The finalization barrier re-sends exactly this object, so the value must
    /// be derived deterministically and compared against the service echo.
    public var effectiveSession: SpeechRailRealtimeSessionConfiguration {
        SpeechRailRealtimeSessionConfiguration(
            model: model,
            language: language,
            prompt: prompt,
            keywords: keywords
        )
    }

    fileprivate func sessionUpdateText(eventID: String) throws -> String {
        try SpeechRailRealtimeASRConfiguration.encodeJSONObject([
            "type": "session.update",
            "event_id": eventID,
            "session": effectiveSession.jsonObject,
        ])
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

/// The transcription session this client requests, in the SpeechRail 4.0 shape.
///
/// `audio.input` nests the wire format and the transcription options;
/// `speechrail` pins the task and disables the auxiliary capabilities. Manual
/// turn detection stays off because the app owns the turn boundary.
public nonisolated struct SpeechRailRealtimeSessionConfiguration: Sendable, Equatable {
    public let model: String
    public let language: String?
    public let prompt: String?
    public let keywords: [String]

    public init(
        model: String,
        language: String? = nil,
        prompt: String? = nil,
        keywords: [String] = []
    ) {
        self.model = model
        self.language = language
        self.prompt = prompt
        self.keywords = keywords
    }

    public var jsonObject: [String: Any] {
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
        return [
            "type": "transcription",
            "audio": [
                "input": [
                    "format": [
                        "type": SpeechRailRealtimeWire.pcmFormatType,
                        "rate": SpeechRailRealtimeWire.sampleRate,
                    ],
                    "transcription": transcription,
                    "turn_detection": NSNull(),
                    "speechrail": speechrailObject,
                ],
            ],
            "speechrail": speechrailObject,
        ]
    }

    /// Alignment and diarization are disabled for this iteration: their events
    /// are accepted and ignored, never allowed to change the text terminal.
    private var speechrailObject: [String: Any] {
        [
            "task": "transcription",
            "tts": ["enabled": false],
            "alignment": ["enabled": false],
            "diarization": ["enabled": false],
        ]
    }

    /// Parse the `session` object of a `session.created` / `session.updated`
    /// event. Anything the client asked for but the service did not echo is a
    /// mismatch, not a silently accepted default.
    public static func parse(_ object: Any) throws -> Self {
        guard let session = object as? [String: Any],
              (session["type"] as? String) == "transcription",
              let audio = session["audio"] as? [String: Any],
              let input = audio["input"] as? [String: Any],
              let format = input["format"] as? [String: Any],
              (format["type"] as? String) == SpeechRailRealtimeWire.pcmFormatType,
              let rate = format["rate"] as? NSNumber,
              rate.intValue == SpeechRailRealtimeWire.sampleRate,
              let transcription = input["transcription"] as? [String: Any],
              let model = transcription["model"] as? String,
              !model.isEmpty
        else {
            throw SpeechRailRealtimeASRFailure.invalidEnvelope
        }

        // The service may echo the speechrail block nested or hoisted; both
        // describe the same session, so accept either placement.
        let speechrail = (input["speechrail"] as? [String: Any])
            ?? (session["speechrail"] as? [String: Any])
        guard let speechrail,
              (speechrail["task"] as? String) == "transcription",
              (speechrail["tts"] as? [String: Any])?["enabled"] as? Bool == false,
              (speechrail["alignment"] as? [String: Any])?["enabled"] as? Bool == false,
              (speechrail["diarization"] as? [String: Any])?["enabled"] as? Bool == false
        else {
            throw SpeechRailRealtimeASRFailure.invalidEnvelope
        }

        // `turn_detection` is optional in the schema; an absent value and an
        // explicit null both mean "the app owns the turn boundary".
        if let turnDetection = input["turn_detection"], !(turnDetection is NSNull) {
            guard (turnDetection as? String) == "manual" else {
                throw SpeechRailRealtimeASRFailure.invalidEnvelope
            }
        }

        return Self(
            model: model,
            language: transcription["language"] as? String,
            prompt: transcription["prompt"] as? String,
            keywords: transcription["keywords"] as? [String] ?? []
        )
    }
}

public nonisolated struct SpeechRailRealtimeASRConnectionInfo: Sendable, Equatable {
    public let connectionEpoch: UUID
    public let serviceSessionID: String
    public let lastServerSequence: Int64
    public let sampleRate: Int
    public let session: SpeechRailRealtimeSessionConfiguration

    public init(
        connectionEpoch: UUID,
        serviceSessionID: String,
        lastServerSequence: Int64,
        sampleRate: Int,
        session: SpeechRailRealtimeSessionConfiguration
    ) {
        self.connectionEpoch = connectionEpoch
        self.serviceSessionID = serviceSessionID
        self.lastServerSequence = lastServerSequence
        self.sampleRate = sampleRate
        self.session = session
    }
}

public actor SpeechRailRealtimeASRConnection {
    public static let maximumAppendBytes = 64 * 1024

    private let configuration: SpeechRailRealtimeASRConfiguration
    private let transport: any SpeechRailRealtimeASRTransport
    private var connectionEpoch = UUID()
    private var serviceSessionID: String?
    private var lastServerSequence: Int64 = 0
    private var hasSequenceBaseline = false
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
        hasSequenceBaseline = false

        do {
            let created = try await receiveValidated()
            switch created.event {
            case .sessionCreated:
                // The created echo carries service defaults; our configuration
                // is only proven by the `session.updated` that follows.
                break
            case .error(let code, _):
                throw SpeechRailRealtimeASRFailure.sessionRejected(code: code)
            default:
                throw SpeechRailRealtimeASRFailure.invalidEnvelope
            }

            let updateID = "wom-session-\(UUID().uuidString)"
            try await transport.sendText(
                configuration.sessionUpdateText(eventID: updateID)
            )
            let updated = try await receiveValidated()
            guard case .sessionUpdated(let echoed) = updated.event else {
                if case .error(let code, _) = updated.event {
                    throw SpeechRailRealtimeASRFailure.sessionRejected(code: code)
                }
                throw SpeechRailRealtimeASRFailure.invalidEnvelope
            }
            // The handshake only counts as ready once the service proved it
            // applied the exact configuration we asked for.
            guard echoed == configuration.effectiveSession else {
                throw SpeechRailRealtimeASRFailure.sessionConfigurationMismatch
            }

            ready = true
            guard let serviceSessionID else {
                throw SpeechRailRealtimeASRFailure.invalidEnvelope
            }
            return SpeechRailRealtimeASRConnectionInfo(
                connectionEpoch: connectionEpoch,
                serviceSessionID: serviceSessionID,
                lastServerSequence: lastServerSequence,
                sampleRate: configuration.sampleRate,
                session: echoed
            )
        } catch {
            await transport.close()
            serviceSessionID = nil
            lastServerSequence = 0
            hasSequenceBaseline = false
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

    /// Re-send the identical effective session configuration.
    ///
    /// The service processes client events on one FIFO queue, so this update is
    /// handled only after the commit handler has drained its ASR reader. The
    /// resulting `session.updated` is therefore the barrier that proves every
    /// item of this turn is terminal.
    @discardableResult
    public func resendSessionUpdate() async throws -> String {
        guard ready else {
            throw SpeechRailRealtimeASRFailure.notConnected
        }
        let eventID = "wom-barrier-\(UUID().uuidString)"
        try await transport.sendText(
            configuration.sessionUpdateText(eventID: eventID)
        )
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
            sampleRate: configuration.sampleRate,
            session: configuration.effectiveSession
        )
    }

    public func close() async {
        ready = false
        serviceSessionID = nil
        lastServerSequence = 0
        hasSequenceBaseline = false
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

        if hasSequenceBaseline {
            let expected = lastServerSequence + 1
            guard envelope.sequence == expected else {
                throw SpeechRailRealtimeASRFailure.sequenceGap(
                    expected: expected,
                    actual: envelope.sequence
                )
            }
        } else {
            // The schema allows 0; the pinned service starts at 1. Accept
            // either first value, then require strict continuity.
            guard envelope.sequence == 0 || envelope.sequence == 1 else {
                throw SpeechRailRealtimeASRFailure.sequenceGap(
                    expected: 1,
                    actual: envelope.sequence
                )
            }
            hasSequenceBaseline = true
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
