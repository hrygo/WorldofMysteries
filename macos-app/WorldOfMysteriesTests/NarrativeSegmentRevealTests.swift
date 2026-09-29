import Foundation
import Testing
@testable import WorldOfMysteriesCore

@MainActor
@Suite("Narrative segment reveal")
struct NarrativeSegmentRevealTests {
    private func waitUntil(
        _ condition: @MainActor () -> Bool,
        timeout: Duration = .seconds(5)
    ) async throws {
        let deadline = ContinuousClock.now.advanced(by: timeout)
        while ContinuousClock.now < deadline {
            if condition() { return }
            try await Task.sleep(for: .milliseconds(2))
        }
        Issue.record("the reveal never reached the expected state")
    }

    @Test("The first segment arrives with the text, the rest follow in order")
    func revealsInOrder() async throws {
        let reveal = NarrativeSegmentReveal(cadence: .milliseconds(20))
        let segments = ["一", "二", "三", "四"]

        reveal.present(turnId: "turn_1", segments: segments)

        #expect(reveal.visible(from: segments, turnId: "turn_1") == ["一"])
        try await waitUntil { reveal.visibleCount == 4 }
        #expect(reveal.visible(from: segments, turnId: "turn_1") == segments)
        #expect(!reveal.isRevealing)
    }

    @Test("The reveal always ends on exactly the snapshot it was given")
    func endsOnTheAuthoritativeSnapshot() async throws {
        let reveal = NarrativeSegmentReveal(cadence: .milliseconds(5))
        let segments = ["一", "二"]

        reveal.present(turnId: "turn_1", segments: segments)
        try await waitUntil { !reveal.isRevealing }

        #expect(reveal.visible(from: segments, turnId: "turn_1") == segments)
        // Re-presenting a settled turn must not hide or duplicate anything.
        reveal.present(turnId: "turn_1", segments: segments)
        #expect(reveal.visible(from: segments, turnId: "turn_1") == segments)
    }

    @Test("A single segment is never delayed")
    func singleSegmentIsImmediate() {
        let reveal = NarrativeSegmentReveal(cadence: .seconds(30))
        let segments = ["只有一句"]

        reveal.present(turnId: "turn_1", segments: segments)

        #expect(reveal.visible(from: segments, turnId: "turn_1") == segments)
        #expect(!reveal.isRevealing)
    }

    @Test("A new turn starts over instead of continuing the previous one")
    func newTurnResets() async throws {
        let reveal = NarrativeSegmentReveal(cadence: .milliseconds(200))
        let first = ["一", "二", "三"]
        reveal.present(turnId: "turn_1", segments: first)
        #expect(reveal.visible(from: first, turnId: "turn_1") == ["一"])

        let second = ["甲", "乙"]
        reveal.present(turnId: "turn_2", segments: second)

        #expect(reveal.visible(from: second, turnId: "turn_2") == ["甲"])
        #expect(reveal.visible(from: first, turnId: "turn_1").isEmpty)
        try await waitUntil { reveal.visible(from: second, turnId: "turn_2") == second }
    }

    @Test("A longer snapshot continues the reveal rather than restarting it")
    func longerSnapshotContinues() async throws {
        let reveal = NarrativeSegmentReveal(cadence: .milliseconds(10))
        reveal.present(turnId: "turn_1", segments: ["一", "二"])
        try await waitUntil { reveal.visibleCount == 2 }

        let grown = ["一", "二", "三"]
        reveal.present(turnId: "turn_1", segments: grown)

        #expect(reveal.visible(from: grown, turnId: "turn_1") == ["一", "二"])
        try await waitUntil { reveal.visible(from: grown, turnId: "turn_1") == grown }
    }

    @Test("A pending turn reveals nothing at all")
    func pendingRevealsNothing() {
        let reveal = NarrativeSegmentReveal(cadence: .milliseconds(10))

        reveal.present(turnId: "turn_1", segments: [String]())

        #expect(reveal.visibleCount == 0)
        #expect(reveal.visible(from: ["一"], turnId: "turn_1").isEmpty)
        #expect(!reveal.isRevealing)
    }

    @Test("Resetting hides everything the reader had been shown")
    func resetHidesEverything() async throws {
        let reveal = NarrativeSegmentReveal(cadence: .milliseconds(10))
        let segments = ["一", "二", "三"]
        reveal.present(turnId: "turn_1", segments: segments)
        try await waitUntil { reveal.visibleCount == 3 }

        reveal.reset()

        #expect(reveal.visibleCount == 0)
        #expect(reveal.visible(from: segments, turnId: "turn_1").isEmpty)
    }

    @Test("The panel presents the reveal, not the raw snapshot")
    func panelRendersThroughTheReveal() throws {
        let panel = try String(
            contentsOf: repositoryRoot
                .appendingPathComponent("macos-app/WorldOfMysteries/StorySessionPanel.swift"),
            encoding: .utf8
        )

        #expect(panel.contains("reveal.visible(from: work.narrativeSegments"))
        // Iterating the authoritative list directly is how the panel would go
        // back to showing a whole turn in one frame.
        #expect(!panel.contains("ForEach(Array(work.narrativeSegments"))
    }

    private var repositoryRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }
}
