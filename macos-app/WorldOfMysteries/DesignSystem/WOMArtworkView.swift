import SwiftUI

/// Semantic fallback used while an artwork payload is unavailable or fails to render.
///
/// The fallback remains behind the image at all times. A missing named Asset Catalog image is
/// transparent, so the typed fallback stays visible without requiring a second resource lookup.
public struct WOMArtworkView: View {
    public let assetName: String
    public let fallback: WOMIconSource
    public let fallbackTint: Color
    public let contentMode: ContentMode
    public let accessibilityLabel: String?

    public init(
        assetName: String,
        fallback: WOMIconSource,
        fallbackTint: Color = Color.Mystic.textTertiary,
        contentMode: ContentMode = .fill,
        accessibilityLabel: String? = nil
    ) {
        self.assetName = assetName
        self.fallback = fallback
        self.fallbackTint = fallbackTint
        self.contentMode = contentMode
        self.accessibilityLabel = accessibilityLabel
    }

    @ViewBuilder
    public var body: some View {
        let artwork = ZStack {
            Color.Mystic.obsidianElevated

            WOMIcon(
                source: fallback,
                size: .large,
                accessibilityLabel: nil
            )
            .foregroundStyle(fallbackTint.opacity(0.72))

            Image(assetName)
                .resizable()
                .aspectRatio(contentMode: contentMode)
                .accessibilityHidden(true)
        }
        .clipped()

        if let accessibilityLabel {
            artwork
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(Text(accessibilityLabel))
        } else {
            artwork.accessibilityHidden(true)
        }
    }
}

/// Stable text-support overlay for premium artwork.
///
/// The component never attempts to infer image luminance. Call sites choose a semantic edge that
/// matches the approved quiet zone from the production brief. Increased Contrast receives a
/// denser support layer without mutating the artwork itself.
public struct WOMArtworkScrim: View {
    public nonisolated enum Edge: Sendable {
        case leading
        case trailing
        case top
        case bottom
    }

    public let edge: Edge
    public let strength: Double

    @Environment(\.colorSchemeContrast) private var colorSchemeContrast

    public init(edge: Edge, strength: Double = 0.82) {
        self.edge = edge
        self.strength = min(max(strength, 0), 1)
    }

    public var body: some View {
        LinearGradient(
            colors: [
                Color.Mystic.obsidianBase.opacity(effectiveStrength),
                Color.Mystic.obsidianBase.opacity(effectiveStrength * 0.55),
                Color.Mystic.obsidianBase.opacity(0),
            ],
            startPoint: startPoint,
            endPoint: endPoint
        )
        .accessibilityHidden(true)
        .allowsHitTesting(false)
    }

    private var effectiveStrength: Double {
        colorSchemeContrast == .increased ? min(1, strength + 0.12) : strength
    }

    private var startPoint: UnitPoint {
        switch edge {
        case .leading: .leading
        case .trailing: .trailing
        case .top: .top
        case .bottom: .bottom
        }
    }

    private var endPoint: UnitPoint {
        switch edge {
        case .leading: .trailing
        case .trailing: .leading
        case .top: .bottom
        case .bottom: .top
        }
    }
}
