import SwiftUI

/// Semantic surface families for reusable World of Mysteries containers.
public nonisolated enum WOMSurfaceTone: CaseIterable, Sendable {
    case panel
    case card
    case floating
    case ritual
    case parchment
}

/// Reusable texture overlay with accessibility-aware transparency behavior.
public struct WOMTextureLayer: View {
    public let asset: WOMTextureAsset
    public let opacity: Double
    public let blendMode: BlendMode

    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    public init(
        _ asset: WOMTextureAsset,
        opacity: Double = 0.10,
        blendMode: BlendMode = .softLight
    ) {
        self.asset = asset
        self.opacity = opacity
        self.blendMode = blendMode
    }

    public var body: some View {
        Image(asset.rawValue)
            .resizable()
            .scaledToFill()
            .opacity(reduceTransparency ? min(opacity, 0.025) : opacity)
            .blendMode(blendMode)
            .clipped()
            .allowsHitTesting(false)
            .accessibilityHidden(true)
    }
}

/// Programmatic background for panels, cards, inspectors and ritual surfaces.
public struct WOMPanelBackground: View {
    public let tone: WOMSurfaceTone
    public let cornerRadius: CGFloat
    public let texture: WOMTextureAsset?
    public let textureOpacity: Double

    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

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

        ZStack {
            shape.fill(fillColor)

            if let texture {
                WOMTextureLayer(texture, opacity: textureOpacity)
                    .clipShape(shape)
            }

            shape.stroke(strokeColor, lineWidth: DesignTokens.Borders.hairline)
        }
        .clipShape(shape)
        .shadow(color: shadowColor, radius: shadowRadius, y: shadowOffsetY)
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
        switch tone {
        case .parchment:
            Color.Mystic.parchmentBorder.opacity(0.9)
        case .ritual:
            Color.Mystic.spiritualBlue.opacity(0.38)
        case .panel, .card, .floating:
            Color.Mystic.brassGoldBorder.opacity(0.62)
        }
    }

    private var shadowColor: Color {
        switch tone {
        case .floating:
            Color.black.opacity(0.34)
        case .ritual:
            Color.Mystic.spiritualGlow.opacity(0.45)
        case .panel, .card, .parchment:
            .clear
        }
    }

    private var shadowRadius: CGFloat {
        switch tone {
        case .floating: 14
        case .ritual: 7
        case .panel, .card, .parchment: 0
        }
    }

    private var shadowOffsetY: CGFloat {
        tone == .floating ? 6 : 0
    }
}

/// Selection/hover chrome layered on top of the base card surface.
public struct WOMCardChrome: ViewModifier {
    public let tone: WOMSurfaceTone
    public let texture: WOMTextureAsset?
    public let isSelected: Bool
    public let isHovered: Bool
    public let cornerRadius: CGFloat

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
                shape.stroke(
                    chromeStrokeColor,
                    lineWidth: isSelected
                        ? DesignTokens.Interaction.selectedBorderWidth
                        : DesignTokens.Borders.hairline
                )
            )
            .shadow(
                color: isSelected
                    ? Color.Mystic.brassGoldGlow
                    : (isHovered ? Color.Mystic.brassGoldGlow.opacity(0.45) : .clear),
                radius: isSelected ? DesignTokens.Interaction.selectedShadowRadius : 3
            )
            .animation(DesignTokens.Interaction.selectionSpring, value: isSelected)
            .animation(DesignTokens.Interaction.hoverAnimation, value: isHovered)
    }

    private var chromeStrokeColor: Color {
        if isSelected {
            return Color.Mystic.brassGoldPrimary
        }
        if isHovered {
            return Color.Mystic.brassGoldBorder.opacity(0.9)
        }
        return Color.clear
    }
}

/// Typography treatment for compact section headers.
public struct WOMSectionHeaderStyle: ViewModifier {
    public init() {}

    public func body(content: Content) -> some View {
        content
            .font(Font.Mystic.caption)
            .tracking(DesignTokens.TypographyMetrics.captionTracking)
            .foregroundStyle(Color.Mystic.textGoldAccent)
    }
}

/// Lightweight programmatic divider ornament; no bitmap asset required.
public struct WOMDividerOrnament: View {
    public let opacity: Double

    public init(opacity: Double = 0.55) {
        self.opacity = opacity
    }

    public var body: some View {
        HStack(spacing: DesignTokens.Spacing.sm) {
            Rectangle()
                .frame(height: DesignTokens.Borders.hairline)

            Rectangle()
                .frame(width: 5, height: 5)
                .rotationEffect(.degrees(45))

            Rectangle()
                .frame(height: DesignTokens.Borders.hairline)
        }
        .foregroundStyle(Color.Mystic.brassGoldBorder.opacity(opacity))
        .accessibilityHidden(true)
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
