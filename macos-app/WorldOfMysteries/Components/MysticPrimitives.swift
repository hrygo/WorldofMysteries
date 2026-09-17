import SwiftUI

// MARK: - 通用语义色调体系 (Semantic Tones)

/// 跨组件统一的六档语义色调：所有徽章、状态点、计量条、分割线共用同一套语义映射，
/// 避免各组件各自硬编码 `Color.Mystic.*` 造成的语义漂移。
public enum MysticTone: String, Sendable, CaseIterable {
    /// 暗金：正典、灵性权威、主行动
    case gold
    /// 青碧：在线、稳定、可用
    case teal
    /// 灵蓝：灵性读数、非凡信息
    case azure
    /// 琥珀：预警、干扰、需留意
    case amber
    /// 猩红：危险、失效、丧失
    case crimson
    /// 中性：次要元数据、未激活
    case neutral

    public var accent: Color {
        switch self {
        case .gold: return Color.Mystic.brassGoldPrimary
        case .teal: return Color.Mystic.statusOnline
        case .azure: return Color.Mystic.spiritualBlue
        case .amber: return Color.Mystic.statusWarning
        case .crimson: return Color.Mystic.statusDanger
        case .neutral: return Color.Mystic.textTertiary
        }
    }

    /// Readable semantic foreground for text placed on the app's dark surfaces.
    /// Accent color remains available for rails, fills, dots and borders; low-contrast semantic
    /// hues must not carry critical 11–13pt text by themselves.
    public var readableForeground: Color {
        switch self {
        case .gold:
            Color.Mystic.brassGoldPrimary
        case .teal:
            Color.Mystic.statusOnline
        case .azure, .crimson:
            Color.Mystic.textPrimary
        case .amber:
            Color.Mystic.statusWarning
        case .neutral:
            Color.Mystic.textSecondary
        }
    }

    public var semanticLabel: String {
        switch self {
        case .gold: return "正典灵性"
        case .teal: return "在线稳定"
        case .azure: return "灵性读数"
        case .amber: return "预警留意"
        case .crimson: return "危险失效"
        case .neutral: return "次要元数据"
        }
    }
}

// MARK: - 状态徽章 (Badge)

public enum MysticBadgeVariant: Sendable {
    /// 紧凑胶囊：用于标题行内的品阶、消耗、标签
    case capsule
    /// 面板徽章：用于状态块、据点危险等级
    case panel
    /// 纯文本徽章：用于正文内联标注
    case plain
}

/// 通用状态徽章：统一「图标 + 文本 + 语义色 + 边距」的呈现方式
public struct MysticBadge: View {
    public let text: String
    public let tone: MysticTone
    public let variant: MysticBadgeVariant
    public let systemIcon: String?
    public let isEmphasized: Bool

    public init(
        _ text: String,
        tone: MysticTone = .neutral,
        variant: MysticBadgeVariant = .capsule,
        systemIcon: String? = nil,
        isEmphasized: Bool = false
    ) {
        self.text = text
        self.tone = tone
        self.variant = variant
        self.systemIcon = systemIcon
        self.isEmphasized = isEmphasized
    }

    public var body: some View {
        HStack(spacing: DesignTokens.Spacing.xxs) {
            if let systemIcon {
                Image(systemName: systemIcon)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(tone.readableForeground)
            }
            Text(text)
                .font(Font.Mystic.caption)
                .fontWeight(isEmphasized ? .bold : .medium)
                .foregroundStyle(tone.readableForeground)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, horizontalPadding)
        .padding(.vertical, verticalPadding)
        .background(background)
        .clipShape(shape)
        .overlay(border)
        .accessibilityLabel("\(tone.semanticLabel)：\(text)")
    }

    private var horizontalPadding: CGFloat {
        switch variant {
        case .capsule: return DesignTokens.LayoutInsets.badgePaddingHorizontal + 2
        case .panel: return DesignTokens.LayoutInsets.badgePaddingHorizontal
        case .plain: return 0
        }
    }

    private var verticalPadding: CGFloat {
        switch variant {
        case .capsule: return DesignTokens.LayoutInsets.badgePaddingVertical
        case .panel: return DesignTokens.LayoutInsets.badgePaddingVertical + 1
        case .plain: return 0
        }
    }

    @ViewBuilder
    private var background: some View {
        switch variant {
        case .capsule:
            Capsule().fill(tone.accent.opacity(0.15))
        case .panel:
            RoundedRectangle(cornerRadius: DesignTokens.Radii.xs).fill(Color.Mystic.obsidianCard)
        case .plain:
            Color.clear
        }
    }

    private var shape: AnyShape {
        switch variant {
        case .capsule: return AnyShape(Capsule())
        case .panel, .plain: return AnyShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.xs))
        }
    }

    @ViewBuilder
    private var border: some View {
        if variant == .panel {
            RoundedRectangle(cornerRadius: DesignTokens.Radii.xs)
                .stroke(tone.accent.opacity(0.45), lineWidth: DesignTokens.Borders.hairline)
        }
    }
}

// MARK: - 呼吸状态点 (Status Dot)

/// 通用状态点：统一在线/预警/危险指示与呼吸微光
public struct MysticStatusDot: View {
    public let tone: MysticTone
    public let diameter: CGFloat
    public let isPulsing: Bool
    public let label: String?

    @State private var pulsePhase: Bool = false

    public init(
        tone: MysticTone,
        diameter: CGFloat = 8,
        isPulsing: Bool = false,
        label: String? = nil
    ) {
        self.tone = tone
        self.diameter = diameter
        self.isPulsing = isPulsing
        self.label = label
    }

    public var body: some View {
        HStack(spacing: DesignTokens.Spacing.xs) {
            Circle()
                .fill(tone.accent)
                .frame(width: diameter, height: diameter)
                .overlay(Circle().stroke(Color.Mystic.textPrimary.opacity(0.28), lineWidth: 1))
                .shadow(color: tone.accent.opacity(pulsePhase ? 0.35 : 0.8), radius: pulsePhase ? 6 : 3)
                .scaleEffect(pulsePhase ? 1.12 : 1.0)
                .onAppear {
                    guard isPulsing else { return }
                    withAnimation(.easeInOut(duration: DesignTokens.Motion.listeningPulseDuration / 2).repeatForever(autoreverses: true)) {
                        pulsePhase = true
                    }
                }

            if let label {
                Text(label)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(tone.readableForeground)
            }
        }
        .accessibilityLabel(label ?? tone.semanticLabel)
    }
}

// MARK: - 计量条 (Metric Bar)

/// 通用计量条：统一灵性/理智/雾霾等读数的轨道、圆角、临界阈值提示
public struct MysticMetricBar: View {
    /// 归一化取值 0...1
    public let value: Double
    public let tone: MysticTone
    public let height: CGFloat
    /// 临界阈值（低于该值转为猩红色警示），nil 表示不启用
    public let criticalThreshold: Double?
    /// 严重度渐变色阶（由低到高）；提供时优先于 `tone`，用于雾霾等连续恶化读数
    public let gradientTones: [MysticTone]

    public init(
        value: Double,
        tone: MysticTone = .azure,
        height: CGFloat = 5,
        criticalThreshold: Double? = nil,
        gradientTones: [MysticTone] = []
    ) {
        self.value = value
        self.tone = tone
        self.height = height
        self.criticalThreshold = criticalThreshold
        self.gradientTones = gradientTones
    }

    private var isCritical: Bool {
        guard let criticalThreshold else { return false }
        return clampedValue < criticalThreshold
    }

    private var clampedValue: Double {
        min(max(value, 0), 1)
    }

    private var resolvedTone: MysticTone {
        isCritical ? .crimson : tone
    }

    public var body: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                RoundedRectangle(cornerRadius: height / 2)
                    .fill(Color.black.opacity(0.4))

                RoundedRectangle(cornerRadius: height / 2)
                    .fill(fillStyle)
                    .frame(width: geo.size.width * clampedValue)
                    .shadow(color: resolvedTone.accent.opacity(0.5), radius: isCritical ? 5 : 2)
            }
        }
        .frame(height: height)
        .animation(DesignTokens.Interaction.hoverAnimation, value: clampedValue)
        .accessibilityValue("\(Int(clampedValue * 100))%")
    }

    private var fillStyle: AnyShapeStyle {
        guard gradientTones.count >= 2 else {
            return AnyShapeStyle(resolvedTone.accent)
        }
        return AnyShapeStyle(
            LinearGradient(
                colors: gradientTones.map(\.accent),
                startPoint: .leading,
                endPoint: .trailing
            )
        )
    }
}

// MARK: - 分区标题 (Section Header)

/// 通用分区标题：统一「暗金指示柱 + 标题 + 计数 + 尾随操作」的骨架
public struct MysticSectionHeader<Trailing: View>: View {
    public let title: String
    public let caption: String?
    public let count: Int?
    public let tone: MysticTone
    public let isProminent: Bool
    private let trailing: Trailing

    public init(
        title: String,
        caption: String? = nil,
        count: Int? = nil,
        tone: MysticTone = .gold,
        isProminent: Bool = false,
        @ViewBuilder trailing: () -> Trailing
    ) {
        self.title = title
        self.caption = caption
        self.count = count
        self.tone = tone
        self.isProminent = isProminent
        self.trailing = trailing()
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
            HStack(spacing: DesignTokens.Spacing.xs) {
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(tone.accent)
                    .frame(width: 3, height: 14)

                Text(title)
                    .font(isProminent ? Font.Mystic.titleMedium : Font.Mystic.titleSmall)
                    .fontWeight(.semibold)
                    .foregroundStyle(tone.readableForeground)
                    .fixedSize(horizontal: false, vertical: true)

                if let count {
                    Text("\(count)")
                        .font(Font.Mystic.monoBadge)
                        .foregroundStyle(Color.Mystic.textTertiary)
                }

                Spacer(minLength: DesignTokens.Spacing.sm)

                trailing
            }

            if let caption {
                Text(caption)
                    .mysticCaptionStyle(color: Color.Mystic.textTertiary)
                    .padding(.leading, DesignTokens.Spacing.md)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .combine)
    }
}

public extension MysticSectionHeader where Trailing == EmptyView {
    init(
        title: String,
        caption: String? = nil,
        count: Int? = nil,
        tone: MysticTone = .gold,
        isProminent: Bool = false
    ) {
        self.init(title: title, caption: caption, count: count, tone: tone, isProminent: isProminent) {
            EmptyView()
        }
    }
}

// MARK: - 键值行 (Key/Value Row)

/// 通用键值行：统一「标签 + 数值」的对齐、字距与等宽数字呈现
public struct MysticKeyValueRow: View {
    public let key: String
    public let value: String
    public let tone: MysticTone
    public let isMonospaced: Bool
    public let systemIcon: String?

    public init(
        key: String,
        value: String,
        tone: MysticTone = .neutral,
        isMonospaced: Bool = false,
        systemIcon: String? = nil
    ) {
        self.key = key
        self.value = value
        self.tone = tone
        self.isMonospaced = isMonospaced
        self.systemIcon = systemIcon
    }

    public var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: DesignTokens.Spacing.xs) {
                keyLabel
                Spacer(minLength: DesignTokens.Spacing.xs)
                valueLabel
            }

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                keyLabel
                valueLabel
            }
        }
        .accessibilityElement(children: .combine)
    }

    private var keyLabel: some View {
        HStack(spacing: DesignTokens.Spacing.xs) {
            if let systemIcon {
                Image(systemName: systemIcon)
                    .font(.system(size: 11))
                    .foregroundStyle(tone.readableForeground)
                    .frame(width: 14)
            }

            Text(key)
                .mysticCaptionStyle(color: Color.Mystic.textTertiary)
        }
    }

    private var valueLabel: some View {
        Text(value)
            .font(isMonospaced ? Font.Mystic.monoBadge : Font.Mystic.caption)
            .foregroundStyle(tone == .neutral ? Color.Mystic.textSecondary : tone.readableForeground)
            .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: - 暗金分割线 (Divider)

/// 通用分割线：统一发丝级暗金分隔与可选标签
public struct MysticDivider: View {
    public let tone: MysticTone
    public let label: String?

    public init(tone: MysticTone = .gold, label: String? = nil) {
        self.tone = tone
        self.label = label
    }

    public var body: some View {
        HStack(spacing: DesignTokens.Spacing.sm) {
            Rectangle()
                .fill(tone.accent.opacity(0.30))
                .frame(height: DesignTokens.Borders.hairline)
                .frame(maxWidth: .infinity)

            if let label {
                Text(label)
                    .font(Font.Mystic.caption)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.Mystic.textTertiary)
                    .fixedSize()

                Rectangle()
                    .fill(tone.accent.opacity(0.30))
                    .frame(height: DesignTokens.Borders.hairline)
                    .frame(maxWidth: .infinity)
            }
        }
        .accessibilityHidden(true)
    }
}

// MARK: - 空态占位 (Empty State)

/// 通用空态：统一「符号 + 标题 + 说明 + 可选操作」的占位骨架
public struct MysticEmptyState: View {
    public let systemIcon: String
    public let title: String
    public let message: String
    public let tone: MysticTone
    public let actionTitle: String?
    public var onAction: (@MainActor () -> Void)?

    public init(
        systemIcon: String,
        title: String,
        message: String,
        tone: MysticTone = .neutral,
        actionTitle: String? = nil,
        onAction: (@MainActor () -> Void)? = nil
    ) {
        self.systemIcon = systemIcon
        self.title = title
        self.message = message
        self.tone = tone
        self.actionTitle = actionTitle
        self.onAction = onAction
    }

    public var body: some View {
        VStack(spacing: DesignTokens.Spacing.sm) {
            Image(systemName: systemIcon)
                .font(.system(size: 22))
                .foregroundStyle(tone.readableForeground)

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
                Button(action: onAction) {
                    Text(actionTitle)
                        .font(Font.Mystic.caption)
                        .foregroundStyle(tone.readableForeground)
                        .padding(.horizontal, DesignTokens.Spacing.md)
                        .padding(.vertical, DesignTokens.Spacing.xs)
                        .background(
                            RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                                .fill(tone.accent.opacity(0.12))
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                                .stroke(tone.accent.opacity(0.45), lineWidth: DesignTokens.Borders.hairline)
                        )
                }
                .mysticPressable()
                .padding(.top, DesignTokens.Spacing.xxs)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(DesignTokens.LayoutInsets.cardPadding)
    }
}

// MARK: - 图标命令按钮 (Icon Button)

/// 通用图标命令按钮：统一图标、可选标题、悬停微光与按压反馈
public struct MysticIconButton: View {
    public let systemIcon: String
    public let title: String?
    public let tone: MysticTone
    public let helpText: String?
    public var action: @MainActor () -> Void

    @State private var isHovered: Bool = false

    public init(
        systemIcon: String,
        title: String? = nil,
        tone: MysticTone = .gold,
        helpText: String? = nil,
        action: @escaping @MainActor () -> Void
    ) {
        self.systemIcon = systemIcon
        self.title = title
        self.tone = tone
        self.helpText = helpText
        self.action = action
    }

    public var body: some View {
        Button(action: action) {
            HStack(spacing: DesignTokens.Spacing.xs) {
                Image(systemName: systemIcon)
                    .font(.system(size: 11, weight: .semibold))
                if let title {
                    Text(title)
                        .font(Font.Mystic.caption)
                }
            }
            .foregroundStyle(isHovered ? tone.readableForeground : Color.Mystic.textSecondary)
            .padding(.horizontal, DesignTokens.Spacing.sm)
            .padding(.vertical, DesignTokens.LayoutInsets.badgePaddingVertical + 2)
            .background(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.xs)
                    .fill(tone.accent.opacity(isHovered ? DesignTokens.Interaction.hoverBackgroundOpacity : 0.06))
            )
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.xs)
                    .stroke(
                        tone.accent.opacity(isHovered ? DesignTokens.Interaction.hoverBorderOpacity : 0.28),
                        lineWidth: DesignTokens.Borders.hairline
                    )
            )
        }
        .mysticPressable(scale: 0.97)
        .onHover { hovering in
            withAnimation(DesignTokens.Interaction.hoverAnimation) {
                isHovered = hovering
            }
        }
        .help(helpText ?? title ?? systemIcon)
    }
}
