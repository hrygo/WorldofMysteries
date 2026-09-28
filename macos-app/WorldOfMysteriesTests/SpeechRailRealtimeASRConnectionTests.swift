import Foundation
import Testing
@testable import WorldOfMysteriesCore

private actor FakeSpeechRailRealtimeTransport: SpeechRailRealtimeASRTransport {
    private var openedRequests: [URLRequest] = []
    private var sentTextsStorage: [String] = []
    private var inbound: [Data] = []
    private var waiting: [CheckedContinuation<Data, any Error>] = []
    private(set) var closed = false
    private(set) var openCount = 0

    func open(_ request: URLRequest) async throws {
        openCount += 1
        openedRequests.append(request)
    }

    func sendText(_ text: String) async throws {
        sentTextsStorage.append(text)
    }

    func receiveData() async throws -> Data {
        if !inbound.isEmpty {
            return inbound.removeFirst()
        }
        return try await withCheckedThrowingContinuation { continuation in
            waiting.append(continuation)
        }
    }

    func close() async {
        closed = true
        let pending = waiting
        waiting.removeAll()
        for continuation in pending {
            continuation.resume(throwing: SpeechRailRealtimeASRFailure.connectionClosed)
        }
    }

    func push(_ json: String) {
        let data = Data(json.utf8)
        if !waiting.isEmpty {
            waiting.removeFirst().resume(returning: data)
        } else {
            inbound.append(data)
        }
    }

    func requests() -> [URLRequest] { openedRequests }
    func sentTexts() -> [String] { sentTextsStorage }
}

@Suite("SpeechRail Realtime ASR connection")
struct SpeechRailRealtimeASRConnectionTests {
    /// A service-side `session` echo.
    private func sessionJSON(
        model: String = SpeechRailRealtimeSessionConfiguration.registeredASRModel,
        language: String? = "zh",
        prompt: String? = nil,
        keywords: [String] = [],
        rate: Int = 24_000,
        formatType: String = "audio/pcm",
        task: String = "transcription",
        tts: Bool = false,
        alignment: Bool = false,
        diarization: Bool = false
    ) -> String {
        var transcription = "\"model\":\"\(model)\""
        if let language { transcription += ",\"language\":\"\(language)\"" }
        if let prompt { transcription += ",\"prompt\":\"\(prompt)\"" }
        if !keywords.isEmpty {
            transcription += ",\"keywords\":[\(keywords.map { "\"\($0)\"" }.joined(separator: ","))]"
        }
        let speechrail = """
        {"task":"\(task)","tts":{"enabled":\(tts)},"alignment":{"enabled":\(alignment)}\
        ,"diarization":{"enabled":\(diarization)}}
        """
        return """
        {"id":"sess-1","type":"transcription","audio":{"input":{"format":\
        {"type":"\(formatType)","rate":\(rate)},"transcription":{\(transcription)},\
        "turn_detection":null,"speechrail":\(speechrail)}},"speechrail":\(speechrail)}
        """
    }

    private func server(
        _ type: String,
        sequence: Int,
        eventID: String,
        sessionID: String = "sess-1",
        extra: String = ""
    ) -> String {
        let suffix = extra.isEmpty ? "" : ",\(extra)"
        return #"{"type":"\#(type)","event_id":"\#(eventID)","session_id":"\#(sessionID)","sequence":\#(sequence)\#(suffix)}"#
    }

    private func primeHandshake(
        _ transport: FakeSpeechRailRealtimeTransport,
        model: String = SpeechRailRealtimeSessionConfiguration.registeredASRModel,
        language: String? = "zh"
    ) async {
        await transport.push(
            server("session.created", sequence: 1, eventID: "s1",
                   extra: "\"session\":\(sessionJSON(model: model))")
        )
        await transport.push(
            server("session.updated", sequence: 2, eventID: "s2",
                   extra: "\"session\":\(sessionJSON(model: model, language: language))")
        )
    }

    @Test("The handshake proves the exact effective configuration before the turn starts")
    func handshakeProvesEffectiveConfiguration() async throws {
        let transport = FakeSpeechRailRealtimeTransport()
        let echoed = sessionJSON(
            model: "whisper-1",
            prompt: "只转写玩家说话",
            keywords: ["克莱恩"]
        )
        let created = server(
            "session.created",
            sequence: 1,
            eventID: "s1",
            extra: "\"session\":\(echoed)"
        )
        let updated = server(
            "session.updated",
            sequence: 2,
            eventID: "s2",
            extra: "\"session\":\(echoed)"
        )
        await transport.push(created)
        await transport.push(updated)
        let configuration = SpeechRailRealtimeASRConfiguration(
            apiKey: "local-secret",
            model: "whisper-1",
            language: "zh",
            prompt: "只转写玩家说话",
            keywords: ["克莱恩"]
        )
        let connection = SpeechRailRealtimeASRConnection(
            configuration: configuration,
            transport: transport
        )

        let info = try await connection.connect()
        #expect(info.serviceSessionID == "sess-1")
        #expect(info.lastServerSequence == 2)
        #expect(info.sampleRate == 24_000)
        #expect(info.session == configuration.effectiveSession)
        #expect(!configuration.description.contains("local-secret"))

        let requests = await transport.requests()
        #expect(requests.count == 1)
        #expect(requests[0].url?.absoluteString == "ws://127.0.0.1:8201/v1/realtime?model=whisper-1")
        #expect(requests[0].value(forHTTPHeaderField: "Authorization") == "Bearer local-secret")

        let sent = await transport.sentTexts()
        #expect(sent.count == 1)
        let object = try #require(
            try JSONSerialization.jsonObject(with: Data(sent[0].utf8)) as? [String: Any]
        )
        #expect(object["type"] as? String == "session.update")
        let session = try #require(object["session"] as? [String: Any])
        #expect(session["type"] as? String == "transcription")

        // The wire format moved into audio.input and the flat 16 kHz fields are
        // gone; this is the single place the 24 kHz fact is written.
        let audio = try #require(session["audio"] as? [String: Any])
        let input = try #require(audio["input"] as? [String: Any])
        let format = try #require(input["format"] as? [String: Any])
        #expect(format["type"] as? String == "audio/pcm")
        #expect(format["rate"] as? Int == 24_000)
        #expect(input["turn_detection"] is NSNull)
        #expect(session["input_audio_format"] == nil)
        #expect(session["input_audio_transcription"] == nil)
        #expect(session["turn_detection"] == nil)

        let transcription = try #require(input["transcription"] as? [String: Any])
        #expect(transcription["model"] as? String == "whisper-1")
        #expect(transcription["language"] as? String == "zh")

        let speechrail = try #require(input["speechrail"] as? [String: Any])
        #expect(speechrail["task"] as? String == "transcription")
        #expect((speechrail["tts"] as? [String: Any])?["enabled"] as? Bool == false)
        #expect((speechrail["alignment"] as? [String: Any])?["enabled"] as? Bool == false)
        #expect((speechrail["diarization"] as? [String: Any])?["enabled"] as? Bool == false)
    }

    @Test("A partial configuration echo cannot start a turn")
    func partialConfigurationEchoRejected() async {
        let transport = FakeSpeechRailRealtimeTransport()
        await primeHandshake(transport)
        let connection = SpeechRailRealtimeASRConnection(
            configuration: SpeechRailRealtimeASRConfiguration(
                model: "whisper-1",
                prompt: "只转写玩家说话"
            ),
            transport: transport
        )
        do {
            _ = try await connection.connect()
            Issue.record("A partial configuration echo was accepted")
        } catch let failure as SpeechRailRealtimeASRFailure {
            #expect(failure == .sessionConfigurationMismatch)
        } catch {
            Issue.record("Unexpected error: \(error)")
        }
    }

    @Test("A service echo with a different wire rate fails the handshake")
    func wireRateMismatchRejected() async {
        let transport = FakeSpeechRailRealtimeTransport()
        await transport.push(
            server("session.created", sequence: 1, eventID: "s1",
                   extra: "\"session\":\(sessionJSON())")
        )
        await transport.push(
            server("session.updated", sequence: 2, eventID: "s2",
                   extra: "\"session\":\(sessionJSON(rate: 16_000))")
        )
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        do {
            _ = try await connection.connect()
            Issue.record("A 16 kHz echo was accepted by a 24 kHz client")
        } catch let failure as SpeechRailRealtimeASRFailure {
            #expect(failure == .invalidEnvelope)
        } catch {
            Issue.record("Unexpected error: \(error)")
        }
    }

    @Test("An echo that re-enables TTS fails the handshake")
    func ttsReEnableRejected() async {
        let transport = FakeSpeechRailRealtimeTransport()
        await transport.push(
            server("session.created", sequence: 1, eventID: "s1",
                   extra: "\"session\":\(sessionJSON())")
        )
        await transport.push(
            server("session.updated", sequence: 2, eventID: "s2",
                   extra: "\"session\":\(sessionJSON(tts: true))")
        )
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        do {
            _ = try await connection.connect()
            Issue.record("A TTS-enabled echo was accepted")
        } catch let failure as SpeechRailRealtimeASRFailure {
            #expect(failure == .invalidEnvelope)
        } catch {
            Issue.record("Unexpected error: \(error)")
        }
    }

    @Test("Service defaults on session.created do not fail the handshake")
    func serviceDefaultsOnCreatedAccepted() async throws {
        // The real service opens the socket with its own defaults — task
        // `conversation` and the canonical model id — before this client has
        // sent anything. Only the `session.updated` that follows proves the
        // applied configuration, so `created` must be read for shape only.
        let transport = FakeSpeechRailRealtimeTransport()
        let registered = SpeechRailRealtimeSessionConfiguration.registeredASRModel
        let created = server(
            "session.created",
            sequence: 1,
            eventID: "s1",
            extra: "\"session\":\(sessionJSON(model: registered, language: nil, task: "conversation"))"
        )
        let updated = server(
            "session.updated",
            sequence: 2,
            eventID: "s2",
            extra: "\"session\":\(sessionJSON(model: registered))"
        )
        await transport.push(
            created
        )
        await transport.push(updated)
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        let info = try await connection.connect()
        #expect(info.serviceSessionID == "sess-1")
        #expect(info.session.model == registered)
    }

    @Test("An updated echo that resolves to another task fails the handshake")
    func updatedTaskMismatchRejected() async {
        let transport = FakeSpeechRailRealtimeTransport()
        await transport.push(
            server("session.created", sequence: 1, eventID: "s1",
                   extra: "\"session\":\(sessionJSON())")
        )
        await transport.push(
            server("session.updated", sequence: 2, eventID: "s2",
                   extra: "\"session\":\(sessionJSON(task: "caption"))")
        )
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        do {
            _ = try await connection.connect()
            Issue.record("An echo that resolved to another task was accepted")
        } catch let failure as SpeechRailRealtimeASRFailure {
            #expect(failure == .invalidEnvelope)
        } catch {
            Issue.record("Unexpected error: \(error)")
        }
    }

    @Test("Append, commit and the barrier re-send are ordered and use text JSON events")
    func orderedClientEvents() async throws {
        let transport = FakeSpeechRailRealtimeTransport()
        await primeHandshake(transport)
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        _ = try await connection.connect()

        _ = try await connection.appendPCM16(Data([0, 0, 1, 0]))
        _ = try await connection.commit()
        _ = try await connection.resendSessionUpdate()

        let sent = await transport.sentTexts()
        #expect(sent.count == 4)
        var types: [String] = []
        var sessions: [[String: Any]] = []
        for text in sent {
            let object = try #require(
                try JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any]
            )
            types.append(try #require(object["type"] as? String))
            if let session = object["session"] as? [String: Any] {
                sessions.append(session)
            }
        }
        #expect(types == [
            "session.update",
            "input_audio_buffer.append",
            "input_audio_buffer.commit",
            "session.update",
        ])
        // The barrier must be the same configuration as the handshake, so the
        // service cannot answer the barrier from a different session.
        #expect(sessions.count == 2)
        let barrierData = try JSONSerialization.data(
            withJSONObject: sessions[1], options: [.sortedKeys]
        )
        let handshakeData = try JSONSerialization.data(
            withJSONObject: sessions[0], options: [.sortedKeys]
        )
        #expect(barrierData == handshakeData)
    }

    @Test("The first server sequence may be 0 or 1")
    func firstSequenceTolerance() async throws {
        for first in [0, 1] {
            let transport = FakeSpeechRailRealtimeTransport()
            await transport.push(
                server("session.created", sequence: first, eventID: "s1",
                       extra: "\"session\":\(sessionJSON())")
            )
            await transport.push(
                server("session.updated", sequence: first + 1, eventID: "s2",
                       extra: "\"session\":\(sessionJSON())")
            )
            let connection = SpeechRailRealtimeASRConnection(transport: transport)
            let info = try await connection.connect()
            #expect(info.lastServerSequence == Int64(first + 1))
        }
    }

    @Test("A first sequence beyond 1 is refused rather than tolerated as a gap")
    func implausibleFirstSequenceRejected() async {
        let transport = FakeSpeechRailRealtimeTransport()
        await transport.push(
            server("session.created", sequence: 7, eventID: "s1",
                   extra: "\"session\":\(sessionJSON())")
        )
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        do {
            _ = try await connection.connect()
            Issue.record("An out-of-band first sequence was accepted")
        } catch let failure as SpeechRailRealtimeASRFailure {
            #expect(failure == .sequenceGap(expected: 1, actual: 7))
        } catch {
            Issue.record("Unexpected error: \(error)")
        }
    }

    @Test("A sequence gap fails before a partial turn can be consumed")
    func sequenceGap() async throws {
        let transport = FakeSpeechRailRealtimeTransport()
        await primeHandshake(transport)
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        _ = try await connection.connect()
        await transport.push(
            server(
                "conversation.item.input_audio_transcription.completed",
                sequence: 4,
                eventID: "gap",
                extra: #""item_id":"a","content_index":0,"transcript":"x""#
            )
        )

        do {
            _ = try await connection.receiveEnvelope()
            Issue.record("Sequence gap was accepted")
        } catch let failure as SpeechRailRealtimeASRFailure {
            #expect(failure == .sequenceGap(expected: 3, actual: 4))
        } catch {
            Issue.record("Unexpected error: \(error)")
        }
    }

    @Test("A non-zero content index is refused instead of read as the primary content")
    func nonPrimaryContentIndexRejected() async throws {
        let transport = FakeSpeechRailRealtimeTransport()
        await primeHandshake(transport)
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        _ = try await connection.connect()
        await transport.push(
            server(
                "conversation.item.input_audio_transcription.completed",
                sequence: 3,
                eventID: "e3",
                extra: #""item_id":"a","content_index":1,"transcript":"x""#
            )
        )
        do {
            _ = try await connection.receiveEnvelope()
            Issue.record("A non-primary content index was accepted")
        } catch let failure as SpeechRailRealtimeASRFailure {
            #expect(failure == .invalidEnvelope)
        } catch {
            Issue.record("Unexpected error: \(error)")
        }
    }

    @Test("Remote plaintext SpeechRail is rejected before a socket is opened")
    func remotePlaintextRejected() async {
        let transport = FakeSpeechRailRealtimeTransport()
        let configuration = SpeechRailRealtimeASRConfiguration(
            baseURL: URL(string: "http://speech.example.test:8201/v1")!,
            allowRemote: true
        )
        let connection = SpeechRailRealtimeASRConnection(
            configuration: configuration,
            transport: transport
        )

        do {
            _ = try await connection.connect()
            Issue.record("Remote plaintext endpoint was accepted")
        } catch let failure as SpeechRailRealtimeASRFailure {
            #expect(failure == .invalidConfiguration)
        } catch {
            Issue.record("Unexpected error: \(error)")
        }
        #expect(await transport.requests().isEmpty)
    }

    @Test("No API key means no Authorization header rather than an empty bearer")
    func absentAPIKeySendsNoAuthorization() async throws {
        let transport = FakeSpeechRailRealtimeTransport()
        await primeHandshake(transport)
        let connection = SpeechRailRealtimeASRConnection(
            configuration: SpeechRailRealtimeASRConfiguration(apiKey: "   "),
            transport: transport
        )
        _ = try await connection.connect()
        #expect(await transport.requests()[0].value(forHTTPHeaderField: "Authorization") == nil)
    }

    @Test("PCM append rejects empty odd and oversized frames locally")
    func invalidPCMFrames() async throws {
        let transport = FakeSpeechRailRealtimeTransport()
        await primeHandshake(transport)
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        _ = try await connection.connect()

        for data in [
            Data(),
            Data([0]),
            Data(repeating: 0, count: SpeechRailRealtimeASRConnection.maximumAppendBytes + 2),
        ] {
            do {
                _ = try await connection.appendPCM16(data)
                Issue.record("Invalid PCM frame was accepted")
            } catch let failure as SpeechRailRealtimeASRFailure {
                #expect(failure == .audioFrameInvalid)
            }
        }
    }

    @Test("A turn collects events from a single reader without reopening the socket")
    func singleReaderPerConnection() async throws {
        let transport = FakeSpeechRailRealtimeTransport()
        await primeHandshake(transport)
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        _ = try await connection.connect()

        async let first = connection.receiveEnvelope()
        async let second = connection.receiveEnvelope()
        await transport.push(
            server("conversation.item.input_audio_transcription.delta",
                   sequence: 3, eventID: "d3",
                   extra: #""item_id":"a","content_index":0,"delta":"你""#)
        )
        await transport.push(
            server("conversation.item.input_audio_transcription.delta",
                   sequence: 4, eventID: "d4",
                   extra: #""item_id":"a","content_index":0,"delta":"好""#)
        )
        let received = try await [first, second]
        // 原断言依赖 async let 的调度顺序，不代表产品契约；本次调整的是测试的确定性，不改变被测代码。
        #expect(received.map(\.sequence).sorted() == [3, 4])
        #expect(received.map(\.eventID).sorted() == ["d3", "d4"])
        let receivedDeltaTexts = received.compactMap { envelope -> String? in
            guard case let .partial(itemID, delta) = envelope.event,
                  itemID == "a"
            else {
                return nil
            }
            return delta
        }
        #expect(receivedDeltaTexts.sorted() == ["你", "好"])
        #expect(await transport.openCount == 1)
    }
}
