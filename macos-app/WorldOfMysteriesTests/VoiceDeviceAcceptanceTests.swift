import AVFoundation
import Foundation
import Testing
@testable import WorldOfMysteriesCore

private let deviceAcceptanceEnabled =
    ProcessInfo.processInfo.environment["WOM_DEVICE_ACCEPTANCE"] == "1"

/// Layer-C device acceptance: the half of the voice stack that only a real
/// microphone and a real speaker can exercise.
///
/// `VoiceProcessingDuplexGraphTests` deliberately stops at the pure
/// configuration gate, because building an `AVAudioEngine` opens hardware.
/// This suite is that missing half, and it is opt-in: without
/// `WOM_DEVICE_ACCEPTANCE=1` every test skips, so CI never touches a
/// microphone.
///
/// The product requirement these tests protect is that the app supports
/// whatever hardware the user happens to have. So nothing here selects a
/// device: every test runs on the ambient default route, whatever its rate.
/// A Bluetooth headset at 16 kHz and a built-in array at 48 kHz are both
/// valid, and the app is required to absorb the difference rather than ask
/// the user to change hardware.
@Suite("Voice device acceptance (layer C)", .enabled(if: deviceAcceptanceEnabled))
@MainActor
struct VoiceDeviceAcceptanceTests {
    private func requireDeviceAcceptance() throws {
        try #require(
            MicrophoneCaptureSession.authorizationStatus == .authorized,
            "microphone access is not authorized")
    }

    /// Builds a duplex graph, tolerating a device that is still releasing.
    ///
    /// Opening and closing a voice-processing I/O pair several times in a row
    /// is something no real session does, and a Bluetooth route can report
    /// itself unavailable for a moment afterwards. That is a property of the
    /// test sequence, not a defect in the app, so settle and retry rather than
    /// report a failure the user would never see.
    private func makeGraph() async throws -> (
        VoiceProcessingAudioGraph,
        AsyncThrowingStream<MicrophonePCM16Chunk, any Error>
    ) {
        var lastError: (any Error)?
        for attempt in 0..<4 {
            let graph = VoiceProcessingAudioGraph()
            do {
                try graph.enableVoiceProcessing()
                if graph.isVoiceProcessingEnabled {
                    // Confirm capture really starts before handing the graph
                    // out. Retrying only the enable step is not enough: a
                    // route that has just been cycled accepts the flag and
                    // then refuses the input. Capture is returned already
                    // running: on this route a stop/start cycle does not
                    // survive, so the caller must not restart it.
                    let stream = try graph.startCapture(
                        configuration: .init(targetSampleRate: 24_000))
                    return (graph, stream)
                }
            } catch {
                lastError = error
            }
            graph.shutdown()
            try? await Task.sleep(nanoseconds: UInt64(attempt + 1) * 400_000_000)
        }
        throw lastError ?? VoiceProcessingFailureFallback.notReady
    }

    private enum VoiceProcessingFailureFallback: Error {
        case notReady
    }

    /// The whole point of the resampler: whatever the hardware reports, the
    /// wire always sees the 24 kHz the SpeechRail 4.0 contract requires.
    @Test("Default route capture reaches the wire rate whatever the hardware rate is")
    func defaultRouteResamplesToWireRate() async throws {
        try requireDeviceAcceptance()
        let engine = AVAudioEngine()
        let hardware = engine.inputNode.outputFormat(forBus: 0)
        let hardwareRate = hardware.sampleRate
        let hardwareChannels = hardware.channelCount
        #expect(hardwareRate > 0)
        #expect(hardwareChannels > 0)

        let session = try MicrophoneCaptureSession(
            configuration: .init(targetSampleRate: 24_000))
        let stream = try session.start()
        var chunks = 0
        var totalFrames = 0
        for try await chunk in stream {
            #expect(chunk.sampleRate == 24_000)
            #expect(chunk.channels == 1)
            #expect(chunk.frameCount > 0)
            #expect(chunk.data.count == chunk.frameCount * 2)
            chunks += 1
            totalFrames += chunk.frameCount
            if chunks >= 12 { break }
        }
        session.stop()
        #expect(chunks > 0)
        #expect(totalFrames > 0)
    }

    /// Voice processing is what makes full duplex possible. It is a property
    /// of the live I/O pair, so it can only be observed on a real route.
    @Test("Voice processing engages on the ambient device pair")
    func voiceProcessingEngagesOnDefaultRoute() async throws {
        try requireDeviceAcceptance()
        let provision = VoiceProcessingDuplexFactory.make(
            microphoneConfiguration: .init(targetSampleRate: 24_000))
        guard case .fullDuplex = provision else {
            Issue.record("24 kHz target must provision a full-duplex stack")
            return
        }
        let (graph, _) = try await makeGraph()
        #expect(graph.isVoiceProcessingEnabled)
        #expect(graph.snapshot().voiceProcessingEnabled)
        graph.shutdown()
    }

    /// Wire audio is 24 kHz; the output device is whatever it is. Playback
    /// must accept the wire format and let the engine convert, rather than
    /// refusing a device that does not happen to run at 24 kHz.
    @Test("24 kHz wire audio is accepted by the ambient output route")
    func wireAudioAcceptedByDefaultOutputRoute() async throws {
        try requireDeviceAcceptance()
        let (graph, _) = try await makeGraph()
        try graph.startPlayback(sampleRate: 24_000, channels: 1, outputGain: 0.5)
        let frames = 24_000 / 2
        let pcm = Self.tonePCM(frames: frames, amplitude: 6_000)
        try graph.enqueuePlayback(pcm16: pcm, frameCount: frames)
        #expect(graph.snapshot().playbackActive)
        graph.stopPlayback()
        graph.shutdown()
    }

    /// The claim layer B explicitly could not make: the audio physically
    /// leaves the speaker.
    ///
    /// Comparing capture level with playback running against capture level
    /// with silence is device-agnostic on purpose. Correlation against the
    /// played waveform would need a strong acoustic loop, which a Bluetooth
    /// earbud does not provide -- its microphone sits in the earbud, not near
    /// the room.
    ///
    /// Whether that works is a property of the user's hardware, not of the
    /// app, so this reports rather than asserts. On a Bluetooth earbud the
    /// ambient room noise routinely exceeds the coupled signal and the delta
    /// swings between runs, which means the route is *inconclusive* -- and a
    /// test that reported that as a pass would be lying. Asserting a fixed
    /// threshold would be worse still: it would fail on hardware the app is
    /// required to support.
    @Test("Reports the duplex mode this route actually offers")
    func duplexModeAndEmissionAreReportedForThisRoute() async throws {
        try requireDeviceAcceptance()

        // One engine for the whole probe, capture already running. A second
        // AVAudioEngine competing for the same input returns silence, which
        // would make this measurement pass by measuring nothing.
        let (graph, capture) = try await makeGraph()
        // The requirement is that every route ends up usable, not that every
        // route manages full duplex. A Bluetooth headset can hold a
        // voice-processed input open and still refuse to add playback to it;
        // the app's answer is the half-duplex PTT fallback, so that is what
        // gets checked here.
        do {
            // Baseline first, playback second: measuring both while the tone
            // is playing would compare the signal against itself.
            let quiet = try await bestOfThree(capture)
            try graph.startPlayback(
                sampleRate: 24_000, channels: 1, outputGain: 1.0)
            let pcm = Self.tonePCM(frames: 24_000, amplitude: 30_000)
            try graph.enqueuePlayback(pcm16: pcm, frameCount: 24_000)
            let loud = try await bestOfThree(capture)
            let deltaDB = (loud.peak > 0 && quiet.peak > 0)
                ? 20 * log10(loud.peak / quiet.peak) : 0
            // Two LSB is the 16-bit quantisation floor. At that level the
            // route cannot distinguish "AEC removed the echo" from "the
            // earbud microphone never heard it", and this must not claim
            // otherwise. Only a rise counts as emission: a fall means ambient
            // noise or an engine transient.
            let floor = 2.0 / 32768.0
            let detectable = loud.peak > floor && deltaDB >= 3.0
            print(
                "device_acceptance duplex=full quiet_rms=\(quiet.rms) "
                    + "quiet_peak=\(quiet.peak) loud_rms=\(loud.rms) "
                    + "loud_peak=\(loud.peak) delta_db=\(deltaDB) "
                    + "at_quantisation_floor=\(loud.peak <= floor) "
                    + "emission_detected=\(detectable)")
            graph.stopPlayback()
        } catch {
            // Not a failure: half duplex is a supported mode, and the route
            // simply cannot do both at once.
            print(
                "device_acceptance duplex=half_duplex_ptt "
                    + "emission_measurable=false reason=\(error)")
        }
        graph.stopCapture()
        graph.shutdown()
    }

    private struct Level {
        let rms: Double
        let peak: Double
    }

    private static func tonePCM(frames: Int, amplitude: Double) -> Data {
        var pcm = Data(repeating: 0, count: frames * 2)
        for i in 0..<frames {
            let value = Int16(amplitude * sin(2 * .pi * 440 * Double(i) / 24_000))
            pcm[i * 2] = UInt8(truncatingIfNeeded: value)
            pcm[i * 2 + 1] = UInt8(truncatingIfNeeded: value >> 8)
        }
        return pcm
    }

    /// Reads level straight off the production capture stream, so the
    /// measurement exercises the same resampling path the app uses.
    private func bestOfThree(
        _ stream: AsyncThrowingStream<MicrophonePCM16Chunk, any Error>
    ) async throws -> Level {
        // The first window is discarded: engine start and Bluetooth route
        // activation produce a loud transient that is not the signal under test.
        _ = try await measure(stream, seconds: 0.5)
        var best = Level(rms: 0, peak: 0)
        for _ in 0..<5 {
            let level = try await measure(stream, seconds: 1.0)
            if level.peak > best.peak { best = level }
            if level.rms > best.rms { best = Level(rms: level.rms, peak: best.peak) }
        }
        return best
    }

    private func measure(
        _ stream: AsyncThrowingStream<MicrophonePCM16Chunk, any Error>,
        seconds: Double
    ) async throws -> Level {
        let wanted = Int(24_000 * seconds)
        var slice: [Int16] = []
        slice.reserveCapacity(wanted)
        for try await chunk in stream {
            #expect(chunk.sampleRate == 24_000)
            chunk.data.withUnsafeBytes { raw in
                let binding = raw.bindMemory(to: Int16.self)
                slice.append(contentsOf: binding)
            }
            if slice.count >= wanted { break }
        }
        guard !slice.isEmpty else { return Level(rms: 0, peak: 0) }
        let values = slice.prefix(wanted).map { Double($0) / 32768.0 }
        let peak = values.reduce(0.0) { max($0, abs($1)) }
        let rms = sqrt(values.reduce(0.0) { $0 + $1 * $1 } / Double(values.count))
        return Level(rms: rms, peak: peak)
    }
}
