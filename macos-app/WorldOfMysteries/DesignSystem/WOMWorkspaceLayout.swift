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
    /// 命运页局势卷宗的理想宽度：与 280pt 锚点并列时仍能容纳 3-4 行中文段落。
    public static let fateSituationIdealWidth: CGFloat = 460
    /// 世界首页左栏（世界脉动 + 可观察事件）的理想宽度。
    public static let worldPulseIdealWidth: CGFloat = 460
    /// 世界首页右栏（廷根市档案 + 观察者询问）的理想宽度。
    public static let worldDossierIdealWidth: CGFloat = 380
}

/// Three-band workspace column: status bar, scrolling main surface, persistent bottom bar.
///
/// Layout contract — every band declares an explicit width, and the middle band absorbs the
/// remaining height. Without those constraints SwiftUI hugs the scroll surface to its content and
/// stretches the flexible bar backgrounds across the whole column, so translucent panels end up
/// painting over the main content (readability collapse). Keep this container as the only
/// supported way to compose the app's workspace column.
public struct WOMWorkspaceColumn<Top: View, Main: View, Bottom: View>: View {
    private let top: Top
    private let main: Main
    private let bottom: Bottom

    public init(
        @ViewBuilder top: () -> Top,
        @ViewBuilder main: () -> Main,
        @ViewBuilder bottom: () -> Bottom
    ) {
        self.top = top()
        self.main = main()
        self.bottom = bottom()
    }

    public var body: some View {
        VStack(spacing: 0) {
            top
                .frame(maxWidth: .infinity)

            main
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            bottom
                .frame(maxWidth: .infinity)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// Reusable two-pane composition that preserves a clear horizontal hierarchy when space allows
/// and falls back to a vertical stack instead of compressing readable content.
public struct WOMAdaptivePair<Primary: View, Secondary: View>: View {
    public let trailingIdealWidth: CGFloat
    /// 主栏的理想宽度。
    ///
    /// `ViewThatFits` 依据候选布局的**理想尺寸**决定取舍：若主栏内容（长段落）的理想宽度不被钉住，
    /// 它的理想尺寸会等于整段文字不换行的宽度，于是双栏候选永远「放不下」，
    /// 在默认 1180×760 与最小 960×640 下都会退化成纵向堆叠。
    /// 因此主栏显式声明理想宽度，双栏在内容宽度 ≥ `primaryIdealWidth + trailingIdealWidth + spacing`
    /// 时才会出现，更窄时仍按契约回退为纵向堆叠而不是压缩文字。
    public let primaryIdealWidth: CGFloat
    public let spacing: CGFloat

    private let primary: Primary
    private let secondary: Secondary

    public init(
        trailingIdealWidth: CGFloat,
        primaryIdealWidth: CGFloat = 420,
        spacing: CGFloat = WOMWorkspaceMetrics.standardGap,
        @ViewBuilder primary: () -> Primary,
        @ViewBuilder secondary: () -> Secondary
    ) {
        self.trailingIdealWidth = trailingIdealWidth
        self.primaryIdealWidth = primaryIdealWidth
        self.spacing = spacing
        self.primary = primary()
        self.secondary = secondary()
    }

    public var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .top, spacing: spacing) {
                primary
                    .frame(
                        minWidth: 0,
                        idealWidth: primaryIdealWidth,
                        maxWidth: .infinity,
                        alignment: .leading
                    )

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

/// Preview-only QA host that exercises the real SwiftUI Inspector presentation path.
/// It deliberately contains long localized content so the 280pt minimum can be inspected for
/// wrapping, contrast, spacing and collision regressions without creating fake production data.
private struct WOMInspectorVisualQAPreview: View {
    @State private var isInspectorPresented = true

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
            Text("Window / Inspector Visual QA")
                .font(Font.Mystic.titleMedium)
                .foregroundStyle(Color.Mystic.textGoldAccent)

            Text("主工作区保持 13pt+ 正文与自然换行；Inspector 由系统呈现，不由 WOM 模拟窗口层级。")
                .font(Font.Mystic.bodyMedium)
                .foregroundStyle(Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            Button(isInspectorPresented ? "隐藏 Inspector" : "显示 Inspector") {
                isInspectorPresented.toggle()
            }
            .buttonStyle(WOMButtonStyle(.secondary))

            WOMAdaptivePair(trailingIdealWidth: WOMWorkspaceMetrics.fateAnchorWidth) {
                WOMStatusBanner(
                    tone: .info,
                    title: "主内容区域",
                    message: "双栏空间不足时自动降级为纵向，而不是压缩文字。"
                )
            } secondary: {
                WOMAchievementSeal(
                    title: "Inspector / Workspace Layout Contract",
                    detail: "Long English metadata and 中文说明都应保持完整、工整且可辨认。",
                    state: .completed
                )
            }
        }
        .padding(DesignTokens.LayoutInsets.panelPadding)
        .frame(
            minWidth: WOMWindowMetrics.minimumWidth,
            minHeight: WOMWindowMetrics.minimumHeight
        )
        .background(Color.Mystic.obsidianBase)
        .inspector(isPresented: $isInspectorPresented) {
            WOMInspectorContent {
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
                    Text("属性检查器 · Inspector")
                        .font(Font.Mystic.titleSmall)
                        .foregroundStyle(Color.Mystic.textPrimary)

                    Text("280pt minimum width stress: 极端长中文属性说明与 English metadata 必须自然换行，不能互相覆盖，也不能通过缩小字体逃避空间不足。")
                        .font(Font.Mystic.bodyMedium)
                        .foregroundStyle(Color.Mystic.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)

                    WOMRelationBadge(
                        "长期可靠联系 / Trusted relationship with localized metadata",
                        role: .trusted,
                        detail: "Inspector 内同样遵守 11pt metadata 与非 color-only 状态表达。"
                    )

                    WOMCooldownIndicator(
                        "仪式冷却状态",
                        state: .cooling(
                            progress: 0.42,
                            remainingLabel: "剩余信息由 Runtime 提供，不在 Inspector 内部计时"
                        )
                    )
                }
            }
        }
    }
}

#Preview("Native Inspector · Visual QA") {
    WOMInspectorVisualQAPreview()
}
