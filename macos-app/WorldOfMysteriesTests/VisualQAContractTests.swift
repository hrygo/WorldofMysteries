import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Visual QA Contracts")
struct VisualQAContractTests {
    @Test("danger button keeps a high-contrast solid semantic fill")
    func dangerButtonContrastSource() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/WOMButtonStyles.swift")
        #expect(source.contains("Color.Mystic.crimsonThread.opacity"))
        #expect(!source.contains("return Color.Mystic.crimsonStar.opacity((isHovered ? 0.95 : 0.78)"))
    }

    @Test("ritual readable text does not use unsafe dynamic pathway colors")
    func ritualTextContrast() throws {
        let altar = try file("macos-app/WorldOfMysteries/Components/BronzeAltarPrayerCard.swift")
        let pendulum = try file("macos-app/WorldOfMysteries/Components/CitrinePendulumScryingCard.swift")

        #expect(!altar.contains(".foregroundStyle(pathwayColor)"))
        #expect(altar.contains(".foregroundStyle(Color.Mystic.textSecondary)"))
        #expect(pendulum.contains(".mysticCaptionStyle(color: Color.Mystic.brassGoldPrimary)"))
        #expect(pendulum.contains("WOMPanelBackground(\n                tone: .card"))
    }

    @Test("sidebar key microcopy remains legible")
    func sidebarMicrocopy() throws {
        let sidebar = try file("macos-app/WorldOfMysteries/Components/AppSidebarView.swift")
        #expect(!sidebar.contains(".font(.system(size: 9"))
        #expect(!sidebar.contains("Color.Mystic.textTertiary.opacity(0.6)"))
        #expect(sidebar.contains("Text(\"World of Mysteries\")\n                        .font(Font.Mystic.caption)"))
        #expect(sidebar.contains("Text(\"85%\")\n                    .font(Font.Mystic.monoBadge)"))
    }

    @Test("content-heavy historical cards keep responsive fallback layouts")
    func responsiveHistoricalCards() throws {
        let character = try file("macos-app/WorldOfMysteries/Components/CharacterCodexCard.swift")
        let dossier = try file("macos-app/WorldOfMysteries/Components/TingenCityDossierCard.swift")
        let chronicle = try file("macos-app/WorldOfMysteries/Components/NarrativeChronicleView.swift")

        #expect(character.contains("ViewThatFits(in: .horizontal)"))
        #expect(character.contains("GridItem(.adaptive(minimum: 96)"))
        #expect(dossier.contains("ViewThatFits(in: .horizontal)"))
        #expect(chronicle.contains("ViewThatFits(in: .horizontal)"))
    }

    @Test("minimum-window shell and artifact entry use adaptive structures")
    func minimumWindowLayoutContracts() throws {
        let content = try file("macos-app/WorldOfMysteries/ContentView.swift")
        let fate = try file("macos-app/WorldOfMysteries/Artifacts/ArtifactFateInterventionView.swift")
        let showcase = try file("macos-app/WorldOfMysteries/Artifacts/ArtifactShowcaseView.swift")

        #expect(content.contains("ViewThatFits(in: .horizontal)"))
        #expect(content.contains("GridItem(.adaptive(minimum: 240)"))
        #expect(fate.contains("GridItem(\n            .adaptive(minimum: 148, maximum: 220)"))
        #expect(showcase.contains("ViewThatFits(in: .horizontal)"))
        #expect(!showcase.contains(".frame(width: 170)"))
    }

    @Test("artifact semantic accent stays decoration rather than small selected text")
    func artifactTextUsesStableTokens() throws {
        let fate = try file("macos-app/WorldOfMysteries/Artifacts/ArtifactFateInterventionView.swift")
        let showcase = try file("macos-app/WorldOfMysteries/Artifacts/ArtifactShowcaseView.swift")

        #expect(fate.contains(".foregroundStyle(isEnabled ? Color.Mystic.textSecondary : Color.Mystic.textTertiary)"))
        #expect(!fate.contains("descriptor.tone.accent.opacity(isEnabled ? 0.9 : 0.45)"))
        #expect(showcase.contains("isSelected ? Color.Mystic.textPrimary : Color.Mystic.textSecondary"))
    }

    @Test("component gallery retains the visual QA stress regression surface")
    func visualQAStressSurface() throws {
        let gallery = try file("macos-app/WorldOfMysteries/Components/ComponentGalleryVisualSystemSection.swift")
        #expect(gallery.contains("Visual QA Stress · 可读性与布局压力"))
        #expect(gallery.contains("GridItem(.adaptive"))
        #expect(gallery.contains("超长中文标题压力"))
        #expect(gallery.contains("Extremely long English heading"))
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
