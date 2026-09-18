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
        #expect(primitives.contains("minWidth: title == nil ? WOMButtonDensity.icon.minWidth : nil"))
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
        #expect(primitives.contains("@FocusState private var isFocused: Bool"))
        #expect(primitives.contains(".focused($isFocused)"))
        #expect(!primitives.contains(".opacity(isEnabled ? 1 : 0.48)"))
        #expect(primitives.contains("isHovered = isEnabled && hovering"))
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

    @Test("advice input reuses unified button primitives and exposes focus semantics")
    func adviceInputUsesUnifiedControls() throws {
        let source = try source("Components/AdviceInputField.swift")
        #expect(source.contains(".buttonStyle(WOMIconButtonStyle(.secondary))"))
        #expect(source.contains(".buttonStyle(WOMButtonStyle(.primary))"))
        #expect(source.contains(".disabled(isSubmitDisabled)"))
        #expect(source.contains("inputBorderColor"))
        #expect(source.contains("colorSchemeContrast == .increased"))
        #expect(!source.contains(".mysticPressable("))
    }

    @Test("sidebar status meter reuses semantic status and metric primitives")
    func sidebarStatusUsesSharedPrimitives() throws {
        let source = try source("Components/AppSidebarView.swift")
        #expect(source.contains("MysticStatusDot(tone: .teal"))
        #expect(source.contains("MysticMetricBar("))
        #expect(source.contains("label: \"灵性储备\""))
    }

    @Test("typed system-action registry covers refresh and legacy icon buttons accept it")
    func typedRefreshActionContract() throws {
        #expect(WOMSystemIcon.refresh.rawValue == "arrow.triangle.2.circlepath")

        let primitives = try source("Components/MysticPrimitives.swift")
        #expect(primitives.contains("systemIcon: WOMSystemIcon"))
        #expect(primitives.contains("systemIcon: systemIcon.rawValue"))
    }

    @Test("database rebuild action cannot appear enabled without a probe reading and a handler")
    func databaseRebuildAvailabilityContract() throws {
        let source = try source("Components/DatabaseStatusHUDCard.swift")
        #expect(source.contains("systemIcon: .refresh"))
        // 比「渲染后禁用」更强：未探明或缺少回调时，重建控件根本不进入视图树。
        #expect(source.contains("if role.isRebuildable, status.isProbed, let onRebuildTapped"))
        #expect(!source.contains(".disabled(onRebuildTapped == nil)"))
    }

    @Test("component gallery carries compact-control stress specimens")
    func galleryCompactControlStressSpecimen() throws {
        let gallery = try source("Components/ComponentGalleryInteractionSpecimenSection.swift")
        #expect(gallery.contains("compactControlStressSpecimen"))
        #expect(gallery.contains("提交给当前世界线中的角色进行独立判断"))
        #expect(gallery.contains("Review the full intervention evidence before continuing"))
        #expect(gallery.contains("MysticMetricBar("))
        #expect(gallery.contains("criticalThreshold: 0.25"))
    }

    @Test("spirituality gauge respects reduced motion")
    func spiritualityGaugeReduceMotionContract() throws {
        let source = try source("Components/SpiritualityGaugeView.swift")
        #expect(source.contains("@Environment(\\.accessibilityReduceMotion)"))
        #expect(source.contains(".animation(reduceMotion ? nil"))
    }

    @Test("listening ring is keyboard-focusable and no longer tap-gesture only")
    func listeningRingInteractionContract() throws {
        let source = try source("Components/ListeningRingView.swift")
        #expect(source.contains("@FocusState private var isRingFocused"))
        #expect(source.contains("Button(action: onRingTapped)"))
        #expect(source.contains(".focused($isRingFocused)"))
        #expect(source.contains(".accessibilityHint("))
        #expect(source.contains(".phaseAnimator([0.0, 1.0])"))
        #expect(!source.contains(".rotationEffect("))
        #expect(!source.contains(".onTapGesture"))
    }

    @Test("tarot card does not expose a no-op action and has explicit focus semantics")
    func tarotCardInteractionContract() throws {
        let source = try source("Components/TarotCardView.swift")
        #expect(source.contains("@FocusState private var isCardFocused"))
        #expect(source.contains(".disabled(onCardTapped == nil)"))
        #expect(source.contains("isCardFocused && onCardTapped != nil ? 1 : 0"))
        #expect(source.contains(".accessibilityValue(discovery.stageText)"))
    }

    @Test("pendulum standard actions use typed system icon sources")
    func pendulumTypedActionIconContract() throws {
        #expect(WOMSystemIcon.retry.rawValue == "arrow.counterclockwise")
        let source = try source("Components/SpiritPendulumView.swift")
        #expect(source.contains("WOMIcon(status: .active"))
        #expect(source.contains("WOMIcon(system: .retry"))
    }

    @Test("pressable style and optional-action components fail closed when disabled")
    func optionalActionFailClosedContract() throws {
        let interaction = try source("DesignSystem/InteractionStyles.swift")
        #expect(interaction.contains("@Environment(\\.isEnabled)"))
        #expect(interaction.contains("configuration.isPressed && isEnabled"))
        #expect(interaction.contains(": 0.48"))

        let clue = try source("Components/CluePinboardNodeView.swift")
        #expect(clue.contains(".disabled(onNodeTapped == nil)"))

        let worldline = try source("Components/WorldlineNodeView.swift")
        #expect(worldline.contains(".disabled(onSelect == nil)"))

        let codex = try source("Components/CharacterCodexCard.swift")
        #expect(codex.contains(".disabled(onVoiceAdviceTapped == nil)"))
    }

    @Test("Advice input uses the same delivery policy for button and Return-key submission")
    func adviceInputDeliveryBoundary() throws {
        let advice = try source("Components/AdviceInputField.swift")
        #expect(advice.contains("AdviceDraftSubmission.payload("))
        #expect(advice.contains("AdviceDraftSubmission.submit("))
        #expect(advice.contains("hasHandler: onSubmitAdvice != nil"))
        #expect(advice.contains("isEnabled: isEnabled"))
        #expect(advice.contains("WOMIcon(system: .advice"))
        #expect(!advice.contains("onSubmitAdvice?(trimmed)"))
    }

    @Test("Card face, assistive copy and pathway styling use the same discovery projection")
    func tarotDiscoveryProjectionBoundary() throws {
        let card = try source("Components/TarotCardView.swift")
        #expect(card.contains("Text(discovery.sequenceLabel)"))
        #expect(card.contains("Text(discovery.pathwayLabel)"))
        #expect(card.contains("Text(discovery.title)"))
        #expect(card.contains(".accessibilityElement(children: .ignore)"))
        #expect(card.contains(".accessibilityLabel(discovery.accessibilityLabel)"))
        #expect(card.contains("discovery.revealsIdentity ? pathwayColor : Color.Mystic.textTertiary"))
        #expect(!card.contains("Text(pathwayName)"))
        #expect(!card.contains("Text(sequenceTitle)"))
    }

    @Test("status pulse follows live semantic changes, not only view appearance")
    func statusPulseFollowsSemanticChanges() throws {
        let primitives = try source("Components/MysticPrimitives.swift")
        #expect(primitives.contains(".onChange(of: isPulsing)"))
        #expect(primitives.contains("isPulsing && !reduceMotion && !differentiateWithoutColor"))
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
