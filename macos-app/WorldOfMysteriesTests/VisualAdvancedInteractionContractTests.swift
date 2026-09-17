import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Advanced Interaction Visual Contracts")
struct VisualAdvancedInteractionContractTests {
    @Test("adaptive segmented selection keeps native Picker semantics")
    func adaptiveSegmentedUsesNativePicker() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/WOMAdaptiveSegmentedPicker.swift")

        #expect(source.contains("Picker(label, selection: $selection)"))
        #expect(source.contains(".pickerStyle(.segmented)"))
        #expect(source.contains(".pickerStyle(.menu)"))
        #expect(source.contains("ViewThatFits(in: .horizontal)"))
        #expect(!source.contains("Button {"))
        #expect(!source.contains("NSViewRepresentable"))
        #expect(!source.contains("NSSegmentedControl("))
    }

    @Test("world-state chrome keeps icon text and geometry semantic redundancy")
    func worldStateSemanticsAreNotColorOnly() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/WOMWorldStateChrome.swift")

        for role in ["trusted", "aligned", "neutral", "wary", "hostile"] {
            #expect(source.contains("case \(role)"))
        }
        for state in ["locked", "discovered", "completed"] {
            #expect(source.contains("case \(state)"))
        }

        #expect(source.contains("systemImage"))
        #expect(source.contains("readableForeground"))
        #expect(source.contains("accessibilityDifferentiateWithoutColor"))
        #expect(source.contains("differentiateDash"))
        #expect(!source.contains(".font(.system(size: 9"))
    }

    @Test("cooldown indicator is presentation only and owns no clock")
    func cooldownOwnsNoTimer() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/WOMWorldStateChrome.swift")

        #expect(source.contains("case ready"))
        #expect(source.contains("case cooling(progress: Double, remainingLabel: String?)"))
        #expect(source.contains("case locked(reason: String?)"))
        #expect(source.contains("ProgressView(value: progress)"))
        #expect(!source.contains("Timer."))
        #expect(!source.contains("Task.sleep"))
        #expect(!source.contains("repeatForever"))
    }

    @Test("advanced gallery retains narrow and long-label stress specimens")
    func advancedGalleryStressSpecimens() throws {
        let gallery = try file("macos-app/WorldOfMysteries/Components/ComponentGalleryVisualSystemSection.swift")

        #expect(gallery.contains("Advanced Interaction / World-State Chrome"))
        #expect(gallery.contains(".frame(maxWidth: 220"))
        #expect(gallery.contains("Extremely long hostile entity label"))
        #expect(gallery.contains("极端长本地化标题"))
        #expect(gallery.contains("WOMRelationBadge"))
        #expect(gallery.contains("WOMAchievementSeal"))
        #expect(gallery.contains("WOMCooldownIndicator"))
    }

    @Test("Wave F stays presentation-only")
    func waveFStaysPresentationOnly() throws {
        let segmented = try file("macos-app/WorldOfMysteries/DesignSystem/WOMAdaptiveSegmentedPicker.swift")
        let chrome = try file("macos-app/WorldOfMysteries/DesignSystem/WOMWorldStateChrome.swift")
        let combined = segmented + chrome

        #expect(!combined.contains("SQLite"))
        #expect(!combined.contains("EngineIPCClient"))
        #expect(!combined.contains("world.db"))
        #expect(!combined.contains("URLSession"))
    }

    private func file(_ relativePath: String) throws -> String {
        try String(
            contentsOf: repositoryRoot.appendingPathComponent(relativePath),
            encoding: .utf8
        )
    }

    private var repositoryRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }
}
