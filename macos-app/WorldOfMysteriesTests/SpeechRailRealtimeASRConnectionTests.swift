import Foundation
import Testing
@testable import WorldOfMysteriesCore

private actor FakeSpeechRailRealtimeTransport: SpeechRailRealtimeASRTransport {
    private var openedRequests: [URLRequest] = []
    private var sentTextsStorage: [String] = []
    private var inbound: [Data] = []
    private var waiting: [CheckedContinuation<Data, any Error>] = []
    private(set) var closed = false

    func open(_ request: URLRequest) async throws {
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

    private func primeHandshake(_ transport: FakeSpeechRailRealtimeTransport) async {
        await transport.push(server("session.created", sequence: 1, eventID: "s1"))
        await transport.push(server("conversation.created", sequence: 2, eventID: "s2"))
        await transport.push(server("session.updated", sequence: 3, eventID: "s3"))
    }

    @Test("Connection uses current nested transcription session and redacts API key")
    func currentSessionConfiguration() async throws {
        let transport = FakeSpeechRailRealtimeTransport()
        await primeHandshake(transport)
        let configuration = SpeechRailRealtimeASRConfiguration(
            apiKey: "local-secret",
            model: "gpt-4o-transcribe",
            sampleRate: 24_000,
            language: "zh",
            prompt: "只转写玩家说话",
            keywords: ["克莱恩", "源堡"]
        )
        let connection = SpeechRailRealtimeASRConnection(
            configuration: configuration,
            transport: transport
        )

        let info = try await connection.connect()
        #expect(info.serviceSessionID == "sess-1")
        #expect(info.lastServerSequence == 3)
        #expect(info.sampleRate == 24_000)
        #expect(!configuration.description.contains("local-secret"))

        let requests = await transport.requests()
        #expect(requests.count == 1)
        #expect(requests[0].url?.absoluteString == "ws://127.0.0.1:8201/v1/realtime?model=gpt-4o-transcribe")
        #expect(requests[0].value(forHTTPHeaderField: "Authorization") == "Bearer local-secret")

        let sent = await transport.sentTexts()
        #expect(sent.count == 1)
        let data = Data(sent[0].utf8)
        let object = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        let session = try #require(object["session"] as? [String: Any])
        #expect(session["type"] as? String == "transcription")
        let audio = try #require(session["audio"] as? [String: Any])
        let input = try #require(audio["input"] as? [String: Any])
        let format = try #require(input["format"] as? [String: Any])
        #expect(format["type"] as? String == "audio/pcm")
        #expect(format["rate"] as? Int == 24_000)
        let transcription = try #require(input["transcription"] as? [String: Any])
        #expect(transcription["model"] as? String == "gpt-4o-transcribe")
        #expect(transcription["language"] as? String == "zh")
        #expect(input["turn_detection"] is NSNull)
    }

    @Test("Append commit clear remain ordered and use text JSON events")
    func orderedClientEvents() async throws {
        let transport = FakeSpeechRailRealtimeTransport()
        await primeHandshake(transport)
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        _ = try await connection.connect()

        _ = try await connection.appendPCM16(Data([0, 0, 1, 0]))
        _ = try await connection.commit()
        _ = try await connection.clear()

        let sent = await transport.sentTexts()
        #expect(sent.count == 4)
        let types = try sent.map { text -> String in
            let object = try #require(
                try JSONSerialization.jsonObject(with: Data(text.utf8)) as? [String: Any]
            )
            return try #require(object["type"] as? String)
        }
        #expect(types == [
            "session.update",
            "input_audio_buffer.append",
            "input_audio_buffer.commit",
            "input_audio_buffer.clear",
        ])
    }

    @Test("Connection sequence validation feeds the turn assembler without inventing ordering")
    func receiveSequenceAndAssembly() async throws {
        let transport = FakeSpeechRailRealtimeTransport()
        await primeHandshake(transport)
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        let info = try await connection.connect()
        var assembler = InputTurnAssembler(
            connectionEpoch: info.connectionEpoch,
            startingSequence: info.lastServerSequence
        )
        try assembler.beginFinalization()

        await transport.push(
            server(
                "input_audio_buffer.committed",
                sequence: 4,
                eventID: "e4",
                extra: #""item_id":"a""#
            )
        )
        await transport.push(
            server(
                "conversation.item.input_audio_transcription.completed",
                sequence: 5,
                eventID: "e5",
                extra: #""item_id":"a","transcript":"先观察""#
            )
        )
        await transport.push(
            server("input_audio_buffer.cleared", sequence: 6, eventID: "e6")
        )

        for _ in 0..<3 {
            let envelope = try await connection.receiveEnvelope()
            assembler.observe(envelope, connectionEpoch: info.connectionEpoch)
        }

        guard case .transcript(let final)? = assembler.terminalResult else {
            Issue.record("Expected a complete transcript")
            return
        }
        #expect(final.text == "先观察")
    }

    @Test("A service sequence gap fails before a partial turn can be consumed")
    func sequenceGap() async throws {
        let transport = FakeSpeechRailRealtimeTransport()
        await primeHandshake(transport)
        let connection = SpeechRailRealtimeASRConnection(transport: transport)
        _ = try await connection.connect()
        await transport.push(
            server(
                "input_audio_buffer.committed",
                sequence: 5,
                eventID: "gap",
                extra: #""item_id":"a""#
            )
        )

        do {
            _ = try await connection.receiveEnvelope()
            Issue.record("Sequence gap was accepted")
        } catch let failure as SpeechRailRealtimeASRFailure {
            #expect(failure == .sequenceGap(expected: 4, actual: 5))
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
}
