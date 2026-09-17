import SwiftUI

/// The supported icon size scale for World of Mysteries controls and surfaces.
public nonisolated enum WOMIconSize: CaseIterable, Sendable {
    case compact
    case standard
    case prominent
    case large

    public var points: CGFloat {
        switch self {
        case .compact: 16
        case .standard: 20
        case .prominent: 24
        case .large: 32
        }
    }

    /// Platform symbols keep their native optical rendering rather than being stretched as
    /// arbitrary vector artwork. Larger semantic icons receive slightly stronger weight.
    public var symbolWeight: Font.Weight {
        switch self {
        case .compact, .standard: .medium
        case .prominent, .large: .semibold
        }
    }
}

/// A typed source for iconography used by `WOMIcon`.
public nonisolated enum WOMIconSource: Sendable {
    case asset(WOMIconAsset)
    case navigation(WOMNavigationIconAsset)
    case system(WOMSystemIcon)
    case status(WOMStatusIcon)
}

/// Unified rendering entry point for World of Mysteries iconography.
///
/// Custom vector assets and SF Symbols share the same sizing and accessibility policy. Color,
/// hover/pressed/selected state and motion remain responsibilities of the surrounding style.
public struct WOMIcon: View {
    public let source: WOMIconSource
    public let size: WOMIconSize
    public let accessibilityLabel: String?

    public init(
        source: WOMIconSource,
        size: WOMIconSize = .standard,
        accessibilityLabel: String? = nil
    ) {
        self.source = source
        self.size = size
        self.accessibilityLabel = accessibilityLabel
    }

    public init(
        _ asset: WOMIconAsset,
        size: WOMIconSize = .standard,
        accessibilityLabel: String? = nil
    ) {
        self.init(source: .asset(asset), size: size, accessibilityLabel: accessibilityLabel)
    }

    public init(
        navigation asset: WOMNavigationIconAsset,
        size: WOMIconSize = .standard,
        accessibilityLabel: String? = nil
    ) {
        self.init(source: .navigation(asset), size: size, accessibilityLabel: accessibilityLabel)
    }

    public init(
        system icon: WOMSystemIcon,
        size: WOMIconSize = .standard,
        accessibilityLabel: String? = nil
    ) {
        self.init(source: .system(icon), size: size, accessibilityLabel: accessibilityLabel)
    }

    public init(
        status icon: WOMStatusIcon,
        size: WOMIconSize = .standard,
        accessibilityLabel: String? = nil
    ) {
        self.init(source: .status(icon), size: size, accessibilityLabel: accessibilityLabel)
    }

    @ViewBuilder
    private var renderedIcon: some View {
        switch source {
        case .asset(let asset):
            customVector(named: asset.rawValue)
        case .navigation(let asset):
            customVector(named: asset.rawValue)
        case .system(let icon):
            platformSymbol(named: icon.rawValue)
        case .status(let icon):
            platformSymbol(named: icon.rawValue)
        }
    }

    private func customVector(named name: String) -> some View {
        Image(name)
            .renderingMode(.template)
            .resizable()
            .scaledToFit()
            .frame(width: size.points, height: size.points)
    }

    private func platformSymbol(named name: String) -> some View {
        Image(systemName: name)
            .symbolRenderingMode(.monochrome)
            .font(.system(size: size.points, weight: size.symbolWeight))
            .frame(width: size.points, height: size.points, alignment: .center)
    }

    @ViewBuilder
    public var body: some View {
        if let accessibilityLabel {
            renderedIcon.accessibilityLabel(Text(accessibilityLabel))
        } else {
            renderedIcon.accessibilityHidden(true)
        }
    }
}
