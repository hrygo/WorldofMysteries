// Real end-to-end voice turn: microphone -> SpeechRail ASR -> Engine commit ->
// live model -> sealed SpeechUnit -> SpeechRail TTS -> media socket -> speaker.
//
// Every component on the path is production code. The only test-only pieces are
// the synthesized stimulus (played through the system default output so the
// default microphone can hear it) and the RMS/peak measurement taken over the
// PCM that actually crossed the media socket.
//
// Device policy: nothing here selects an input or an output. Both come from
// `AVAudioEngine`'s system defaults, so the same run is valid on built-in
// hardware, a headset, or a speakerphone.

import AVFoundation
import Foundation

private enum E2EFailure: Error, CustomStringConvertible {
    case missing(String)
    var description: String {
        switch self { case .missing(let what): return what }
    }
}

private func require<T>(_ value: T?, _ what: String) throws -> T {
    guard let value else { throw E2EFailure.missing(what) }
    return value
}

/// Phase marker. Progress goes to stderr so the single stdout fact line stays
/// machine-readable even when a phase hangs.
private func step(_ name: String) {
    FileHandle.standardError.write(Data(("E2E-STEP " + name + "\n").utf8))
}

private func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data(("E2E-FAIL " + message + "\n").utf8))
    exit(1)
}

private struct Facts: Codable {
    var transcript: String
    var committedTurn: Int
    var storyRevision: Int
    var discoveredClues: [String]
    var deliveryState: String
    var deliveryReason: String?
    var speechUnitID: String?
    var voiceID: String?
    var mediaFrames: Int
    var mediaBytes: Int
    var pcmPeak: Int
    var pcmRMSMilli: Int
    var sampleRate: Int
    var playedToDevice: Bool
    var playbackTerminal: String
    var healthModelReady: Bool
    var healthVoiceReady: Bool
}

private func emit(_ facts: Facts) {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    guard let data = try? encoder.encode(facts) else { fail("could not encode facts") }
    print("E2E " + String(decoding: data, as: UTF8.self))
}

/// A media transport decorator that measures exactly what crossed the socket.
private actor MeasuringTransport: MediaFrameTransport {
    private let inner: any MediaFrameTransport
    private var frames = 0
    private var bytes = 0
    private var peak = 0
    private var sumSquares: UInt64 = 0
    private var samples: UInt64 = 0

    init(_ inner: any MediaFrameTransport) { self.inner = inner }

    func snapshot() -> (frames: Int, bytes: Int, peak: Int, rmsMilli: Int) {
        guard samples > 0 else { return (frames, bytes, peak, 0) }
        let mean = sumSquares / samples
        return (frames, bytes, peak, Int(Double(mean).squareRoot()))
    }

    func connect(path: String, timeout: TimeInterval) async throws {
        try await inner.connect(path: path, timeout: timeout)
    }

    func send(_ frame: MediaFrame) async throws { try await inner.send(frame) }

    nonisolated func frameStream() -> AsyncThrowingStream<MediaFrame, any Error> {
        let inner = self.inner
        let recorder = self
        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    for try await frame in inner.frameStream() {
                        await recorder.record(frame.payload)
                        continuation.yield(frame)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    func close() async { await inner.close() }

    private func record(_ payload: Data) {
        frames += 1
        bytes += payload.count
        let ordered = [UInt8](payload)
        var index = 0
        while index + 1 < ordered.count {
            let value = Int(Int16(bitPattern: UInt16(ordered[index]) | UInt16(ordered[index + 1]) << 8))
            let magnitude = abs(value)
            if magnitude > peak { peak = magnitude }
            sumSquares &+= UInt64(magnitude * magnitude)
            samples += 1
            index += 2
        }
    }
}

/// Only the keys the Engine actually reads cross into the child process.
private let forwardedEnvironment: [String: String] = {
    var result: [String: String] = [:]
    let environment = ProcessInfo.processInfo.environment
    for key in ["SPEECHRAIL_BASE_URL", "SPEECHRAIL_API_KEY", "OPENAI_AUDIO_BASE_URL",
                "OPENAI_AUDIO_API_KEY", "WOM_MODEL_BASE_URL", "WOM_MODEL_NAME",
                "WOM_MODEL_API_KEY", "WOM_MODEL_EXTRA_BODY", "WOM_MODEL_TIMEOUT"] {
        if let value = environment[key], !value.isEmpty { result[key] = value }
    }
    return result
}()

/// Synthesize the spoken stimulus with SpeechRail and play it out the system
/// default speaker, so the system default microphone hears real speech.
private func speakStimulus(text: String) async throws {
    var request = URLRequest(url: URL(string: "http://127.0.0.1:8201/v1/audio/speech")!)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    if let key = ProcessInfo.processInfo.environment["SPEECHRAIL_API_KEY"], !key.isEmpty {
        request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
    }
    request.httpBody = try JSONSerialization.data(withJSONObject: [
        "model": "tts-1", "voice": "serena", "input": text,
        "response_format": "wav",
    ])
    let box = TaskBox()
    let task = URLSession.shared.dataTask(with: request) { data, response, error in
        if let error { box.fail(error); return }
        guard let http = response as? HTTPURLResponse, let data else {
            box.fail(E2EFailure.missing("empty synthesis response")); return
        }
        guard (200..<300).contains(http.statusCode) else {
            // Surface the provider's own status, never its body: it may quote
            // the request text back.
            box.fail(E2EFailure.missing("synthesis returned HTTP \(http.statusCode)"))
            return
        }
        box.succeed(data)
    }
    task.resume()
    let wav = try await box.data
    step("stimulus.synthesized")

    let file = try AVAudioFile(forReading: try writeTemporary(wav))
    step("stimulus.file.opened")
    let player = AVAudioPlayerNode()
    let engine = AVAudioEngine()
    engine.attach(player)
    engine.connect(player, to: engine.outputNode, format: file.processingFormat)
    engine.prepare()
    try engine.start()
    step("stimulus.engine.started")
    // `scheduleFile(_:at:)`'s async overload and `player.isPlaying` are both
    // unusable here: the async overload never returns on this toolchain, and
    // `isPlaying` stays true after the data has been played, so polling it
    // never terminates. The data-played-back callback is the only signal that
    // actually means "the speaker finished the sentence".
    let fence = PlaybackFence()
    player.scheduleFile(file, at: nil, completionCallbackType: .dataPlayedBack) { _ in
        fence.reach()
    }
    player.play()
    step("stimulus.playing")
    // The callback is the signal, but a wedged audio device must surface as an
    // honest failure rather than as a 10-minute hang.
    let budget = UInt64(file.length) / UInt64(file.processingFormat.sampleRate) + 30
    try await fence.wait(seconds: budget)
    step("stimulus.playback.finished")
    player.stop()
    engine.stop()
}

/// One-shot fence signalled by the player node's data-played-back callback.
private final class PlaybackFence: @unchecked Sendable {
    private let lock = NSLock()
    private var continuation: CheckedContinuation<Void, any Error>?
    private var reached = false

    func reach() {
        lock.lock()
        defer { lock.unlock() }
        reached = true
        continuation?.resume()
        continuation = nil
    }

    func wait(seconds: UInt64) async throws {
        try await withCheckedThrowingContinuation { continuation in
            lock.lock()
            if reached {
                lock.unlock()
                continuation.resume()
                return
            }
            self.continuation = continuation
            lock.unlock()
            Task {
                try await Task.sleep(nanoseconds: seconds * 1_000_000_000)
                self.fail(E2EFailure.missing("stimulus playback did not finish in time"))
            }
        }
    }

    private func fail(_ error: any Error) {
        lock.lock()
        defer { lock.unlock() }
        guard !reached, let continuation else { return }
        self.continuation = nil
        continuation.resume(throwing: error)
    }
}

private final class TaskBox: @unchecked Sendable {
    private let lock = NSLock()
    private var continuation: CheckedContinuation<Data, Error>?
    private var result: Result<Data, Error>?

    func succeed(_ data: Data) { finish(.success(data)) }
    func fail(_ error: Error) { finish(.failure(error)) }

    var data: Data {
        get async throws {
            try await withCheckedThrowingContinuation { continuation in
                lock.lock()
                if let result {
                    lock.unlock()
                    continuation.resume(with: result)
                    return
                }
                self.continuation = continuation
                lock.unlock()
            }
        }
    }

    private func finish(_ value: Result<Data, Error>) {
        lock.lock()
        guard result == nil else { lock.unlock(); return }
        result = value
        let pending = continuation
        continuation = nil
        lock.unlock()
        pending?.resume(with: value)
    }
}

private func writeTemporary(_ data: Data) throws -> URL {
    let url = FileManager.default.temporaryDirectory
        .appendingPathComponent("wom-e2e-stimulus-\(UUID().uuidString).wav")
    try data.write(to: url)
    return url
}

@MainActor
private func run(_ args: [String]) async throws {
    let environment = ProcessInfo.processInfo.environment
    let spokenLine = try require(environment["WOM_E2E_SPOKEN"], "WOM_E2E_SPOKEN is not set")
    let voiceID = try require(environment["WOM_E2E_VOICE_ID"], "WOM_E2E_VOICE_ID is not set")

    let manager = EngineProcessManager(configuration: EngineLaunchConfiguration(
        executableURL: URL(fileURLWithPath: args[1]),
        moduleDirectory: URL(fileURLWithPath: args[2]),
        runtimeRoot: URL(fileURLWithPath: args[3]),
        dataRoot: URL(fileURLWithPath: args[4]),
        voiceId: voiceID,
        environment: forwardedEnvironment
    ))
    let app = AppState(ipcClient: EngineIPCClient(requestTimeout: 180), processManager: manager)
    step("engine.start")
    try await app.startAndConnect()
    step("engine.connected")

    guard let capabilities = app.engineHandshake?.capabilities else {
        fail("no handshake; state=\(String(describing: app.connectionState)) "
             + "error=\(app.connectionError ?? "none") health=\(app.engineHealth == nil ? "nil" : "set")")
    }
    guard capabilities.contains("story.turn.submit"), capabilities.contains("media.open"),
          capabilities.contains("voice.render") else {
        fail("engine did not advertise the live voice path: \(capabilities.sorted())")
    }
    let health = try require(app.engineHealth, "no engine health")
    let client = app.ipcClient

    // 1. Real speech in: a synthesized sentence leaves the default speaker and
    //    is transcribed by the production ASR stack on the default microphone.
    step("asr.start")
    let microphone = try MicrophoneCaptureSession()
    let voiceSession = VoiceInputPTTSession(
        connection: SpeechRailRealtimeASRConnection(
            configuration: SpeechRailRealtimeASRConfiguration(
                apiKey: environment["SPEECHRAIL_API_KEY"])),
        microphone: microphone
    )
    _ = try await voiceSession.start()
    step("asr.capturing")
    // Replay the stimulus while the microphone is actually open.
    try await speakStimulus(text: spokenLine)
    step("asr.finalizing")
    let terminal = await voiceSession.finish()
    step("asr.done")
    guard case .transcript(let final) = terminal else { fail("ASR produced no transcript") }
    let transcript = final.text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !transcript.isEmpty else { fail("ASR produced an empty transcript") }

    // 2. Real commit: the Engine interprets the transcript with the live model,
    //    resolves it deterministically and commits the turn.
    step("story.open")
    try await app.storyModel.startStory()
    step("story.opened")
    let view = try require(app.storyModel.view, "no committed session view")
    let committed = try await client.storyTurnSubmit(try StoryTurnSubmitRequestDTO(
        sessionId: view.sessionId,
        inputTurnId: UUID().uuidString,
        rawInput: transcript,
        inputMode: .voice,
        expectedStoryRevision: view.storyRevision,
        expectedStoreRevision: view.observedStoreRevision
    ))
    step("turn.committed")
    let delivery = try require(committed.delivery, "commit returned no delivery state")
    guard delivery.state == .ready else {
        emit(Facts(transcript: transcript, committedTurn: committed.session.turn,
                   storyRevision: committed.session.storyRevision,
                   discoveredClues: committed.session.discoveredClues.map(\.displayName),
                   deliveryState: delivery.state.rawValue, deliveryReason: delivery.reason,
                   speechUnitID: nil, voiceID: nil, mediaFrames: 0, mediaBytes: 0,
                   pcmPeak: 0, pcmRMSMilli: 0, sampleRate: 24_000, playedToDevice: false,
                   playbackTerminal: "not-started",
                   healthModelReady: health.modelReady, healthVoiceReady: health.voiceReady))
        fail("delivery unavailable: \(delivery.reason ?? "unknown")")
    }
    let recipe = try require(delivery.renderRecipe, "ready delivery without a render recipe")

    // 3. Real audio out: verified SpeechRail PCM over the media socket into the
    //    system default output device.
    let grant = try await client.openMedia(
        direction: .engineToApp,
        generation: 1,
        format: MediaFormat(codec: "pcm_s16le", sampleRate: 24_000, channels: 1))
    _ = try await client.renderVoice(VoiceRenderControlRequestDTO(
        recipe: recipe, mediaStreamId: grant.streamId, generation: Int(grant.generation)))

    let transport = MeasuringTransport(UnixMediaFrameTransport())
    let playbackSession = EngineMediaPlaybackSession(
        grant: grant,
        transport: transport,
        playback: NativePlaybackActor(backend: AVAudioEnginePCMPlaybackBackend()))
    step("media.playing")
    let playbackTerminal = await playbackSession.run()
    step("media.done")
    let measured = await transport.snapshot()

    var playedToDevice = false
    let terminalName: String
    switch playbackTerminal {
    case .ended:
        playedToDevice = true
        terminalName = "ended"
    case .cancelled:
        terminalName = "cancelled"
    case .failed(let failure):
        terminalName = "failed: \(failure)"
    }
    step("media.terminal.\(terminalName)")

    await app.shutdown()
    emit(Facts(
        transcript: transcript,
        committedTurn: committed.session.turn,
        storyRevision: committed.session.storyRevision,
        discoveredClues: committed.session.discoveredClues.map(\.displayName),
        deliveryState: delivery.state.rawValue,
        deliveryReason: nil,
        speechUnitID: recipe.speechUnitId,
        voiceID: recipe.voiceId,
        mediaFrames: measured.frames,
        mediaBytes: measured.bytes,
        pcmPeak: measured.peak,
        pcmRMSMilli: measured.rmsMilli,
        sampleRate: 24_000,
        playedToDevice: playedToDevice,
        playbackTerminal: terminalName,
        healthModelReady: health.modelReady,
        healthVoiceReady: health.voiceReady
    ))
}

@main
private enum VoiceTurnE2EDriver {
    static func main() async throws {
        let arguments = CommandLine.arguments
        guard arguments.count >= 5 else {
            fail("usage: driver <python> <engine-dir> <runtime> <data-root>")
        }
        do {
            try await run(arguments)
        } catch {
            fail("\(error)")
        }
    }
}
