import Foundation
import Testing
@testable import WorldOfMysteriesCore

/// The duplex graph is exercised only through its pure configuration gate.
/// Building a real `AVAudioEngine` would open a microphone in CI, so the
/// device-backed half of the stack stays a manual acceptance item.
@Suite("Voice processing duplex format constraints")
@MainActor
struct VoiceProcessingDuplexGraphTests {
    @Test("A non-24 kHz capture target falls back before the audio device is touched")
    func nonWireRateFallsBack() {
        for rate in [16_000, 48_000, 44_100, 0] {
            let provision = VoiceProcessingDuplexFactory.make(
                microphoneConfiguration: .init(targetSampleRate: rate)
            )
            switch provision {
            case .halfDuplexPTT(let reason):
                #expect(reason == .invalidConfiguration)
            case .fullDuplex:
                Issue.record("A \(rate) Hz capture target must not build a duplex graph")
            }
        }
    }

    @Test("Out-of-range tap and buffer bounds fall back for the same reason")
    func outOfRangeBoundsFallBack() {
        let cases = [
            MicrophoneCaptureConfiguration(targetSampleRate: 24_000, tapFrameCount: 64),
            MicrophoneCaptureConfiguration(targetSampleRate: 24_000, tapFrameCount: 8192),
            MicrophoneCaptureConfiguration(targetSampleRate: 24_000, bufferedChunkLimit: 1),
            MicrophoneCaptureConfiguration(targetSampleRate: 24_000, bufferedChunkLimit: 64),
        ]
        for configuration in cases {
            let provision = VoiceProcessingDuplexFactory.make(
                microphoneConfiguration: configuration
            )
            switch provision {
            case .halfDuplexPTT(let reason):
                #expect(reason == .invalidConfiguration)
            case .fullDuplex:
                Issue.record("Out-of-range bounds must not build a duplex graph")
            }
        }
    }

    @Test("A non-positive queue bound falls back instead of trapping")
    func nonPositiveQueueBoundFallsBack() {
        let provision = VoiceProcessingDuplexFactory.make(
            microphoneConfiguration: .init(targetSampleRate: 24_000),
            maxQueuedBytes: 0
        )
        switch provision {
        case .halfDuplexPTT(let reason):
            #expect(reason == .invalidConfiguration)
        case .fullDuplex:
            Issue.record("A non-positive queue bound must not build a duplex graph")
        }
    }

    @Test("The duplex capture path and the ASR wire agree on one sample rate")
    func duplexAndWireRatesAgree() {
        // The duplex source resamples to `configuration.targetSampleRate`; the
        // push-to-talk fence only accepts the shared wire rate, so a mismatch
        // here would silently drop every chunk at the PTT boundary.
        #expect(MicrophoneCaptureConfiguration().targetSampleRate
            == SpeechRailRealtimeWire.sampleRate)
        #expect(SpeechRailRealtimeWire.sampleRate == 24_000)
    }
}
