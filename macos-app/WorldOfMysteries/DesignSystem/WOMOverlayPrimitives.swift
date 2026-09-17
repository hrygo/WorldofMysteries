import SwiftUI

/// Visual roles for content presented inside native macOS overlays.
///
/// This type intentionally does not own presentation lifecycle. SwiftUI `.inspector`, `.popover`
/// and `.sheet` remain the source of truth for window level, focus, keyboard and accessibility.
public nonisolated enum WOMOverlayRole: String, CaseIterable, Sendable {
    case inspector
    case popover
    case sheet
    case hud
}

/// Stable semantic feedback roles shared by status banners and loading/empty feedback.
public nonisolated enum WOMFeedbackTone: String, CaseIterable, Sendable {
    case info
    case success
    case warning
    case danger

    public var statusIcon: WOMStatusIcon {
        switch self {
        case .info: .info
        case .success: .success
        case .warning: .warning
        case .danger: .danger
        }
    }

    public var semanticLabel: String {
        switch self {
        case .info: "信息"
        case .success: "成功"
        case .warning: "警告"
        case .danger: "危险"
        }
    }
}

/// Reusable visual chrome for content hosted by native macOS overlays.
///
/// The caller remains responsible for using the platform presentation API. This component only
/// supplies spacing, surface tone, texture, radius and accessible visual hierarchy.
public struct WOMOverlayPanel<Content: View>: View {
    public let role: WOMOverlayRole
    private let content: Content

    public init(
        role: WOMOverlayRole,
        @ViewBuilder content: () -> Content
    ) {
        self.role = role
        self.content = content()
    }

    public var body: some View {
        content
            .padding(contentPadding)
            .background(
                WOMPanelBackground(
                    tone: surfaceTone,
                    cornerRadius: cornerRadius,
                    texture: texture,
                    textureOpacity: textureOpacity
                )
            )
    }

    private var surfaceTone: WOMSurfaceTone {
        switch role {
        case .inspector: .panel
        case .popover: .floating
        case .sheet: .floating
        case .hud: .card
        }
    }

    private var texture: WOMTextureAsset? {
        switch role {
        case .inspector, .hud: .sacredSlate
        case .popover: .velvet
        case .sheet: .foolVeil
        }
    }

    private var textureOpacity: Double {
        switch role {
        case .inspector: 0.025
        case .popover: 0.035
        case .sheet: 0.03
        case .hud: 0.02
        }
    }

    private var cornerRadius: CGFloat {
        switch role {
        case .inspector: DesignTokens.Radii.md
        case .popover, .sheet: DesignTokens.Radii.lg
        case .hud: DesignTokens.Radii.sm
        }
    }

    private var contentPadding: CGFloat {
        switch role {
        case .inspector, .sheet: DesignTokens.LayoutInsets.cardPadding
        case .popover, .hud: DesignTokens.LayoutInsets.compactCardPadding
        }
    }
}

/// Native-loading presentation for engine waits, preparation and other indeterminate operations.
///
/// `ProgressView` owns the animation. No second custom spinner or infinite motion loop is created.
public struct WOMLoadingState: View {
    public let title: String
    public let message: String?
    public let source: WOMIconSource?
    public let tone: WOMFeedbackTone

    public init(
        title: String,
        message: String? = nil,
        source: WOMIconSource? = .status(.active),
        tone: WOMFeedbackTone = .info
    ) {
        self.title = title
        self.message = message
        self.source = source
        self.tone = tone
    }

    public var body: some View {
        HStack(alignment: .center, spacing: DesignTokens.Spacing.md) {
            if let source {
                WOMIcon(
                    source: source,
                    size: .prominent,
                    accessibilityLabel: nil
                )
                .foregroundStyle(accentColor)
            }

            ProgressView()
                .controlSize(.small)
                .tint(accentColor)
                .accessibilityLabel("正在加载")

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
                Text(title)
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)

                if let message {
                    Text(message)
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Spacer(minLength: 0)
        }
        .padding(DesignTokens.LayoutInsets.compactCardPadding)
        .background(
            WOMPanelBackground(
                tone: .card,
                cornerRadius: DesignTokens.Radii.md,
                texture: .sacredSlate,
                textureOpacity: 0.018
            )
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(tone.semanticLabel)：\(title)")
    }

    private var accentColor: Color {
        feedbackAccentColor(tone)
    }
}

/// Typed empty-state primitive for new visual-system call sites.
///
/// The legacy `MysticEmptyState(systemIcon:...)` API remains untouched for compatibility; new WOM
/// code should prefer this typed source so custom vector assets and platform symbols share one path.
public struct WOMEmptyState: View {
    public let source: WOMIconSource
    public let title: String
    public let message: String
    public let tone: WOMFeedbackTone
    public let actionTitle: String?
    public var onAction: (@MainActor () -> Void)?

    public init(
        source: WOMIconSource,
        title: String,
        message: String,
        tone: WOMFeedbackTone = .info,
        actionTitle: String? = nil,
        onAction: (@MainActor () -> Void)? = nil
    ) {
        self.source = source
        self.title = title
        self.message = message
        self.tone = tone
        self.actionTitle = actionTitle
        self.onAction = onAction
    }

    public var body: some View {
        VStack(spacing: DesignTokens.Spacing.sm) {
            WOMIcon(
                source: source,
                size: .large,
                accessibilityLabel: nil
            )
            .foregroundStyle(accentColor.opacity(0.82))

            Text(title)
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.textPrimary)
                .fixedSize(horizontal: false, vertical: true)

            Text(message)
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .multilineTextAlignment(.center)
                .lineSpacing(DesignTokens.TypographyMetrics.compactLineSpacing)
                .fixedSize(horizontal: false, vertical: true)

            if let actionTitle, let onAction {
                Button(actionTitle, action: onAction)
                    .buttonStyle(WOMButtonStyle(.secondary))
                    .padding(.top, DesignTokens.Spacing.xxs)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(DesignTokens.LayoutInsets.cardPadding)
        .background(
            WOMPanelBackground(
                tone: .card,
                cornerRadius: DesignTokens.Radii.md,
                texture: .sacredSlate,
                textureOpacity: 0.018
            )
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel("\(tone.semanticLabel)：\(title)")
    }

    private var accentColor: Color {
        feedbackAccentColor(tone)
    }
}

/// Persistent semantic feedback banner for non-modal status communication.
public struct WOMStatusBanner: View {
    public let tone: WOMFeedbackTone
    public let title: String
    public let message: String?
    public let actionTitle: String?
    public var onAction: (@MainActor () -> Void)?

    @Environment(\.accessibilityDifferentiateWithoutColor) private var differentiateWithoutColor
    @Environment(\.colorSchemeContrast) private var colorSchemeContrast

    public init(
        tone: WOMFeedbackTone,
        title: String,
        message: String? = nil,
        actionTitle: String? = nil,
        onAction: (@MainActor () -> Void)? = nil
    ) {
        self.tone = tone
        self.title = title
        self.message = message
        self.actionTitle = actionTitle
        self.onAction = onAction
    }

    public var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .center, spacing: DesignTokens.Spacing.md) {
                statusIdentity
                Spacer(minLength: DesignTokens.Spacing.sm)
                actionButton
            }

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                statusIdentity
                actionButton
            }
        }
        .padding(DesignTokens.LayoutInsets.compactCardPadding)
        .background(
            WOMPanelBackground(
                tone: .card,
                cornerRadius: DesignTokens.Radii.md,
                texture: .sacredSlate,
                textureOpacity: 0.018
            )
        )
        .overlay(alignment: .leading) {
            RoundedRectangle(cornerRadius: 2, style: .continuous)
                .fill(accentColor)
                .frame(width: railWidth)
                .padding(.vertical, DesignTokens.Spacing.xs)
                .accessibilityHidden(true)
        }
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.Radii.md, style: .continuous)
                .stroke(
                    accentColor.opacity(colorSchemeContrast == .increased ? 0.9 : 0.34),
                    style: StrokeStyle(
                        lineWidth: colorSchemeContrast == .increased
                            ? DesignTokens.Borders.standard
                            : DesignTokens.Borders.hairline,
                        dash: differentiateWithoutColor ? dashPattern : []
                    )
                )
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("\(tone.semanticLabel)：\(title)")
    }

    private var statusIdentity: some View {
        HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
            WOMIcon(
                status: tone.statusIcon,
                size: .standard,
                accessibilityLabel: nil
            )
            .foregroundStyle(accentColor)
            .padding(.top, 1)

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
                Text(title)
                    .font(Font.Mystic.bodyMedium)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.Mystic.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)

                if let message {
                    Text(message)
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private var actionButton: some View {
        if let actionTitle, let onAction {
            Button(actionTitle, action: onAction)
                .buttonStyle(WOMButtonStyle(.tertiary))
        }
    }

    private var accentColor: Color {
        feedbackAccentColor(tone)
    }

    private var railWidth: CGFloat {
        differentiateWithoutColor ? 5 : 3
    }

    private var dashPattern: [CGFloat] {
        switch tone {
        case .info: [2, 2]
        case .success: []
        case .warning: [5, 3]
        case .danger: [2, 2, 7, 2]
        }
    }
}

@MainActor
private func feedbackAccentColor(_ tone: WOMFeedbackTone) -> Color {
    switch tone {
    case .info:
        Color.Mystic.spiritualBlue
    case .success:
        Color.Mystic.statusOnline
    case .warning:
        Color.Mystic.statusWarning
    case .danger:
        Color.Mystic.statusDanger
    }
}
