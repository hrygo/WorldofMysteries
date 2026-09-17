import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Window and Inspector Visual Contracts")
struct VisualWindowLayoutContractTests {
    @Test("app window keeps the audited minimum and comfortable default size")
    func windowMetricsStayStable() {
        #expect(WOMWindowMetrics.minimumWidth == 960)
        #expect(WOMWindowMetrics.minimumHeight == 640)
        #expect(WOMWindowMetrics.defaultWidth == 1180)
        #expect(WOMWindowMetrics.defaultHeight == 760)
        #expect(WOMWindowMetrics.defaultWidth > WOMWindowMetrics.minimumWidth)
        #expect(WOMWindowMetrics.defaultHeight > WOMWindowMetrics.minimumHeight)
    }

    @Test("inspector width keeps a readable flexible range")
    func inspectorMetricsStayReadable() {
        #expect(WOMInspectorMetrics.minimumWidth == 280)
        #expect(WOMInspectorMetrics.idealWidth == 320)
        #expect(WOMInspectorMetrics.maximumWidth == 420)
        #expect(WOMInspectorMetrics.minimumWidth < WOMInspectorMetrics.idealWidth)
        #expect(WOMInspectorMetrics.idealWidth < WOMInspectorMetrics.maximumWidth)
    }

    @Test("workspace pair falls back instead of compressing readable content")
    func adaptivePairUsesViewThatFits() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/WOMWorkspaceLayout.swift")

        #expect(source.contains("ViewThatFits(in: .horizontal)"))
        #expect(source.contains("HStack(alignment: .top"))
        #expect(source.contains("VStack(alignment: .leading"))
        #expect(!source.contains(".offset(x:"))
        #expect(!source.contains("negativePadding"))
    }

    @Test("inspector keeps native SwiftUI presentation and flexible column width")
    func inspectorStaysNative() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/WOMWorkspaceLayout.swift")

        #expect(source.contains(".inspectorColumnWidth("))
        #expect(source.contains(".inspector(isPresented:"))
        #expect(source.contains("WOMInspectorContent"))
        #expect(!source.contains("NSPanel"))
        #expect(!source.contains("NSWindow"))
        #expect(!source.contains("NSViewRepresentable"))
    }

    @Test("app scene uses default size without locking native resizing")
    func appSceneUsesDefaultSizeOnly() throws {
        let source = try file("macos-app/WorldOfMysteries/MyApp.swift")

        #expect(source.contains(".defaultSize("))
        #expect(source.contains("WOMWindowMetrics.defaultWidth"))
        #expect(source.contains("WOMWindowMetrics.defaultHeight"))
        #expect(!source.contains(".windowResizability(.contentSize)"))
    }

    @Test("production content uses shared minimum and adaptive fate split")
    func productionWorkspaceUsesSharedMetrics() throws {
        let source = try file("macos-app/WorldOfMysteries/ContentView.swift")

        #expect(source.contains("WOMWindowMetrics.minimumWidth"))
        #expect(source.contains("WOMWindowMetrics.minimumHeight"))
        #expect(source.contains("WOMAdaptivePair("))
        #expect(source.contains("WOMWorkspaceMetrics.fateAnchorWidth"))
        #expect(!source.contains(".frame(minWidth: 960, minHeight: 640)"))
        #expect(!source.contains(".frame(width: 280)"))
    }

    @Test("Inspector QA preview exercises long localized content at real system presentation")
    func inspectorPreviewKeepsStressContent() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/WOMWorkspaceLayout.swift")

        #expect(source.contains("Native Inspector · Visual QA"))
        #expect(source.contains("280pt minimum width stress"))
        #expect(source.contains("Extremely long" ) || source.contains("Long English"))
        #expect(source.contains("WOMRelationBadge"))
        #expect(source.contains("WOMCooldownIndicator"))
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
