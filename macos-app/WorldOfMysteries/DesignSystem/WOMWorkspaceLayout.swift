import SwiftUI

/// Stable app-window geometry for the World of Mysteries macOS client.
///
/// The minimum size is a Visual QA guarantee, while the default size is only a comfortable
/// starting point. Users remain free to resize the native macOS window.
public nonisolated enum WOMWindowMetrics: Sendable {
    public static let minimumWidth: CGFloat = 960
    public static let minimumHeight: CGFloat = 640
    public static let defaultWidth: CGFloat = 1180
    public static let defaultHeight: CGFloat = 760
}

/// Flexible width contract for native SwiftUI Inspector trailing-column presentation.
public nonisolated enum WOMInspectorMetrics: Sendable {
    public static let minimumWidth: CGFloat = 280
    public static let idealWidth: CGFloat = 320
    public static let maximumWidth: CGFloat = 420
}

/// Common responsive geometry used by two-pane workspace compositions.
public nonisolated enum WOMWorkspaceMetrics: Sendable {
    public static let standardGap: CGFloat = DesignTokens.Spacing.lg
    public static let compactGap: CGFloat = DesignTokens.Spacing.md
    public static let fateAnchorWidth: CGFloat = 280
}

/// Reusable two-pane composition that preserves a clear horizontal hierarchy when space allows
/// and falls back to a vertical stack instead of compressing readable content.
public struct WOMAdaptivePair<Primary: View, Secondary: View>: View {
    public let trailingIdealWidth: CGFloat
    public let spacing: CGFloat

    private let primary: Primary
    private let secondary: Secondary

    public init(
        trailingIdealWidth: CGFloat,
        spacing: CGFloat = WOMWorkspaceMetrics.standardGap,
        @ViewBuilder primary: () -> Primary,
        @ViewBuilder secondary: () -> Secondary
    ) {
        self.trailingIdealWidth = trailingIdealWidth
        self.spacing = spacing
        self.primary = primary()
        self.secondary = secondary()
    }

    public var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .top, spacing: spacing) {
                primary
                    .frame(maxWidth: .infinity, alignment: .leading)

                secondary
                    .frame(width: trailingIdealWidth, alignment: .topLeading)
            }

            VStack(alignment: .leading, spacing: spacing) {
                primary
                    .frame(maxWidth: .infinity, alignment: .leading)

                secondary
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
}

/// Standard content wrapper for a native SwiftUI Inspector.
///
/// Presentation state belongs to `.inspector(isPresented:content:)`; this view only standardizes
/// readable padding, scrolling, visual chrome and the flexible trailing-column width contract.
public struct WOMInspectorContent<Content: View>: View {
    private let content: Content

    public init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    public var body: some View {
        ScrollView {
            WOMOverlayPanel(role: .inspector) {
                content
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(DesignTokens.Spacing.sm)
        }
        .background(
            Color.Mystic.obsidianBase
                .overlay(WOMTextureLayer(.sacredSlate, opacity: 0.012))
        )
        .inspectorColumnWidth(
            min: WOMInspectorMetrics.minimumWidth,
            ideal: WOMInspectorMetrics.idealWidth,
            max: WOMInspectorMetrics.maximumWidth
        )
    }
}
