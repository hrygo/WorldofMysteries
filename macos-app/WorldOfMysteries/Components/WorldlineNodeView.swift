import SwiftUI

/// 世界线分支状态枚举
public enum WorldlineBranchStatus: String, Sendable, CaseIterable {
    case canonical = "正典主轴"
    case diverged = "因果分叉"
    case active = "当前活跃"
    case pruned = "已剪枝"

    public var iconName: String {
        switch self {
        case .canonical: return "lock.shield.fill"
        case .diverged: return "arrow.triangle.branch"
        case .active: return "circle.circle.fill"
        case .pruned: return "scissors"
        }
    }

    public var accentColor: Color {
        switch self {
        case .canonical: return Color.Mystic.brassGoldPrimary
        case .diverged: return Color.Mystic.spiritualBlue
        case .active: return Color.Mystic.statusOnline
        case .pruned: return Color.Mystic.textTertiary
        }
    }
}

/// 世界线因果节点卡片（对应 08 世界线 Worldline Nexus）
/// 严格践行 Invariant #3 (Canon 约束历史)、#10 (用户世界不污染 Canon)、#15 (显式世界线分叉)
public struct WorldlineNodeView: View {
    public let title: String
    public let worldTime: String
    public let status: WorldlineBranchStatus
    public let causeSummary: String
    public let turnIndex: Int
    public var onSelect: (@MainActor () -> Void)?

    @State private var isHovered: Bool = false

    public init(
        title: String,
        worldTime: String,
        status: WorldlineBranchStatus = .diverged,
        causeSummary: String,
        turnIndex: Int = 1,
        onSelect: (@MainActor () -> Void)? = nil
    ) {
        self.title = title
        self.worldTime = worldTime
        self.status = status
        self.causeSummary = causeSummary
        self.turnIndex = turnIndex
        self.onSelect = onSelect
    }

    public var body: some View {
        Button {
            onSelect?()
        } label: {
            ZStack {
                WOMArtworkView(
                    assetName: WOMWorldArtworkAsset.fateWorldline.runtimeAssetName,
                    fallback: .asset(.world),
                    fallbackTint: status.accentColor,
                    contentMode: .fill
                )
                .opacity(0.14)
                .allowsHitTesting(false)

                WOMArtworkScrim(edge: .leading, strength: 0.9)

                HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
                    timelineIndicator

                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                        metadataHeader

                        Text(title)
                            .font(Font.Mystic.titleMedium)
                            .foregroundStyle(Color.Mystic.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)

                        Text(causeSummary)
                            .font(Font.Mystic.bodyMedium)
                            .foregroundStyle(Color.Mystic.textSecondary)
                            .lineSpacing(2)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(DesignTokens.Spacing.md)
            }
            .background(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
                    .fill(isHovered ? Color.Mystic.obsidianElevated : Color.Mystic.obsidianCard)
            )
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
                    .stroke(
                        status == .active ? status.accentColor : Color.Mystic.brassGoldBorder.opacity(isHovered ? 0.8 : 0.3),
                        lineWidth: status == .active ? DesignTokens.Borders.chamfer : DesignTokens.Borders.standard
                    )
            )
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
            .shadow(color: Color.black.opacity(0.3), radius: 6, y: 2)
        }
        .mysticPressable(scale: 0.99, pressedOpacity: 0.94)
        .disabled(onSelect == nil)
        .accessibilityLabel(title)
        .accessibilityValue(causeSummary)
        .onHover { hovering in
            withAnimation(DesignTokens.Interaction.hoverAnimation) {
                isHovered = hovering
            }
        }
    }

    private var timelineIndicator: some View {
        VStack(spacing: DesignTokens.Spacing.xs) {
            Circle()
                .fill(status.accentColor.opacity(0.2))
                .frame(width: 32, height: 32)
                .overlay(
                    Image(systemName: status.iconName)
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(status.accentColor)
                )
                .overlay(
                    Circle()
                        .stroke(status.accentColor.opacity(isHovered ? 0.9 : 0.4), lineWidth: DesignTokens.Borders.standard)
                )
                .shadow(color: status.accentColor.opacity(status == .active ? 0.4 : 0.1), radius: 6)

            Rectangle()
                .fill(Color.Mystic.brassGoldBorder.opacity(0.5))
                .frame(width: 2)
                .frame(maxHeight: .infinity)
        }
    }

    private var metadataHeader: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: DesignTokens.Spacing.sm) {
                worldTimeLabel
                Spacer(minLength: DesignTokens.Spacing.sm)
                turnLabel
                statusLabel
            }

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                worldTimeLabel
                HStack(spacing: DesignTokens.Spacing.sm) {
                    turnLabel
                    statusLabel
                }
            }
        }
    }

    private var worldTimeLabel: some View {
        Text(worldTime)
            .font(Font.Mystic.monoBadge)
            .foregroundStyle(Color.Mystic.textGoldAccent)
            .fixedSize(horizontal: false, vertical: true)
    }

    private var turnLabel: some View {
        Text("回合 #\(turnIndex)")
            .font(Font.Mystic.caption)
            .foregroundStyle(Color.Mystic.textTertiary)
    }

    private var statusLabel: some View {
        Text(status.rawValue)
            .font(Font.Mystic.caption)
            .padding(.horizontal, DesignTokens.Spacing.xs)
            .padding(.vertical, 2)
            .background(status.accentColor.opacity(0.15))
            .foregroundStyle(status.accentColor)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.xs))
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.xs)
                    .stroke(status.accentColor.opacity(0.3), lineWidth: DesignTokens.Borders.hairline)
            )
    }
}

#Preview("Worldline Nodes") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()

        VStack(spacing: DesignTokens.Spacing.md) {
            WorldlineNodeView(
                title: "正典主轴：廷根市的枪声",
                worldTime: "第五纪 1349年 6月28日 晨",
                status: .canonical,
                causeSummary: "既定历史：克莱恩·莫雷蒂在自杀现场苏醒，安提哥努斯笔记随韦尔奇身亡而不知所踪。",
                turnIndex: 0
            )

            WorldlineNodeView(
                title: "分支 A：提前上报值夜者小队",
                worldTime: "第五纪 1349年 6月28日 午",
                status: .active,
                causeSummary: "因果偏离：玩家建议向邓恩·史密斯汇报韦尔奇日记疑点，值夜者在瑞尔·比伯逃逸前封锁码头。",
                turnIndex: 3
            )

            WorldlineNodeView(
                title: "分支 B：私自追踪密修会占卜师",
                worldTime: "第五纪 1349年 6月29日 夜",
                status: .diverged,
                causeSummary: "因果偏离：克莱恩未等队友策应独入东区，灵性消耗过度触发轻微幻听，局势严重失控。",
                turnIndex: 5
            )
        }
        .padding(DesignTokens.Spacing.xl)
        .frame(width: 580)
    }
}
