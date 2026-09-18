import Foundation
import SwiftUI
import Testing
@testable import WorldOfMysteriesCore

@Suite("Control Recovery View Review")
@MainActor
struct ControlRecoveryViewTests {
    @Test("constructing empty, missing and duplicate options never writes the binding")
    func pickerConstructionIsReadOnly() {
        var selected = "archive"
        var writes = 0
        let binding = Binding(get: { selected }, set: { selected = $0; writes += 1 })
        let options: [WOMSegmentedOption<String>] = [
            .init(value: "world", title: "世界"),
            .init(value: "archive", title: "档案"),
            .init(value: "archive", title: "重复档案"),
        ]
        for subset in [[], Array(options.prefix(1)), options] {
            let view = WOMAdaptiveSegmentedPicker("范围", selection: binding, options: subset)
            _ = view.body
        }
        #expect(selected == "archive")
        #expect(writes == 0)
    }

    @Test(arguments: [220, 280, 420])
    func feedbackRendersWithinProposedWidth(_ width: Int) throws {
        var actions = 0
        let banner = WOMStatusBanner(
            tone: .warning,
            title: "需要重试的窄面板状态说明与完整标题",
            message: "Long status text and a retry action must remain within this narrow inspector.",
            actionTitle: "重试示例操作"
        ) { actions += 1 }
        let renderer = ImageRenderer(content: banner.environment(\.colorScheme, .dark))
        renderer.scale = 1
        renderer.proposedSize = ProposedViewSize(width: CGFloat(width), height: nil)
        let image = try #require(renderer.cgImage)
        #expect(image.width <= width)
        #expect(image.height > 0)
        #expect(actions == 0)
    }

    @Test("blank feedback actions are suppressed by production views")
    func viewUsesNormalizedActions() throws {
        let overlay = try source("DesignSystem/WOMOverlayPrimitives.swift")
        #expect(overlay.components(separatedBy: "if let actionTitle = presentation.actionTitle, let onAction").count == 3)
        #expect(overlay.contains("正在加载：\\(presentation.accessibilitySummary)"))
        #expect(overlay.contains(".accessibilityElement(children: .contain)"))
    }

    @Test("native picker receives unique options and an explicit retained missing-value tag")
    func pickerUsesResolvedContent() throws {
        let picker = try source("DesignSystem/WOMAdaptiveSegmentedPicker.swift")
        #expect(picker.contains("ForEach(presentation.options)"))
        #expect(picker.contains(".tag(selection)"))
        #expect(picker.contains(".disabled(presentation.isEmpty)"))
        #expect(!picker.contains("selection = options"))
    }

    private func source(_ path: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("WorldOfMysteries")
        return try String(contentsOf: root.appendingPathComponent(path), encoding: .utf8)
    }
}
