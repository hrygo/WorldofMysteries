import SwiftUI

/// 仪式魔法与三段式尊名祈祷卡片（对应 11 灰雾之上与 12 仪式魔法）
public struct BronzeAltarPrayerCard: View {
    public let deityTitle: String
    public let domainName: String
    public let blessingTitle: String
    public let pathwayColor: Color
    public let ritualIntent: String
    public let spiritualityCost: Double
    public let isPraying: Bool
    public var onChantPrayer: (@MainActor () -> Void)?
    
    @State private var candleFlicker: Bool = false
    
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
            // 顶部三支草药蜡烛与灵性之墙标识
            HStack {
                HStack(spacing: DesignTokens.Spacing.sm) {
                    // 三支象征三元祭祀的蜡烛火焰
                    ForEach(0..<3) { index in
                        Circle()
                            .fill(Color.Mystic.spiritualBlue)
                            .frame(width: 6, height: 6)
                            .shadow(color: Color.Mystic.spiritualBlue, radius: candleFlicker ? 6 : 2)
                            .scaleEffect(candleFlicker ? 1.2 : 0.9)
                            .animation(
                                .easeInOut(duration: 0.8 + Double(index) * 0.2).repeatForever(autoreverses: true),
                                value: candleFlicker
                            )
                    }
                    Text("灵性之墙 · 幽蓝圣焰")
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.spiritualBlue)
                }
                
                Spacer()
                
                HStack(spacing: DesignTokens.Spacing.xs) {
                    Image(systemName: "flame.circle")
                    Text("灵性消耗: \(Int(spiritualityCost * 100))%")
                }
                .font(Font.Mystic.monoBadge)
                .foregroundStyle(Color.Mystic.brassGoldPrimary)
            }
            .padding(.bottom, 2)
            
            // 中央三段式神圣尊名（三元叙事排版，古典衬线 New York + 宋体）
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
            
            // 祈祷意图说明
            HStack {
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
            .background(Color.Mystic.obsidianElevated)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.xs))
            
            // 底部仪式响应按钮
            HStack {
                Spacer()
                
                Button {
                    onChantPrayer?()
                } label: {
                    HStack(spacing: DesignTokens.Spacing.xs) {
                        Image(systemName: isPraying ? "rays" : "hands.sparkles.fill")
                        Text(isPraying ? "仪式共鸣中..." : "以赫密斯语吟诵尊名")
                    }
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.obsidianBase)
                    .padding(.horizontal, DesignTokens.Spacing.lg)
                    .padding(.vertical, DesignTokens.Spacing.sm)
                    .background(
                        LinearGradient(
                            colors: [Color.Mystic.brassGoldPrimary, Color.Mystic.brassGoldHover],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
                    .shadow(color: Color.Mystic.brassGoldPrimary.opacity(0.3), radius: 6)
                }
                .mysticPressable(scale: 0.97)
            }
        }
        .padding(DesignTokens.Spacing.lg)
        .background(Color.Mystic.obsidianCard)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.lg))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radii.lg)
                .stroke(
                    LinearGradient(
                        colors: [Color.Mystic.brassGoldBorder, pathwayColor.opacity(0.5), Color.Mystic.brassGoldBorder],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    lineWidth: DesignTokens.Borders.standard
                )
        )
        .onAppear {
            candleFlicker = true
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
