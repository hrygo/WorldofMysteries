import SwiftUI

/// Semantic visual roles for World of Mysteries buttons.
public nonisolated enum WOMButtonVariant: CaseIterable, Sendable {
    case primary
    case secondary
    case tertiary
    case danger
    case ritual
}

private nonisolated enum WOMButtonDensity: Sendable {
    case standard
    case icon
    case toolbar

    var horizontalPadding: CGFloat {
        switch self {
        case .standard: DesignTokens.Spacing.lg
        case .icon: DesignTokens.Spacing.sm
        case .toolbar: 6
        }
    }

    var verticalPadding: CGFloat {
        switch self {
        case .standard: DesignTokens.Spacing.sm
        case .icon: DesignTokens.Spacing.sm
        case .toolbar: 5
        }
    }

    var minHeight: CGFloat {
        switch self {
        case .standard: 34
        case .icon: 32
        case .toolbar: 28
        }
    }

    var cornerRadius: CGFloat {
        switch self {
        case .standard, .icon: DesignTokens.Radii.sm
        case .toolbar: DesignTokens.Radii.xs
        }
    }
}

/// General-purpose World of Mysteries button chrome.
public struct WOMButtonStyle: ButtonStyle, Sendable {
    public let variant: WOMButtonVariant

    public init(_ variant: WOMButtonVariant = .primary) {
        self.variant = variant
    }

    public func makeBody(configuration: Configuration) -> some View {
        WOMButtonChrome(
            label: configuration.label,
            variant: variant,
            density: .standard,
            isPressed: configuration.isPressed
        )
    }
}

/// Compact icon-only button chrome with the same semantic variant model as `WOMButtonStyle`.
public struct WOMIconButtonStyle: ButtonStyle, Sendable {
    public let variant: WOMButtonVariant

    public init(_ variant: WOMButtonVariant = .secondary) {
        self.variant = variant
    }

    public func makeBody(configuration: Configuration) -> some View {
        WOMButtonChrome(
            label: configuration.label,
            variant: variant,
            density: .icon,
            isPressed: configuration.isPressed
        )
    }
}

/// Dense toolbar button chrome for macOS toolbars and inspector header actions.
public struct WOMToolbarButtonStyle: ButtonStyle, Sendable {
    public let variant: WOMButtonVariant

    public init(_ variant: WOMButtonVariant = .tertiary) {
        self.variant = variant
    }

    public func makeBody(configuration: Configuration) -> some View {
        WOMButtonChrome(
            label: configuration.label,
            variant: variant,
            density: .toolbar,
            isPressed: configuration.isPressed
        )
    }
}

private struct WOMButtonChrome<Label: View>: View {
    let label: Label
    let variant: WOMButtonVariant
    let density: WOMButtonDensity
    let isPressed: Bool

    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.isFocused) private var isFocused
    @Environment(\.appearsActive) private var appearsActive
    @Environment(\.colorSchemeContrast) private var colorSchemeContrast
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.accessibilityDifferentiateWithoutColor) private var differentiateWithoutColor
    @State private var isHovered = false

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: density.cornerRadius, style: .continuous)

        label
            .padding(.horizontal, density.horizontalPadding)
            .padding(.vertical, density.verticalPadding)
            .frame(minHeight: density.minHeight)
            .foregroundStyle(foregroundColor)
            .background(shape.fill(backgroundColor))
            .overlay(
                shape.stroke(borderColor, style: borderStrokeStyle)
            )
            .overlay(
                shape
                    .stroke(focusRingColor, lineWidth: DesignTokens.Accessibility.focusRingWidth)
                    .padding(-DesignTokens.Accessibility.focusRingOffset)
                    .opacity(isFocused && isEnabled ? 1 : 0)
            )
            .shadow(color: shadowColor, radius: shadowRadius)
            .scaleEffect(pressedScale)
            .opacity(isEnabled ? pressedOpacity : 0.48)
            .contentShape(shape)
            .animation(reduceMotion ? nil : DesignTokens.Interaction.clickSpring, value: isPressed)
            .animation(reduceMotion ? nil : DesignTokens.Interaction.hoverAnimation, value: isHovered)
            .animation(reduceMotion ? nil : DesignTokens.Interaction.hoverAnimation, value: isFocused)
            .onHover { hovering in
                isHovered = hovering
            }
    }

    private var isIncreasedContrast: Bool {
        colorSchemeContrast == .increased
    }

    private var foregroundColor: Color {
        switch variant {
        case .primary:
            Color.Mystic.obsidianBase
        case .secondary, .tertiary, .ritual, .danger:
            Color.Mystic.textPrimary
        }
    }

    private var backgroundColor: Color {
        guard isEnabled else {
            return Color.Mystic.obsidianCard.opacity(0.55)
        }

        let activityOpacity = appearsActive ? 1.0 : 0.72

        switch variant {
        case .primary:
            return (isHovered ? Color.Mystic.brassGoldHover : Color.Mystic.brassGoldPrimary)
                .opacity((isPressed ? 0.86 : 1) * activityOpacity)
        case .secondary:
            return Color.Mystic.obsidianCard.opacity((isHovered ? 1 : 0.82) * activityOpacity)
        case .tertiary:
            return Color.Mystic.obsidianElevated.opacity((isHovered ? 0.72 : 0) * activityOpacity)
        case .danger:
            // `crimsonThread` keeps white labels above the 4.5:1 text-contrast floor even after
            // hover/pressed/inactive-window compositing. The previous semi-transparent
            // `crimsonStar` fill dipped below the Visual QA contract.
            return Color.Mystic.crimsonThread.opacity((isHovered ? 1.0 : 0.88) * activityOpacity)
        case .ritual:
            return Color.Mystic.deepVoid.opacity((isHovered ? 0.96 : 0.82) * activityOpacity)
        }
    }

    private var borderColor: Color {
        guard isEnabled else {
            return Color.Mystic.brassGoldBorder.opacity(0.25)
        }

        if isIncreasedContrast {
            switch variant {
            case .danger:
                return Color.Mystic.statusDanger
            case .ritual:
                return Color.Mystic.spiritualBlue
            case .primary, .secondary, .tertiary:
                return Color.Mystic.textGoldAccent
            }
        }

        switch variant {
        case .primary:
            return Color.Mystic.brassGoldHover.opacity(0.9)
        case .secondary:
            return Color.Mystic.brassGoldBorder.opacity(isHovered ? 0.9 : 0.65)
        case .tertiary:
            return Color.Mystic.brassGoldBorder.opacity(isHovered ? 0.65 : 0.25)
        case .danger:
            return Color.Mystic.crimsonStar.opacity(isHovered ? 1 : 0.68)
        case .ritual:
            return Color.Mystic.spiritualBlue.opacity(isHovered ? 0.9 : 0.55)
        }
    }

    private var borderStrokeStyle: StrokeStyle {
        StrokeStyle(
            lineWidth: borderWidth,
            lineCap: .round,
            lineJoin: .round,
            dash: borderDash
        )
    }

    private var borderWidth: CGFloat {
        if isIncreasedContrast || isFocused {
            return DesignTokens.Borders.heavy
        }
        return isHovered ? DesignTokens.Borders.standard : DesignTokens.Borders.hairline
    }

    private var borderDash: [CGFloat] {
        guard differentiateWithoutColor else { return [] }
        switch variant {
        case .danger:
            return [4, 2]
        case .ritual:
            return [1, 2]
        case .primary, .secondary, .tertiary:
            return []
        }
    }

    private var focusRingColor: Color {
        isIncreasedContrast ? Color.Mystic.textPrimary : Color.Mystic.textGoldAccent
    }

    private var shadowColor: Color {
        guard isEnabled, isHovered, appearsActive, !isIncreasedContrast else { return .clear }
        switch variant {
        case .primary:
            return Color.Mystic.brassGoldGlow
        case .ritual:
            return Color.Mystic.spiritualGlow
        case .danger:
            return Color.Mystic.crimsonGlow
        case .secondary, .tertiary:
            return .clear
        }
    }

    private var shadowRadius: CGFloat {
        guard isEnabled, isHovered, appearsActive, !isIncreasedContrast else { return 0 }
        switch variant {
        case .primary, .ritual, .danger:
            return 5
        case .secondary, .tertiary:
            return 0
        }
    }

    private var pressedScale: CGFloat {
        guard isEnabled, isPressed, !reduceMotion else { return 1 }
        return DesignTokens.Interaction.pressedScale
    }

    private var pressedOpacity: Double {
        guard isEnabled, isPressed else { return 1 }
        return DesignTokens.Interaction.pressedOpacity
    }
}
