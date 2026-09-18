import SwiftUI

/// Global product identity for World of Mysteries.
///
/// The visual source is intentionally shared with the shipping AppIcon so the
/// Dock/Finder identity and in-app brand mark cannot drift into separate brands.
public enum WOMBrandAsset: String, Sendable {
    case primary = "wom.brand.primary"
}

public struct WOMBrandMark: View {
    private let size: CGFloat
    private let accessibilityLabel: String?

    public init(size: CGFloat = 32, accessibilityLabel: String? = nil) {
        self.size = size
        self.accessibilityLabel = accessibilityLabel
    }

    @ViewBuilder
    public var body: some View {
        let mark = Image(WOMBrandAsset.primary.rawValue)
            .resizable()
            .scaledToFit()
            .frame(width: size, height: size)

        if let accessibilityLabel {
            mark.accessibilityLabel(Text(accessibilityLabel))
        } else {
            mark.accessibilityHidden(true)
        }
    }
}
