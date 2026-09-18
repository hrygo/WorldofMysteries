import SwiftUI

/// Semantic surface families for reusable World of Mysteries containers.
public nonisolated enum WOMSurfaceTone: CaseIterable, Sendable {
    case panel
    case card
    case floating
    case ritual
    case parchment
}

/// Opaque window canvas for the app's dark-only design language.
///
/// The canvas owns the single opaque backdrop of a window. Panels, cards and scroll surfaces
/// layer on top of it; nothing in the app is allowed to depend on the system window backdrop,
/// because that backdrop follows the macOS appearance and silently swaps to a light surface.
public struct WOMWindowCanvas: View {
    public let texture: WOMTextureAsset?
    public let textureOpacity: Double

    public init(
        texture: WOMTextureAsset? = .sacredSlate,
        textureOpacity: Double = 0.012
    ) {
        self.texture = texture
        self.textureOpacity = textureOpacity
    }

    public var body: some View {
        Color.Mystic.obsidianBase
            .overlay {
                if let texture {
                    WOMTextureLayer(texture, opacity: textureOpacity)
                }
            }
    }
}

/// Reusable texture overlay with accessibility-aware transparency behavior.
public struct WOMTextureLayer: View {
    public let asset: WOMTextureAsset
    public let opacity: Double
    public let blendMode: BlendMode

    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var colorSchemeContrast

    public init(
        _ asset: WOMTextureAsset,
        opacity: Double = 0.10,
        blendMode: BlendMode = .normal
    ) {
        self.asset = asset
        self.opacity = opacity
        self.blendMode = blendMode
    }

    public var body: some View {
        Image(asset.rawValue)
            .resizable()
            .scaledToFill()
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
            .opacity(effectiveOpacity)
            .blendMode(blendMode)
            .clipped()
            .allowsHitTesting(false)
            .accessibilityHidden(true)
    }

    private var effectiveOpacity: Double {
        if reduceTransparency {
            return min(opacity, 0.025)
        }
        if colorSchemeContrast == .increased {
            return min(opacity, 0.05)
        }
        return opacity
    }
}

/// Programmatic background for panels, cards, inspectors and ritual surfaces.
public struct WOMPanelBackground: View {
    public let tone: WOMSurfaceTone
    public let cornerRadius: CGFloat
    public let texture: WOMTextureAsset?
    public let textureOpacity: Double

    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var colorSchemeContrast
    @Environment(\.appearsActive) private var appearsActive

    public init(
        tone: WOMSurfaceTone = .panel,
        cornerRadius: CGFloat = DesignTokens.Radii.md,
        texture: WOMTextureAsset? = nil,
        textureOpacity: Double = 0.08
    ) {
        self.tone = tone
        self.cornerRadius = cornerRadius
        self.texture = texture
        self.textureOpacity = textureOpacity
    }

    public var body: some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)

        // 背景必须「以填充面为根、纹理与描边走 overlay」。
        // 若把 Shape 放进 ZStack 作为背景根，SwiftUI 会按容器尺寸（而非内容尺寸）布局该背景，
        // 于是半透明面板会铺满整个工作列并盖住主内容，造成大面积不可读。
        fillColor
            .overlay {
                if let texture {
                    WOMTextureLayer(texture, opacity: textureOpacity)
                }
            }
            .overlay {
                shape.stroke(strokeColor, lineWidth: strokeWidth)
            }
        .compositingGroup()
        .clipShape(shape)
        .shadow(color: shadowColor, radius: shadowRadius, y: shadowOffsetY)
    }

    private var isIncreasedContrast: Bool {
        colorSchemeContrast == .increased
    }

    private var fillColor: Color {
        switch tone {
        case .panel:
            Color.Mystic.obsidianElevated
        case .card:
            Color.Mystic.obsidianCard
        case .floating:
            reduceTransparency ? Color.Mystic.obsidianElevated : Color.Mystic.obsidianGlass
        case .ritual:
            Color.Mystic.deepVoid
        case .parchment:
            Color.Mystic.parchmentCard
        }
    }

    private var strokeColor: Color {
        if isIncreasedContrast {
            switch tone {
            case .parchment:
                return Color.Mystic.parchmentInkSecondary
            case .ritual:
                return Color.Mystic.spiritualBlue
            case .panel, .card, .floating:
                return Color.Mystic.textGoldAccent
            }
        }

        let activityOpacity = appearsActive ? 1.0 : 0.6
        switch tone {
        case .parchment:
            return Color.Mystic.parchmentBorder.opacity(0.9 * activityOpacity)
        case .ritual:
            return Color.Mystic.spiritualBlue.opacity(0.38 * activityOpacity)
        case .panel, .card, .floating:
            return Color.Mystic.brassGoldBorder.opacity(0.62 * activityOpacity)
        }
    }

    private var strokeWidth: CGFloat {
        isIncreasedContrast ? DesignTokens.Borders.standard : DesignTokens.Borders.hairline
    }

    private var shadowColor: Color {
        guard appearsActive, !isIncreasedContrast else { return .clear }
        switch tone {
        case .floating:
            return Color.black.opacity(0.34)
        case .ritual:
            return Color.Mystic.spiritualGlow.opacity(0.45)
        case .panel, .card, .parchment:
            return .clear
        }
    }

    private var shadowRadius: CGFloat {
        guard appearsActive, !isIncreasedContrast else { return 0 }
        return switch tone {
        case .floating: 14
        case .ritual: 7
        case .panel, .card, .parchment: 0
        }
    }

    private var shadowOffsetY: CGFloat {
        tone == .floating && appearsActive && !isIncreasedContrast ? 6 : 0
    }
}

/// Selection/hover chrome layered on top of the base card surface.
public struct WOMCardChrome: ViewModifier {
    public let tone: WOMSurfaceTone
    public let texture: WOMTextureAsset?
    public let isSelected: Bool
    public let isHovered: Bool
    public let cornerRadius: CGFloat

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.accessibilityDifferentiateWithoutColor) private var differentiateWithoutColor
    @Environment(\.colorSchemeContrast) private var colorSchemeContrast
    @Environment(\.appearsActive) private var appearsActive

    public init(
        tone: WOMSurfaceTone = .card,
        texture: WOMTextureAsset? = nil,
        isSelected: Bool = false,
        isHovered: Bool = false,
        cornerRadius: CGFloat = DesignTokens.Radii.md
    ) {
        self.tone = tone
        self.texture = texture
        self.isSelected = isSelected
        self.isHovered = isHovered
        self.cornerRadius = cornerRadius
    }

    public func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)

        content
            .background(
                WOMPanelBackground(
                    tone: tone,
                    cornerRadius: cornerRadius,
                    texture: texture
                )
            )
            .overlay(
                shape.stroke(chromeStrokeColor, lineWidth: chromeStrokeWidth)
            )
            .overlay(
                shape
                    .inset(by: 3)
                    .stroke(
                        differentiateWithoutColor && isSelected
                            ? chromeStrokeColor.opacity(0.9)
                            : Color.clear,
                        lineWidth: DesignTokens.Borders.hairline
                    )
            )
            .shadow(color: chromeShadowColor, radius: chromeShadowRadius)
            .animation(reduceMotion ? nil : DesignTokens.Interaction.selectionSpring, value: isSelected)
            .animation(reduceMotion ? nil : DesignTokens.Interaction.hoverAnimation, value: isHovered)
    }

    private var isIncreasedContrast: Bool {
        colorSchemeContrast == .increased
    }

    private var chromeStrokeColor: Color {
        if isSelected {
            return isIncreasedContrast ? Color.Mystic.textGoldAccent : Color.Mystic.brassGoldPrimary
        }
        if isHovered {
            return isIncreasedContrast
                ? Color.Mystic.textSecondary
                : Color.Mystic.brassGoldBorder.opacity(0.9)
        }
        return Color.clear
    }

    private var chromeStrokeWidth: CGFloat {
        if isSelected {
            return isIncreasedContrast
                ? DesignTokens.Borders.heavy
                : DesignTokens.Interaction.selectedBorderWidth
        }
        if isHovered {
            return isIncreasedContrast ? DesignTokens.Borders.standard : DesignTokens.Borders.hairline
        }
        return DesignTokens.Borders.hairline
    }

    private var chromeShadowColor: Color {
        guard appearsActive, !isIncreasedContrast else { return .clear }
        if isSelected {
            return Color.Mystic.brassGoldGlow
        }
        if isHovered {
            return Color.Mystic.brassGoldGlow.opacity(0.45)
        }
        return .clear
    }

    private var chromeShadowRadius: CGFloat {
        guard appearsActive, !isIncreasedContrast else { return 0 }
        return isSelected ? DesignTokens.Interaction.selectedShadowRadius : (isHovered ? 3 : 0)
    }
}

/// Typography treatment for compact section headers.
public struct WOMSectionHeaderStyle: ViewModifier {
    @Environment(\.colorSchemeContrast) private var colorSchemeContrast
    @Environment(\.appearsActive) private var appearsActive

    public init() {}

    public func body(content: Content) -> some View {
        content
            .font(Font.Mystic.caption)
            .tracking(DesignTokens.TypographyMetrics.captionTracking)
            .foregroundStyle(headerColor)
    }

    private var headerColor: Color {
        if colorSchemeContrast == .increased {
            return Color.Mystic.textGoldAccent
        }
        return Color.Mystic.textGoldAccent.opacity(appearsActive ? 1 : 0.72)
    }
}

/// Lightweight programmatic divider ornament; no bitmap asset required.
public struct WOMDividerOrnament: View {
    public let opacity: Double

    @Environment(\.colorSchemeContrast) private var colorSchemeContrast

    public init(opacity: Double = 0.55) {
        self.opacity = opacity
    }

    public var body: some View {
        HStack(spacing: DesignTokens.Spacing.sm) {
            Rectangle()
                .frame(height: dividerWidth)

            Rectangle()
                .frame(width: 5, height: 5)
                .rotationEffect(.degrees(45))

            Rectangle()
                .frame(height: dividerWidth)
        }
        .foregroundStyle(dividerColor)
        .accessibilityHidden(true)
    }

    private var dividerWidth: CGFloat {
        colorSchemeContrast == .increased
            ? DesignTokens.Borders.standard
            : DesignTokens.Borders.hairline
    }

    private var dividerColor: Color {
        colorSchemeContrast == .increased
            ? Color.Mystic.textGoldAccent
            : Color.Mystic.brassGoldBorder.opacity(opacity)
    }
}

public extension View {
    func womCardChrome(
        tone: WOMSurfaceTone = .card,
        texture: WOMTextureAsset? = nil,
        isSelected: Bool = false,
        isHovered: Bool = false,
        cornerRadius: CGFloat = DesignTokens.Radii.md
    ) -> some View {
        modifier(
            WOMCardChrome(
                tone: tone,
                texture: texture,
                isSelected: isSelected,
                isHovered: isHovered,
                cornerRadius: cornerRadius
            )
        )
    }

    func womSectionHeaderStyle() -> some View {
        modifier(WOMSectionHeaderStyle())
    }
}
