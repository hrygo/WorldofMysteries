import SwiftUI

// MARK: - Relationship

/// Presentation-only relationship semantics.
///
/// Domain engines may map their own relationship facts into these roles, but this visual enum is
/// not a persistence model and does not assign or mutate relationship scores.
public enum WOMRelationRole: String, CaseIterable, Sendable {
    case trusted
    case aligned
    case neutral
    case wary
    case hostile

    public var localizedTitle: String {
        switch self {
        case .trusted: "信任"
        case .aligned: "友好"
        case .neutral: "中立"
        case .wary: "戒备"
        case .hostile: "敌对"
        }
    }

    public var systemImage: String {
        switch self {
        case .trusted: "checkmark.shield.fill"
        case .aligned: "person.2.fill"
        case .neutral: "minus.circle"
        case .wary: "eye.trianglebadge.exclamationmark"
        case .hostile: "exclamationmark.shield.fill"
        }
    }

    public var tone: MysticTone {
        switch self {
        case .trusted: .teal
        case .aligned: .gold
        case .neutral: .neutral
        case .wary: .amber
        case .hostile: .crimson
        }
    }

    fileprivate var differentiateDash: [CGFloat] {
        switch self {
        case .trusted: []
        case .aligned: [6, 2]
        case .neutral: [2, 2]
        case .wary: [5, 3]
        case .hostile: [2, 2, 7, 2]
        }
    }
}

/// Compact relation chrome that never relies on color alone.
public struct WOMRelationBadge: View {
    public let title: String
    public let role: WOMRelationRole
    public let detail: String?

    @Environment(\.accessibilityDifferentiateWithoutColor) private var differentiateWithoutColor
    @Environment(\.colorSchemeContrast) private var colorSchemeContrast

    public init(
        _ title: String,
        role: WOMRelationRole,
        detail: String? = nil
    ) {
        self.title = title
        self.role = role
        self.detail = detail
    }

    public var body: some View {
        HStack(alignment: .top, spacing: DesignTokens.Spacing.sm) {
            Image(systemName: role.systemImage)
                .font(.system(size: 14, weight: .semibold))
                .foregroundStyle(role.tone.accent)
                .frame(width: 20, height: 20)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
                Text(title)
                    .font(Font.Mystic.bodyMedium)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.Mystic.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)

                Text(role.localizedTitle)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(role.tone.readableForeground)

                if let detail {
                    Text(detail)
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Spacer(minLength: DesignTokens.Spacing.xs)
        }
        .padding(.horizontal, DesignTokens.LayoutInsets.compactCardPadding)
        .padding(.vertical, DesignTokens.Spacing.sm)
        .background(
            WOMPanelBackground(
                tone: .card,
                cornerRadius: DesignTokens.Radii.sm,
                texture: .sacredSlate,
                textureOpacity: 0.014
            )
        )
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.Radii.sm, style: .continuous)
                .stroke(
                    role.tone.accent.opacity(colorSchemeContrast == .increased ? 0.92 : 0.48),
                    style: StrokeStyle(
                        lineWidth: colorSchemeContrast == .increased
                            ? DesignTokens.Borders.standard
                            : DesignTokens.Borders.hairline,
                        dash: differentiateWithoutColor ? role.differentiateDash : []
                    )
                )
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title)，关系：\(role.localizedTitle)")
    }
}

// MARK: - Achievement

public enum WOMAchievementState: String, CaseIterable, Sendable {
    case locked
    case discovered
    case completed

    public var localizedTitle: String {
        switch self {
        case .locked: "未解锁"
        case .discovered: "已发现"
        case .completed: "已完成"
        }
    }

    public var systemImage: String {
        switch self {
        case .locked: "lock.fill"
        case .discovered: "sparkles"
        case .completed: "checkmark.seal.fill"
        }
    }

    public var tone: MysticTone {
        switch self {
        case .locked: .neutral
        case .discovered: .azure
        case .completed: .gold
        }
    }

    fileprivate var differentiateDash: [CGFloat] {
        switch self {
        case .locked: [2, 2]
        case .discovered: [6, 2]
        case .completed: []
        }
    }
}

/// Discovery/achievement presentation that keeps locked content readable.
public struct WOMAchievementSeal: View {
    public let title: String
    public let detail: String?
    public let state: WOMAchievementState
    public let systemImage: String?

    @Environment(\.accessibilityDifferentiateWithoutColor) private var differentiateWithoutColor
    @Environment(\.colorSchemeContrast) private var colorSchemeContrast

    public init(
        title: String,
        detail: String? = nil,
        state: WOMAchievementState,
        systemImage: String? = nil
    ) {
        self.title = title
        self.detail = detail
        self.state = state
        self.systemImage = systemImage
    }

    public var body: some View {
        HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
            ZStack {
                Circle()
                    .fill(state.tone.accent.opacity(0.12))
                    .frame(width: 42, height: 42)

                Image(systemName: systemImage ?? state.systemImage)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(state.tone.readableForeground)
            }
            .overlay(
                Circle()
                    .stroke(
                        state.tone.accent.opacity(colorSchemeContrast == .increased ? 0.92 : 0.5),
                        lineWidth: colorSchemeContrast == .increased
                            ? DesignTokens.Borders.standard
                            : DesignTokens.Borders.hairline
                    )
            )
            .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                Text(title)
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)

                Text(state.localizedTitle)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(state.tone.readableForeground)

                if let detail {
                    Text(detail)
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Spacer(minLength: DesignTokens.Spacing.sm)
        }
        .padding(DesignTokens.LayoutInsets.compactCardPadding)
        .background(
            WOMPanelBackground(
                tone: .card,
                cornerRadius: DesignTokens.Radii.md,
                texture: state == .completed ? .gold : .sacredSlate,
                textureOpacity: state == .completed ? 0.026 : 0.014
            )
        )
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.Radii.md, style: .continuous)
                .stroke(
                    state.tone.accent.opacity(colorSchemeContrast == .increased ? 0.9 : 0.42),
                    style: StrokeStyle(
                        lineWidth: colorSchemeContrast == .increased
                            ? DesignTokens.Borders.standard
                            : DesignTokens.Borders.hairline,
                        dash: differentiateWithoutColor ? state.differentiateDash : []
                    )
                )
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title)，\(state.localizedTitle)")
    }
}

// MARK: - Cooldown / availability

/// Externally supplied availability state.
///
/// No timer is owned by this enum or by `WOMCooldownIndicator`; domain/runtime layers remain the
/// source of truth for when an action becomes available.
public enum WOMCooldownState: Equatable, Sendable {
    case ready
    case cooling(progress: Double, remainingLabel: String?)
    case locked(reason: String?)

    public var localizedTitle: String {
        switch self {
        case .ready: "可用"
        case .cooling: "冷却中"
        case .locked: "不可用"
        }
    }

    public var systemImage: String {
        switch self {
        case .ready: "checkmark.circle.fill"
        case .cooling: "clock.arrow.circlepath"
        case .locked: "lock.fill"
        }
    }

    public var tone: MysticTone {
        switch self {
        case .ready: .teal
        case .cooling: .azure
        case .locked: .neutral
        }
    }

    public var progress: Double? {
        switch self {
        case .cooling(let progress, _): min(max(progress, 0), 1)
        case .ready, .locked: nil
        }
    }

    public var supplementalText: String? {
        switch self {
        case .ready: nil
        case .cooling(_, let remainingLabel): remainingLabel
        case .locked(let reason): reason
        }
    }
}

/// Static availability/cooldown presentation. It intentionally owns no clock or repeating task.
public struct WOMCooldownIndicator: View {
    public let title: String
    public let state: WOMCooldownState

    @Environment(\.colorSchemeContrast) private var colorSchemeContrast

    public init(
        _ title: String,
        state: WOMCooldownState
    ) {
        self.title = title
        self.state = state
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            HStack(alignment: .firstTextBaseline, spacing: DesignTokens.Spacing.sm) {
                Image(systemName: state.systemImage)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(state.tone.accent)
                    .accessibilityHidden(true)

                Text(title)
                    .font(Font.Mystic.bodyMedium)
                    .fontWeight(.semibold)
                    .foregroundStyle(Color.Mystic.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)

                Spacer(minLength: DesignTokens.Spacing.sm)

                Text(state.localizedTitle)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(state.tone.readableForeground)
            }

            if let progress = state.progress {
                ProgressView(value: progress)
                    .progressViewStyle(.linear)
                    .tint(Color.Mystic.spiritualBlue)
                    .accessibilityLabel("冷却进度")
                    .accessibilityValue("\(Int(progress * 100))%")
            }

            if let supplementalText = state.supplementalText {
                Text(supplementalText)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(DesignTokens.LayoutInsets.compactCardPadding)
        .background(
            WOMPanelBackground(
                tone: .card,
                cornerRadius: DesignTokens.Radii.sm,
                texture: .sacredSlate,
                textureOpacity: 0.014
            )
        )
        .overlay {
            RoundedRectangle(cornerRadius: DesignTokens.Radii.sm, style: .continuous)
                .stroke(
                    state.tone.accent.opacity(colorSchemeContrast == .increased ? 0.9 : 0.4),
                    lineWidth: colorSchemeContrast == .increased
                        ? DesignTokens.Borders.standard
                        : DesignTokens.Borders.hairline
                )
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title)，\(state.localizedTitle)")
    }
}
