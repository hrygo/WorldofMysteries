import CryptoKit
import Foundation

public nonisolated enum SpeechRailRealtimeTTSFailure: Error, Sendable, Equatable, LocalizedError {
    case invalidConfiguration
    case notConnected
    case unsupportedMessage
    case ttsUnavailable
    case sessionRejected(code: String)
    case invalidEnvelope
    case sequenceGap(expected: Int64, actual: Int64)
    case requestInvalid
    case responseMismatch
    case audioChunkInvalid
    case audioStreamIncomplete
    case receiptMissing
    case receiptMismatch
    case providerFailed(code: String?)
    case cancelled
    case connectionClosed
    case invalidState

    public var errorDescription: String? {
        "The realtime speech render could not be proven complete."
    }
}

public nonisolated enum SpeechRailTTSResponseStatus: String, Sendable, Equatable {
    case completed
    case failed
    case cancelled
}

public nonisolated struct SpeechRailTTSRenderReceiptSummary: Sendable, Equatable {
    public let receiptID: String
    public let requestID: String
    public let responseID: String
    public let status: String
    public let voiceID: String
    public let voiceRevision: String?
    public let outputFormat: String
    public let sampleRate: Int
    public let channels: Int
    public let sampleCount: Int64
    public let pcmSHA256: String
    public let errorCode: String?

    fileprivate static func decode(_ object: [String: Any]) throws -> Self {
        func string(_ object: [String: Any], _ key: String) throws -> String {
            guard let value = object[key] as? String, !value.isEmpty else {
                throw SpeechRailRealtimeTTSFailure.invalidEnvelope
            }
            return value
        }
        guard let voice = object["voice"] as? [String: Any],
              let audio = object["audio"] as? [String: Any],
              let sampleRate = audio["pcm_sample_rate"] as? Int,
              let channels = audio["channels"] as? Int,
              let sampleCountNumber = audio["sample_count"] as? NSNumber,
              sampleCountNumber.int64Value >= 0
        else {
            throw SpeechRailRealtimeTTSFailure.invalidEnvelope
        }
        return Self(
            receiptID: try string(object, "receipt_id"),
            requestID: try string(object, "request_id"),
            responseID: try string(object, "response_id"),
            status: try string(object, "status"),
            voiceID: try string(voice, "id"),
            voiceRevision: voice["revision"] as? String,
            outputFormat: try string(audio, "format"),
            sampleRate: sampleRate,
            channels: channels,
            sampleCount: sampleCountNumber.int64Value,
            pcmSHA256: try string(audio, "pcm_sha256"),
            errorCode: object["error_code"] as? String
        )
    }
}

public nonisolated enum SpeechRailTTSServerEvent: Sendable, Equatable {
    case sessionCreated(ttsAvailable: Bool)
    case transcriptionSessionUpdated(ttsEnabled: Bool, receiptsEnabled: Bool)
    case responseCreated(responseID: String)
    case audioDelta(responseID: String, itemID: String, pcm16: Data)
    case audioDone(responseID: String, itemID: String)
    case responseDone(
        responseID: String,
        status: SpeechRailTTSResponseStatus,
        requestID: String,
        voiceRevision: String?,
        receipt: SpeechRailTTSRenderReceiptSummary?
    )
    case error(code: String, requestID: String?, triggerEventID: String?)
    case other(type: String)
}

public nonisolated struct SpeechRailTTSServerEnvelope: Sendable, Equatable {
    public let eventID: String
    public let sessionID: String
    public let sequence: Int64
    public let event: SpeechRailTTSServerEvent

    public static func decode(_ data: Data) throws -> Self {
        struct Base: Decodable {
            let type: String
            let event_id: String
            let session_id: String
            let sequence: Int64
        }

        let base: Base
        do {
            base = try JSONDecoder().decode(Base.self, from: data)
        } catch {
            throw SpeechRailRealtimeTTSFailure.invalidEnvelope
        }
        guard !base.type.isEmpty,
              !base.event_id.isEmpty,
              !base.session_id.isEmpty,
              base.sequence > 0
        else {
            throw SpeechRailRealtimeTTSFailure.invalidEnvelope
        }

        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw SpeechRailRealtimeTTSFailure.invalidEnvelope
        }

        func requiredString(_ object: [String: Any], _ key: String) throws -> String {
            guard let value = object[key] as? String, !value.isEmpty else {
                throw SpeechRailRealtimeTTSFailure.invalidEnvelope
            }
            return value
        }

        let event: SpeechRailTTSServerEvent
        switch base.type {
        case "session.created":
            guard let session = object["session"] as? [String: Any] else {
                throw SpeechRailRealtimeTTSFailure.invalidEnvelope
            }
            let capabilities = session["capabilities"] as? [String] ?? []
            let speechCapabilities = session["speech_capabilities"] as? [String: Any]
            let available = capabilities.contains("speech")
                || (speechCapabilities?["available"] as? Bool == true)
            event = .sessionCreated(ttsAvailable: available)

        case "transcription_session.updated":
            guard let session = object["session"] as? [String: Any],
                  let speechrail = session["speechrail"] as? [String: Any],
                  let tts = speechrail["tts"] as? [String: Any],
                  let enabled = tts["enabled"] as? Bool
            else {
                throw SpeechRailRealtimeTTSFailure.invalidEnvelope
            }
            let receipts = (speechrail["render_receipts"] as? [String: Any])?["enabled"] as? Bool ?? false
            event = .transcriptionSessionUpdated(
                ttsEnabled: enabled,
                receiptsEnabled: receipts
            )

        case "response.created":
            guard let response = object["response"] as? [String: Any] else {
                throw SpeechRailRealtimeTTSFailure.invalidEnvelope
            }
            event = .responseCreated(responseID: try requiredString(response, "id"))

        case "response.output_audio.delta":
            let responseID = try requiredString(object, "response_id")
            let itemID = try requiredString(object, "item_id")
            let encoded = try requiredString(object, "delta")
            guard let pcm16 = Data(base64Encoded: encoded),
                  !pcm16.isEmpty,
                  pcm16.count.isMultiple(of: MemoryLayout<Int16>.size)
            else {
                throw SpeechRailRealtimeTTSFailure.audioChunkInvalid
            }
            event = .audioDelta(responseID: responseID, itemID: itemID, pcm16: pcm16)

        case "response.output_audio.done":
            event = .audioDone(
                responseID: try requiredString(object, "response_id"),
                itemID: try requiredString(object, "item_id")
            )

        case "response.done":
            guard let response = object["response"] as? [String: Any],
                  let statusText = response["status"] as? String,
                  let status = SpeechRailTTSResponseStatus(rawValue: statusText),
                  let speechrail = object["speechrail"] as? [String: Any],
                  speechrail["kind"] as? String == "tts"
            else {
                throw SpeechRailRealtimeTTSFailure.invalidEnvelope
            }
            let receipt: SpeechRailTTSRenderReceiptSummary?
            if let rawReceipt = speechrail["render_receipt"] as? [String: Any] {
                receipt = try .decode(rawReceipt)
            } else {
                receipt = nil
            }
            event = .responseDone(
                responseID: try requiredString(response, "id"),
                status: status,
                requestID: try requiredString(speechrail, "request_id"),
                voiceRevision: speechrail["voice_revision"] as? String,
                receipt: receipt
            )

        case "error":
            guard let error = object["error"] as? [String: Any] else {
                throw SpeechRailRealtimeTTSFailure.invalidEnvelope
            }
            event = .error(
                code: try requiredString(error, "code"),
                requestID: error["request_id"] as? String,
                triggerEventID: error["event_id"] as? String
            )

        default:
            event = .other(type: base.type)
        }

        return Self(
            eventID: base.event_id,
            sessionID: base.session_id,
            sequence: base.sequence,
            event: event
        )
    }
}

public nonisolated protocol SpeechRailRealtimeTTSTransport: Sendable {
    func open(_ request: URLRequest) async throws
    func sendText(_ text: String) async throws
    func receiveData() async throws -> Data
    func close() async
}

public actor URLSessionSpeechRailRealtimeTTSTransport: SpeechRailRealtimeTTSTransport {
    private var session: URLSession?
    private var task: URLSessionWebSocketTask?

    public init() {}

    public func open(_ request: URLRequest) async throws {
        guard task == nil else { throw SpeechRailRealtimeTTSFailure.invalidState }
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
        guard let task else { throw SpeechRailRealtimeTTSFailure.notConnected }
        try await task.send(.string(text))
    }

    public func receiveData() async throws -> Data {
        guard let task else { throw SpeechRailRealtimeTTSFailure.notConnected }
        switch try await task.receive() {
        case .string(let text):
            return Data(text.utf8)
        case .data:
            throw SpeechRailRealtimeTTSFailure.unsupportedMessage
        @unknown default:
            throw SpeechRailRealtimeTTSFailure.unsupportedMessage
        }
    }

    public func close() async {
        task?.cancel(with: .normalClosure, reason: nil)
        task = nil
        session?.invalidateAndCancel()
        session = nil
    }
}

public nonisolated struct SpeechRailRealtimeTTSConfiguration: Sendable, Equatable, CustomStringConvertible {
    public let baseURL: URL
    public let allowRemote: Bool
    public let renderReceipts: Bool
    public let expectedModelRevision: String?
    fileprivate let apiKey: String?

    public init(
        baseURL: URL = URL(string: "http://127.0.0.1:8201/v1")!,
        apiKey: String? = nil,
        allowRemote: Bool = false,
        renderReceipts: Bool = true,
        expectedModelRevision: String? = nil
    ) {
        self.baseURL = baseURL
        self.apiKey = apiKey?.trimmingCharacters(in: .whitespacesAndNewlines)
        self.allowRemote = allowRemote
        self.renderReceipts = renderReceipts
        self.expectedModelRevision = expectedModelRevision
    }

    public var description: String {
        "SpeechRailRealtimeTTSConfiguration(baseURL: \(baseURL.absoluteString), apiKey: <redacted>)"
    }

    fileprivate func makeRequest() throws -> URLRequest {
        guard var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false),
              let originalScheme = components.scheme?.lowercased(),
              originalScheme == "http" || originalScheme == "https",
              let host = components.host?.lowercased(),
              components.user == nil,
              components.password == nil,
              components.query == nil,
              components.fragment == nil,
              Self.validModelRevision(expectedModelRevision)
        else {
            throw SpeechRailRealtimeTTSFailure.invalidConfiguration
        }

        let loopbackHosts: Set<String> = ["127.0.0.1", "localhost", "::1"]
        if !allowRemote, !loopbackHosts.contains(host) {
            throw SpeechRailRealtimeTTSFailure.invalidConfiguration
        }
        if allowRemote, !loopbackHosts.contains(host), originalScheme != "https" {
            throw SpeechRailRealtimeTTSFailure.invalidConfiguration
        }

        var basePath = components.path
        while basePath.count > 1, basePath.hasSuffix("/") { basePath.removeLast() }
        guard basePath.hasSuffix("/v1") else {
            throw SpeechRailRealtimeTTSFailure.invalidConfiguration
        }

        components.scheme = originalScheme == "https" ? "wss" : "ws"
        components.path = basePath + "/realtime"
        guard let url = components.url else {
            throw SpeechRailRealtimeTTSFailure.invalidConfiguration
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
        var speechrail: [String: Any] = [
            "tts": ["enabled": true],
            "render_receipts": ["enabled": renderReceipts],
        ]
        if let expectedModelRevision {
            speechrail["model_revision"] = ["expected": expectedModelRevision]
        }
        return try Self.encodeJSONObject([
            "type": "transcription_session.update",
            "event_id": eventID,
            "session": [
                "type": "transcription",
                "turn_detection": NSNull(),
                "speechrail": speechrail,
            ],
        ])
    }

    fileprivate static func encodeJSONObject(_ object: [String: Any]) throws -> String {
        guard JSONSerialization.isValidJSONObject(object) else {
            throw SpeechRailRealtimeTTSFailure.invalidConfiguration
        }
        let data = try JSONSerialization.data(
            withJSONObject: object,
            options: [.sortedKeys, .withoutEscapingSlashes]
        )
        guard let text = String(data: data, encoding: .utf8) else {
            throw SpeechRailRealtimeTTSFailure.invalidConfiguration
        }
        return text
    }

    private static func validModelRevision(_ revision: String?) -> Bool {
        guard let revision else { return true }
        guard revision.count == 40 else { return false }
        return revision.utf8.allSatisfy { byte in
            (48...57).contains(byte) || (97...102).contains(byte)
        }
    }
}

public nonisolated struct SpeechRailTTSRequest: Sendable, Equatable {
    public let requestID: String
    public let text: String
    public let voice: String
    public let speed: Double
    public let expectedVoiceRevision: String?

    public init(
        requestID: String,
        text: String,
        voice: String,
        speed: Double = 1.0,
        expectedVoiceRevision: String? = nil
    ) {
        self.requestID = requestID
        self.text = text
        self.voice = voice
        self.speed = speed
        self.expectedVoiceRevision = expectedVoiceRevision
    }

    fileprivate func encodedText() throws -> String {
        guard !requestID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              requestID.count <= 128,
              !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              text.count <= 4_096,
              !voice.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              voice.count <= 128,
              speed.isFinite,
              (0.25...4.0).contains(speed),
              expectedVoiceRevision.map({ !$0.isEmpty && $0.count <= 128 }) ?? true
        else {
            throw SpeechRailRealtimeTTSFailure.requestInvalid
        }
        var object: [String: Any] = [
            "type": "speechrail.tts.create",
            "request_id": requestID,
            "text": text,
            "voice": voice,
            "speed": speed,
        ]
        if let expectedVoiceRevision {
            object["expected_voice_revision"] = expectedVoiceRevision
        }
        return try SpeechRailRealtimeTTSConfiguration.encodeJSONObject(object)
    }
}

public nonisolated struct SpeechRailRealtimeTTSConnectionInfo: Sendable, Equatable {
    public let serviceSessionID: String
    public let lastServerSequence: Int64
    public let ttsEnabled: Bool
    public let renderReceiptsEnabled: Bool
}

public actor SpeechRailRealtimeTTSConnection {
    private let configuration: SpeechRailRealtimeTTSConfiguration
    private let transport: any SpeechRailRealtimeTTSTransport
    private var serviceSessionID: String?
    private var lastServerSequence: Int64 = 0
    private var ready = false
    private var activeRequestID: String?
    private var activeResponseID: String?

    public init(
        configuration: SpeechRailRealtimeTTSConfiguration = .init(),
        transport: (any SpeechRailRealtimeTTSTransport)? = nil
    ) {
        self.configuration = configuration
        self.transport = transport ?? URLSessionSpeechRailRealtimeTTSTransport()
    }

    public func connect() async throws -> SpeechRailRealtimeTTSConnectionInfo {
        guard !ready else { throw SpeechRailRealtimeTTSFailure.invalidState }
        let request = try configuration.makeRequest()
        try await transport.open(request)
        serviceSessionID = nil
        lastServerSequence = 0
        activeRequestID = nil
        activeResponseID = nil

        do {
            let created = try await receiveValidated()
            guard case .sessionCreated(let ttsAvailable) = created.event else {
                if case .error(let code, _, _) = created.event {
                    throw SpeechRailRealtimeTTSFailure.sessionRejected(code: code)
                }
                throw SpeechRailRealtimeTTSFailure.invalidEnvelope
            }
            guard ttsAvailable else { throw SpeechRailRealtimeTTSFailure.ttsUnavailable }

            try await transport.sendText(
                configuration.sessionUpdateText(eventID: "wom-tts-session-\(UUID().uuidString)")
            )
            let updated = try await receiveValidated()
            guard case .transcriptionSessionUpdated(let ttsEnabled, let receiptsEnabled) = updated.event else {
                if case .error(let code, _, _) = updated.event {
                    throw SpeechRailRealtimeTTSFailure.sessionRejected(code: code)
                }
                throw SpeechRailRealtimeTTSFailure.invalidEnvelope
            }
            guard ttsEnabled else { throw SpeechRailRealtimeTTSFailure.ttsUnavailable }
            if configuration.renderReceipts, !receiptsEnabled {
                throw SpeechRailRealtimeTTSFailure.sessionRejected(code: "render_receipts_not_enabled")
            }

            ready = true
            return try currentInfo()
        } catch {
            await transport.close()
            serviceSessionID = nil
            lastServerSequence = 0
            ready = false
            activeRequestID = nil
            activeResponseID = nil
            throw error
        }
    }

    public func begin(_ request: SpeechRailTTSRequest) async throws {
        guard ready else { throw SpeechRailRealtimeTTSFailure.notConnected }
        guard activeRequestID == nil else { throw SpeechRailRealtimeTTSFailure.invalidState }
        let text = try request.encodedText()
        activeRequestID = request.requestID
        activeResponseID = nil
        do {
            try await transport.sendText(text)
        } catch {
            activeRequestID = nil
            throw error
        }
    }

    public func cancelCurrent() async throws {
        guard ready else { throw SpeechRailRealtimeTTSFailure.notConnected }
        guard let requestID = activeRequestID else { throw SpeechRailRealtimeTTSFailure.invalidState }
        var object: [String: Any] = [
            "type": "speechrail.tts.cancel",
            "request_id": requestID,
        ]
        if let activeResponseID { object["response_id"] = activeResponseID }
        try await transport.sendText(
            SpeechRailRealtimeTTSConfiguration.encodeJSONObject(object)
        )
    }

    public func receiveEnvelope() async throws -> SpeechRailTTSServerEnvelope {
        guard ready else { throw SpeechRailRealtimeTTSFailure.notConnected }
        let envelope = try await receiveValidated()
        try validateActiveResponse(envelope.event)
        return envelope
    }

    public func currentInfo() throws -> SpeechRailRealtimeTTSConnectionInfo {
        guard ready, let serviceSessionID else {
            throw SpeechRailRealtimeTTSFailure.notConnected
        }
        return SpeechRailRealtimeTTSConnectionInfo(
            serviceSessionID: serviceSessionID,
            lastServerSequence: lastServerSequence,
            ttsEnabled: true,
            renderReceiptsEnabled: configuration.renderReceipts
        )
    }

    public func close() async {
        ready = false
        serviceSessionID = nil
        lastServerSequence = 0
        activeRequestID = nil
        activeResponseID = nil
        await transport.close()
    }

    private func validateActiveResponse(_ event: SpeechRailTTSServerEvent) throws {
        switch event {
        case .responseCreated(let responseID):
            guard activeRequestID != nil else { throw SpeechRailRealtimeTTSFailure.responseMismatch }
            if let activeResponseID, activeResponseID != responseID {
                throw SpeechRailRealtimeTTSFailure.responseMismatch
            }
            activeResponseID = responseID

        case .audioDelta(let responseID, _, _), .audioDone(let responseID, _):
            guard activeRequestID != nil,
                  let activeResponseID,
                  activeResponseID == responseID
            else {
                throw SpeechRailRealtimeTTSFailure.responseMismatch
            }

        case .responseDone(let responseID, _, let requestID, _, _):
            guard activeRequestID == requestID,
                  let activeResponseID,
                  activeResponseID == responseID
            else {
                throw SpeechRailRealtimeTTSFailure.responseMismatch
            }
            self.activeRequestID = nil
            self.activeResponseID = nil

        case .error(_, let requestID, _):
            if let requestID, let activeRequestID, requestID != activeRequestID {
                throw SpeechRailRealtimeTTSFailure.responseMismatch
            }

        default:
            break
        }
    }

    private func receiveValidated() async throws -> SpeechRailTTSServerEnvelope {
        let envelope: SpeechRailTTSServerEnvelope
        do {
            envelope = try SpeechRailTTSServerEnvelope.decode(
                try await transport.receiveData()
            )
        } catch let failure as SpeechRailRealtimeTTSFailure {
            throw failure
        } catch {
            throw SpeechRailRealtimeTTSFailure.connectionClosed
        }

        let expected = lastServerSequence + 1
        guard envelope.sequence == expected else {
            throw SpeechRailRealtimeTTSFailure.sequenceGap(
                expected: expected,
                actual: envelope.sequence
            )
        }
        if let serviceSessionID {
            guard serviceSessionID == envelope.sessionID else {
                throw SpeechRailRealtimeTTSFailure.invalidEnvelope
            }
        } else {
            serviceSessionID = envelope.sessionID
        }
        lastServerSequence = envelope.sequence
        return envelope
    }
}

public nonisolated struct SpeechRailTTSProviderResult: Sendable, Equatable {
    public let requestID: String
    public let responseID: String
    public let itemID: String
    public let sampleCount: Int64
    public let pcmSHA256: String
    public let voiceRevision: String?
    public let receipt: SpeechRailTTSRenderReceiptSummary
}

public nonisolated enum SpeechRailTTSRenderTerminal: Sendable, Equatable {
    case completed(SpeechRailTTSProviderResult)
    case cancelled
    case failed(SpeechRailRealtimeTTSFailure)
}

/// Verifies one current-only TTS response without retaining PCM in memory.
///
/// A completed provider response is accepted only after output_audio.done and,
/// when requested, a Render Receipt that matches the exact streamed PCM sample
/// count and SHA-256. This result is provider completion evidence only; it says
/// nothing about whether the device has audibly rendered all scheduled frames.
public nonisolated struct SpeechRailTTSRenderAccumulator {
    private let requestID: String
    private let requireReceipt: Bool
    private var responseID: String?
    private var itemID: String?
    private var hasher = SHA256()
    private var sampleCount: Int64 = 0
    private var audioDone = false
    private(set) public var terminal: SpeechRailTTSRenderTerminal?

    public init(requestID: String, requireReceipt: Bool = true) {
        self.requestID = requestID
        self.requireReceipt = requireReceipt
    }

    public mutating func observe(_ envelope: SpeechRailTTSServerEnvelope) {
        guard terminal == nil else { return }
        do {
            switch envelope.event {
            case .responseCreated(let responseID):
                guard self.responseID == nil || self.responseID == responseID else {
                    throw SpeechRailRealtimeTTSFailure.responseMismatch
                }
                self.responseID = responseID

            case .audioDelta(let responseID, let itemID, let pcm16):
                try bind(responseID: responseID, itemID: itemID)
                guard !audioDone,
                      !pcm16.isEmpty,
                      pcm16.count.isMultiple(of: MemoryLayout<Int16>.size)
                else {
                    throw SpeechRailRealtimeTTSFailure.audioChunkInvalid
                }
                hasher.update(data: pcm16)
                sampleCount += Int64(pcm16.count / MemoryLayout<Int16>.size)

            case .audioDone(let responseID, let itemID):
                try bind(responseID: responseID, itemID: itemID)
                guard !audioDone else { throw SpeechRailRealtimeTTSFailure.invalidState }
                audioDone = true

            case .responseDone(
                let responseID,
                let status,
                let requestID,
                let voiceRevision,
                let receipt
            ):
                guard requestID == self.requestID,
                      self.responseID == responseID
                else {
                    throw SpeechRailRealtimeTTSFailure.responseMismatch
                }
                switch status {
                case .cancelled:
                    terminal = .cancelled
                case .failed:
                    terminal = .failed(.providerFailed(code: receipt?.errorCode))
                case .completed:
                    guard audioDone,
                          sampleCount > 0,
                          let itemID
                    else {
                        throw SpeechRailRealtimeTTSFailure.audioStreamIncomplete
                    }
                    let digest = Self.hex(hasher.finalize())
                    guard let receipt else {
                        if requireReceipt { throw SpeechRailRealtimeTTSFailure.receiptMissing }
                        throw SpeechRailRealtimeTTSFailure.receiptMissing
                    }
                    guard receipt.requestID == self.requestID,
                          receipt.responseID == responseID,
                          receipt.status == "completed",
                          receipt.outputFormat == "pcm16",
                          receipt.sampleRate == 24_000,
                          receipt.channels == 1,
                          receipt.sampleCount == sampleCount,
                          receipt.pcmSHA256 == digest,
                          receipt.voiceRevision == voiceRevision
                    else {
                        throw SpeechRailRealtimeTTSFailure.receiptMismatch
                    }
                    terminal = .completed(
                        SpeechRailTTSProviderResult(
                            requestID: self.requestID,
                            responseID: responseID,
                            itemID: itemID,
                            sampleCount: sampleCount,
                            pcmSHA256: digest,
                            voiceRevision: voiceRevision,
                            receipt: receipt
                        )
                    )
                }

            case .error(let code, let requestID, _):
                if let requestID, requestID != self.requestID {
                    throw SpeechRailRealtimeTTSFailure.responseMismatch
                }
                terminal = .failed(.providerFailed(code: code))

            default:
                break
            }
        } catch let failure as SpeechRailRealtimeTTSFailure {
            terminal = .failed(failure)
        } catch {
            terminal = .failed(.invalidEnvelope)
        }
    }

    private mutating func bind(responseID: String, itemID: String) throws {
        guard self.responseID == responseID else {
            throw SpeechRailRealtimeTTSFailure.responseMismatch
        }
        if let currentItemID = self.itemID {
            guard currentItemID == itemID else {
                throw SpeechRailRealtimeTTSFailure.responseMismatch
            }
        } else {
            self.itemID = itemID
        }
    }

    private static func hex<D: Sequence>(_ digest: D) -> String where D.Element == UInt8 {
        digest.map { String(format: "%02x", $0) }.joined()
    }
}
