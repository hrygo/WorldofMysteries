import SwiftUI

/// 仪式魔法与三段式尊名祈祷卡片（对应 11 灰雾之上与 12 仪式魔法）。
public struct BronzeAltarPrayerCard: View {
    public let deityTitle: String
    public let domainName: String
    public let blessingTitle: String
    public let pathwayColor: Color
    public let ritualIntent: String
    public let spiritualityCost: Double
    public let isPraying: Bool
    public var onChantPrayer: (@MainActor () -> Void)?

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var candleFlicker = false

    public init(
        deityTitle: String = "不属于这个时代的愚者",
        domainName: String = "灰雾之上的神秘主宰",
        blessingTitle: String = "执掌好运的黄黑之王",
        pathwayColor: Color = Color.Mystic.Pathways.fool,
        ritualIntent: String = "祈求灰雾之力的庇佑与隐秘线索的占卜启示",
        spiritualityCost: Double = 0.20,
        isPraying: Bool = false,
        onChantPrayer: (@MainActor () -> Void)? = nil
    ) {
        self.deityTitle = deityTitle
        self.domainName = domainName
        self.blessingTitle = blessingTitle
        self.pathwayColor = pathwayColor
        self.ritualIntent = ritualIntent
        self.spiritualityCost = spiritualityCost
        self.isPraying = isPraying
        self.onChantPrayer = onChantPrayer
    }

    public var body: some View {
        VStack(spacing: DesignTokens.Spacing.md) {
            ritualHeader
            honorifics
            intentPanel
            chantAction
        }
        .padding(DesignTokens.Spacing.lg)
        .background(
            WOMPanelBackground(
                tone: .ritual,
                cornerRadius: DesignTokens.Radii.lg,
                texture: .foolVeil,
                textureOpacity: 0.045
            )
        )
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radii.lg, style: .continuous)
                .stroke(
                    LinearGradient(
                        colors: [
                            Color.Mystic.brassGoldBorder,
                            pathwayColor.opacity(0.52),
                            Color.Mystic.brassGoldBorder
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    lineWidth: DesignTokens.Borders.standard
                )
        )
        .onAppear {
            candleFlicker = !reduceMotion
        }
        .onChange(of: reduceMotion) { _, newValue in
            candleFlicker = !newValue
        }
    }

    private var ritualHeader: some View {
        HStack {
            HStack(spacing: DesignTokens.Spacing.sm) {
                WOMIcon(.ritual, size: .standard)
                    .foregroundStyle(Color.Mystic.spiritualBlue)

                HStack(spacing: DesignTokens.Spacing.xs) {
                    ForEach(0..<3) { index in
                        Circle()
                            .fill(Color.Mystic.spiritualBlue)
                            .frame(width: 6, height: 6)
                            .shadow(
                                color: Color.Mystic.spiritualBlue,
                                radius: reduceMotion ? 2 : (candleFlicker ? 6 : 2)
                            )
                            .scaleEffect(reduceMotion ? 1 : (candleFlicker ? 1.2 : 0.9))
                            .animation(
                                reduceMotion
                                    ? nil
                                    : .easeInOut(duration: 0.8 + Double(index) * 0.2)
                                        .repeatForever(autoreverses: true),
                                value: candleFlicker
                            )
                            .accessibilityHidden(true)
                    }
                }

                Text("灵性之墙 · 幽蓝圣焰")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.spiritualBlue)
            }

            Spacer()

            HStack(spacing: DesignTokens.Spacing.xs) {
                WOMIcon(.spirituality, size: .compact)
                Text("灵性消耗: \(Int(spiritualityCost * 100))%")
            }
            .font(Font.Mystic.monoBadge)
            .foregroundStyle(Color.Mystic.brassGoldPrimary)
            .accessibilityElement(children: .combine)
        }
        .padding(.bottom, 2)
    }

    private var honorifics: some View {
        VStack(spacing: DesignTokens.Spacing.sm) {
            Text("“\(deityTitle)，")
                .font(Font.Mystic.titleMedium)
                .foregroundStyle(Color.Mystic.textPrimary)
                .tracking(DesignTokens.TypographyMetrics.titleTracking)

            Text("\(domainName)，")
                .font(Font.Mystic.titleMedium)
                .foregroundStyle(pathwayColor)
                .tracking(DesignTokens.TypographyMetrics.titleTracking)
                .shadow(color: pathwayColor.opacity(0.4), radius: 8)

            Text("\(blessingTitle)。”")
                .font(Font.Mystic.titleMedium)
                .foregroundStyle(Color.Mystic.textGoldAccent)
                .tracking(DesignTokens.TypographyMetrics.titleTracking)
        }
        .padding(.vertical, DesignTokens.Spacing.md)
    }

    private var intentPanel: some View {
        HStack(alignment: .top, spacing: DesignTokens.Spacing.sm) {
            WOMIcon(.seal, size: .compact)
                .foregroundStyle(Color.Mystic.brassGoldMuted)

            Text("祈求目的：")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textTertiary)

            Text(ritualIntent)
                .font(Font.Mystic.bodyMedium)
                .foregroundStyle(Color.Mystic.textSecondary)

            Spacer()
        }
        .padding(.horizontal, DesignTokens.Spacing.sm)
        .padding(.vertical, DesignTokens.Spacing.xs)
        .background(
            WOMPanelBackground(
                tone: .card,
                cornerRadius: DesignTokens.Radii.xs,
                texture: .sacredSlate,
                textureOpacity: 0.025
            )
        )
    }

    private var chantAction: some View {
        HStack {
            Spacer()

            Button {
                onChantPrayer?()
            } label: {
                HStack(spacing: DesignTokens.Spacing.xs) {
                    if isPraying {
                        WOMIcon(status: .active, size: .standard)
                    } else {
                        WOMIcon(.ritual, size: .standard)
                    }
                    Text(isPraying ? "仪式共鸣中..." : "以赫密斯语吟诵尊名")
                        .font(Font.Mystic.titleSmall)
                }
            }
            .buttonStyle(WOMButtonStyle(.ritual))
            .accessibilityLabel(isPraying ? "仪式共鸣中" : "以赫密斯语吟诵尊名")
        }
    }
}

#Preview("Altar Prayers") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()

        VStack(spacing: DesignTokens.Spacing.xl) {
            BronzeAltarPrayerCard(
                deityTitle: "不属于这个时代的愚者",
                domainName: "灰雾之上的神秘主宰",
                blessingTitle: "执掌好运的黄黑之王",
                pathwayColor: Color.Mystic.Pathways.fool,
                ritualIntent: "祈求灰雾之力的庇佑与安提哥努斯笔记的占卜启示"
            )

            BronzeAltarPrayerCard(
                deityTitle: "比黑夜更漫长的黑夜",
                domainName: "比星空更崇高的星空",
                blessingTitle: "绯红之主，隐秘之母，厄难与恐惧的女皇",
                pathwayColor: Color.Mystic.Pathways.darkness,
                ritualIntent: "向黑夜女神祈求赐予安魂与深眠之水"
            )
        }
        .padding(DesignTokens.Spacing.xl)
        .frame(width: 580)
    }
}
