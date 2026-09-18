import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Visual Control Primitive Contracts")
struct VisualControlPrimitiveContractTests {
    @Test("icon scale remains compact and optically stepped")
    func iconScaleContract() {
        #expect(WOMIconSize.compact.points == 16)
        #expect(WOMIconSize.standard.points == 20)
        #expect(WOMIconSize.prominent.points == 24)
        #expect(WOMIconSize.large.points == 32)
    }

    @Test("icon and toolbar button densities keep stable square minimum geometry")
    func buttonDensityGeometry() {
        #expect(WOMButtonDensity.standard.minWidth == nil)
        #expect(WOMButtonDensity.standard.minHeight == 34)

        #expect(WOMButtonDensity.icon.minWidth == 32)
        #expect(WOMButtonDensity.icon.minHeight == 32)

        #expect(WOMButtonDensity.toolbar.minWidth == 28)
        #expect(WOMButtonDensity.toolbar.minHeight == 28)
    }

    @Test("platform icons retain native SF Symbol rendering")
    func platformSymbolRenderingContract() throws {
        let source = try source("DesignSystem/WOMIcon.swift")
        #expect(source.contains(".symbolRenderingMode(.monochrome)"))
        #expect(source.contains(".font(.system(size: size.points, weight: size.symbolWeight))"))

        let platformSection = try #require(source.components(separatedBy: "private func platformSymbol").last)
        #expect(!platformSection.prefix(700).contains(".resizable()"))
    }

    @Test("interaction primitives honor Reduce Motion")
    func reduceMotionCoverage() throws {
        let interaction = try source("DesignSystem/InteractionStyles.swift")
        let primitives = try source("Components/MysticPrimitives.swift")

        #expect(interaction.contains("@Environment(\\.accessibilityReduceMotion)"))
        #expect(interaction.contains("reduceMotion ? nil"))
        #expect(primitives.contains("private var shouldPulse"))
        #expect(primitives.contains("isPulsing && !reduceMotion"))
        #expect(primitives.contains("reduceMotion ? nil : DesignTokens.Interaction.hoverAnimation"))
    }

    @Test("icon-only command primitive has explicit minimum geometry and accessibility label")
    func iconCommandAccessibilityContract() throws {
        let primitives = try source("Components/MysticPrimitives.swift")
        #expect(primitives.contains("minWidth: title == nil ? 32 : nil"))
        #expect(primitives.contains(".accessibilityLabel(Text(accessibilityText))"))
    }

    @Test("legacy semantic badges expose non-color differentiation hooks")
    func badgeDifferentiationContract() throws {
        let primitives = try source("Components/MysticPrimitives.swift")
        #expect(primitives.contains("@Environment(\\.accessibilityDifferentiateWithoutColor)"))
        #expect(primitives.contains("badgeBorderDash"))
        #expect(primitives.contains("colorSchemeContrast == .increased"))
    }

    @Test("legacy icon command supports focus disabled and reduced-motion states")
    func legacyIconCommandInteractionContract() throws {
        let primitives = try source("Components/MysticPrimitives.swift")
        #expect(primitives.contains("@Environment(\\.isFocused)"))
        #expect(primitives.contains(".opacity(isEnabled ? 1 : 0.48)"))
        #expect(primitives.contains("isFocused && isEnabled ? 1 : 0"))
        #expect(primitives.contains("withAnimation(reduceMotion ? nil"))
    }

    @Test("status and metric primitives expose non-color semantic fallbacks")
    func statusAndMetricNonColorContract() throws {
        let primitives = try source("Components/MysticPrimitives.swift")
        #expect(primitives.contains("differentiationSystemIcon"))
        #expect(primitives.contains("isPulsing && !reduceMotion && !differentiateWithoutColor"))
        #expect(primitives.contains("dash: differentiateWithoutColor && isCritical ? [4, 2] : []"))
        #expect(primitives.contains(".accessibilityLabel(label ??"))
    }

    @Test("legacy empty-state action reuses unified WOM button chrome")
    func emptyStateActionUsesUnifiedButtonChrome() throws {
        let primitives = try source("Components/MysticPrimitives.swift")
        #expect(primitives.contains(".buttonStyle(WOMButtonStyle(emptyActionVariant))"))
        #expect(primitives.contains("private var emptyActionVariant: WOMButtonVariant"))
    }

    @Test("adaptive segmented options keep compact native symbol rendering")
    func segmentedPickerSymbolContract() throws {
        let picker = try source("DesignSystem/WOMAdaptiveSegmentedPicker.swift")
        #expect(picker.contains(".symbolRenderingMode(.monochrome)"))
        #expect(picker.contains(".imageScale(.small)"))
        #expect(picker.contains(".lineLimit(1)"))
    }

    @Test("component gallery exposes real button and icon specimens")
    func galleryControlSpecimen() throws {
        let gallery = try source("Components/ComponentGalleryInteractionSpecimenSection.swift")
        #expect(gallery.contains("controlAndIconSpecimen"))
        #expect(gallery.contains("WOMButtonStyle"))
        #expect(gallery.contains("WOMIconButtonStyle"))
        #expect(gallery.contains("WOMToolbarButtonStyle"))
    }

    private func source(_ relativePath: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("WorldOfMysteries", isDirectory: true)

        return try String(
            contentsOf: root.appendingPathComponent(relativePath),
            encoding: .utf8
        )
    }
}
