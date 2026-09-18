import AppKit
import SwiftUI
import Testing
@testable import WorldOfMysteriesCore

@Suite("Listening Ring Runtime Presentation", .serialized)
struct ListeningRingReviewTests {
    @Test("Idle and deliberation do not simulate listening or processing motion", arguments: [
        ListeningRingState.idle, .interpreting, .deciding, .narrating,
    ])
    func quietStates(state: ListeningRingState) {
        for level in [0.0, 0.4, 1, Double.nan, .infinity, -.infinity] {
            let view = projection(state, audio: level)
            #expect(!view.shouldBreathe)
            #expect(view.scale(at: 0) == 1)
            #expect(view.scale(at: 1) == 1)
            #expect(view.opacity(at: 0) == view.opacity(at: 1))
        }
    }

    @Test("Listening breathes only without measured positive audio")
    func listeningFeedback() {
        let listening = projection(.listening)
        #expect(listening.shouldBreathe)
        #expect(listening.scale(at: 0) == DesignTokens.ComponentMetrics.ListeningRing.breathingScaleMin)
        #expect(abs(listening.scale(at: 1) - DesignTokens.ComponentMetrics.ListeningRing.breathingScaleMax) < 0.0001)
        let measured = projection(.listening, audio: 0.5)
        #expect(!measured.shouldBreathe)
        #expect(measured.scale(at: 0) == measured.scale(at: 1))
        #expect(measured.scale(at: 0) == 1 + 0.5 * DesignTokens.ComponentMetrics.ListeningRing.audioScaleGain)
    }

    @Test("Playback never invents an audio waveform when no valid level is supplied")
    func playbackWithoutLevel() {
        for level in [0.0, Double.nan, .infinity, -.infinity] {
            let view = projection(.speaking, audio: level)
            #expect(!view.shouldBreathe)
            #expect(view.scale(at: 0) == 1)
            #expect(view.scale(at: 1) == 1)
        }
    }

    @Test("Reduced motion, disabled and inactive states remain geometrically stationary")
    func motionPreferences() {
        for state in ListeningRingState.allCases {
            for view in [
                projection(state, audio: 0.5, reduce: true),
                projection(state, audio: 0.5, enabled: false),
                projection(state, audio: 0.5, active: false),
            ] {
                #expect(!view.shouldBreathe)
                #expect(view.scale(at: 0) == 1)
                #expect(view.scale(at: 1) == 1)
            }
        }
    }

    @Test("Audio and animation boundaries never produce non-finite geometry")
    func finiteGeometry() {
        for state in ListeningRingState.allCases {
            for level in [-1, 0, 0.5, 1, 2, Double.nan, .infinity, -.infinity] {
                for phase in [-1, 0, 0.5, 1, 2, Double.nan, .infinity] {
                    let view = projection(state, audio: level)
                    let scale = view.scale(at: phase)
                    let opacity = view.opacity(at: phase)
                    #expect(scale.isFinite && scale > 0 && scale <= 1.3)
                    #expect(opacity.isFinite && opacity >= 0 && opacity <= 1)
                }
            }
        }
    }

    @Test("Speaker identity is supplied, never assumed or leaked into another runtime state")
    func speakerIdentity() {
        #expect(ListeningRingState.speaking.promptText == "人物正在回应…")
        #expect(ListeningRingState.speaking.promptText(speakerName: " \n ") == "人物正在回应…")
        #expect(ListeningRingState.speaking.promptText(speakerName: "  已知人物甲 \n") == "已知人物甲正在回应…")
        for state in ListeningRingState.allCases where state != .speaking {
            #expect(!state.promptText(speakerName: "PRIVATE_SPEAKER").contains("PRIVATE_SPEAKER"))
        }
    }

    @Test("State transitions do not retain another phase's visual projection")
    func stateSequence() {
        let sequence: [ListeningRingState] = [.listening, .deciding, .listening, .speaking, .idle, .deciding]
        for state in sequence {
            let current = projection(state)
            #expect(current.shouldBreathe == (state == .listening))
            if state != .listening { #expect(current.scale(at: 1) == 1) }
        }
    }

    @Test("Native quiet-state pixels do not change with unrelated audio input")
    @MainActor
    func quietStatePixels() throws {
        _ = NSApplication.shared
        for state in [ListeningRingState.idle, .deciding, .narrating] {
            let first = try render(ListeningRingView(state: state, audioLevel: 0))
            let second = try render(ListeningRingView(state: state, audioLevel: 1))
            #expect(first == second)
        }
    }

    @Test("Real view owns no spinner, delay or hidden runtime transition")
    func productionWiring() throws {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("WorldOfMysteries/Components/ListeningRingView.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        #expect(source.contains("if presentation.shouldBreathe"))
        #expect(source.contains(".phaseAnimator([0.0, 1.0])"))
        #expect(!source.contains(".rotationEffect("))
        #expect(!source.contains(".repeatForever("))
        #expect(!source.contains("Task.sleep"))
        #expect(!source.contains("Timer."))
        #expect(!source.contains("克莱恩正在回应"))
    }

    private func projection(
        _ state: ListeningRingState, audio: Double = 0,
        reduce: Bool = false, enabled: Bool = true, active: Bool = true
    ) -> ListeningRingPresentation {
        ListeningRingPresentation(state: state, audioLevel: audio, reduceMotion: reduce,
            isEnabled: enabled, appearsActive: active)
    }

    @MainActor
    private func render<V: View>(_ view: V) throws -> Data {
        let renderer = ImageRenderer(content: view.padding(20)
            .background(Color.Mystic.obsidianBase).environment(\.colorScheme, .dark))
        renderer.scale = 2
        let image = try #require(renderer.cgImage)
        let bitmap = NSBitmapImageRep(cgImage: image)
        return try #require(bitmap.representation(using: .png, properties: [:]))
    }
}
