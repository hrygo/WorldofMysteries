import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Voice microphone capture boundaries")
struct MicrophoneCaptureTests {
    @Test("PCM16 quantizer clips, preserves sign and uses little endian samples")
    func pcm16Quantizer() {
        let values: [Float] = [-2, -1, -0.5, 0, 0.5, 1, 2]
        let data = values.withUnsafeBufferPointer {
            PCM16Quantizer.encode($0.baseAddress!, count: $0.count)
        }
        #expect(data.count == values.count * 2)

        let samples: [Int16] = data.withUnsafeBytes { raw in
            Array(raw.bindMemory(to: Int16.self)).map(Int16.init(littleEndian:))
        }
        #expect(samples[0] == .min)
        #expect(samples[1] == .min)
        #expect(samples[2] < 0)
        #expect(samples[3] == 0)
        #expect(samples[4] > 0)
        #expect(samples[5] == .max)
        #expect(samples[6] == .max)
    }

    @Test("Capture configuration accepts only bounded SpeechRail PCM targets")
    func captureConfigurationBounds() throws {
        _ = try MicrophoneCaptureSession(
            configuration: .init(
                targetSampleRate: 24_000,
                tapFrameCount: 960,
                bufferedChunkLimit: 8
            )
        )
        #expect(throws: MicrophoneCaptureFailure.invalidDeviceFormat) {
            try MicrophoneCaptureSession(
                configuration: .init(targetSampleRate: 48_000)
            )
        }
        #expect(throws: MicrophoneCaptureFailure.invalidDeviceFormat) {
            try MicrophoneCaptureSession(
                configuration: .init(bufferedChunkLimit: 1)
            )
        }
    }

    @Test("App package keeps Sandbox while explicitly granting audio input")
    func entitlementAndUsageDescription() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let entitlements = try String(
            contentsOf: root.appendingPathComponent("Packaging/App.entitlements"),
            encoding: .utf8
        )
        #expect(entitlements.contains("com.apple.security.app-sandbox"))
        #expect(entitlements.contains("com.apple.security.device.audio-input"))
        #expect(entitlements.contains("com.apple.security.network.client"))

        let project = try String(
            contentsOf: root.appendingPathComponent("WorldOfMysteries.xcodeproj/project.pbxproj"),
            encoding: .utf8
        )
        #expect(project.components(separatedBy: "CODE_SIGN_ENTITLEMENTS = Packaging/App.entitlements;").count - 1 == 2)
        #expect(project.components(separatedBy: "INFOPLIST_KEY_NSMicrophoneUsageDescription").count - 1 == 2)
        #expect(project.components(separatedBy: "ENABLE_APP_SANDBOX = YES;").count - 1 == 2)
    }
}
