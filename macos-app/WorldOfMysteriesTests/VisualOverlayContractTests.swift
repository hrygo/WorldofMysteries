import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Visual Overlay Contracts")
struct VisualOverlayContractTests {
    @Test("overlay roles remain semantic visual roles only")
    func overlayRoleSet() {
        #expect(WOMOverlayRole.allCases.map(\.rawValue) == [
            "inspector",
            "popover",
            "sheet",
            "hud",
        ])
    }

    @Test("feedback tones keep stable platform-native status symbols")
    func feedbackToneMappings() {
        #expect(WOMFeedbackTone.info.statusIcon.rawValue == "info.circle")
        #expect(WOMFeedbackTone.success.statusIcon.rawValue == "checkmark.circle")
        #expect(WOMFeedbackTone.warning.statusIcon.rawValue == "exclamationmark.triangle")
        #expect(WOMFeedbackTone.danger.statusIcon.rawValue == "exclamationmark.octagon")
    }

    @Test("overlay primitive does not own native presentation lifecycle")
    func overlayDoesNotBecomePresentationCoordinator() throws {
        let overlay = try source("macos-app/WorldOfMysteries/DesignSystem/WOMOverlayPrimitives.swift")

        #expect(!overlay.contains(".sheet(isPresented:"))
        #expect(!overlay.contains(".popover(isPresented:"))
        #expect(!overlay.contains(".inspector(isPresented:"))
        #expect(!overlay.contains("NSPanel("))
        #expect(!overlay.contains("NSWindow("))
        #expect(overlay.contains("WOMPanelBackground"))
    }

    @Test("typed WOM empty state coexists with legacy Mystic empty state")
    func emptyStateCompatibilityBoundary() throws {
        let overlay = try source("macos-app/WorldOfMysteries/DesignSystem/WOMOverlayPrimitives.swift")
        let legacy = try source("macos-app/WorldOfMysteries/Components/MysticPrimitives.swift")

        #expect(overlay.contains("public struct WOMEmptyState"))
        #expect(overlay.contains("source: WOMIconSource"))
        #expect(legacy.contains("public struct MysticEmptyState"))
        #expect(legacy.contains("systemIcon: String"))
    }

    @Test("gallery keeps overlay and feedback regression specimens")
    func galleryContainsOverlayFeedbackSpecimens() throws {
        let gallery = try source(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryVisualSystemSection.swift"
        )

        #expect(gallery.contains("overlayFeedbackSamples"))
        #expect(gallery.contains("WOMOverlayPanel"))
        #expect(gallery.contains("WOMLoadingState"))
        #expect(gallery.contains("WOMStatusBanner"))
        #expect(gallery.contains("WOMEmptyState"))
    }

    private func source(_ relativePath: String) throws -> String {
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
