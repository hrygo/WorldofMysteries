import AppKit
import SwiftUI

/// Semantic fallback displayed whenever artwork is unavailable or has transparent regions.
public nonisolated enum WOMArtworkFallback: Sendable {
    case icon(WOMIconSource)
    case systemImage(String)
}

/// Runtime presentation for premium artwork with a stable semantic fallback.
///
/// Asset existence is resolved through AppKit so alpha-bearing object art never reveals a
/// fallback icon behind transparent regions. Missing payloads retain the established semantic
/// icon instead of producing an empty identity surface.
public struct WOMArtworkView: View {
    public let assetName: String
    public let fallback: WOMArtworkFallback
    public let fallbackTint: Color
    public let contentMode: ContentMode
    public let accessibilityLabel: String?

    public init(
        assetName: String,
        fallback: WOMArtworkFallback,
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

    public init(
        assetName: String,
        fallback: WOMIconSource,
        fallbackTint: Color = Color.Mystic.textTertiary,
        contentMode: ContentMode = .fill,
        accessibilityLabel: String? = nil
    ) {
        self.init(
            assetName: assetName,
            fallback: .icon(fallback),
            fallbackTint: fallbackTint,
            contentMode: contentMode,
            accessibilityLabel: accessibilityLabel
        )
    }

    @ViewBuilder
    public var body: some View {
        let artwork = ZStack {
            Color.Mystic.obsidianElevated

            if let image = NSImage(named: NSImage.Name(assetName)) {
                Image(nsImage: image)
                    .resizable()
                    .aspectRatio(contentMode: contentMode)
                    .accessibilityHidden(true)
            } else {
                fallbackView
            }
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

    @ViewBuilder
    private var fallbackView: some View {
        switch fallback {
        case .icon(let source):
            WOMIcon(
                source: source,
                size: .large,
                accessibilityLabel: nil
            )
            .foregroundStyle(fallbackTint.opacity(0.72))
        case .systemImage(let name):
            Image(systemName: name)
                .font(.system(size: 54, weight: .ultraLight))
                .foregroundStyle(fallbackTint.opacity(0.72))
                .accessibilityHidden(true)
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
