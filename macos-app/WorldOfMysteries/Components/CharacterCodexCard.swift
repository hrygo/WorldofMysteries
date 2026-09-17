import SwiftUI

/// 人物档案状态卷宗卡片（对应 02 人物档案 Character Codex）
/// 严格遵循 Invariant #2 (角色先于剧情，稳定身份特质) 与 Invariant #6 (零知识越界)
public struct CharacterCodexCard: View {
    public let characterName: String
    public let pathwayTitle: String
    public let occupation: String
    public let location: String
    public let spirituality: Double
    public let sanityScore: Double
    public let traits: [String]
    public let isOnline: Bool
    public let avatarImageName: String?
    public var onVoiceAdviceTapped: (@MainActor () -> Void)?
    
    @State private var isHovered: Bool = false
    
    public init(
        characterName: String,
        pathwayTitle: String,
        occupation: String,
        location: String,
        spirituality: Double = 0.85,
        sanityScore: Double = 0.92,
        traits: [String] = ["谨慎周密", "守护家人", "值夜者誓言"],
        isOnline: Bool = true,
        avatarImageName: String? = "PortraitKlein",
        onVoiceAdviceTapped: (@MainActor () -> Void)? = nil
    ) {
        self.characterName = characterName
        self.pathwayTitle = pathwayTitle
        self.occupation = occupation
        self.location = location
        self.spirituality = spirituality
        self.sanityScore = sanityScore
        self.traits = traits
        self.isOnline = isOnline
        self.avatarImageName = avatarImageName
        self.onVoiceAdviceTapped = onVoiceAdviceTapped
    }
    
    public var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
            // 顶部角色姓名、途径与状态行
            HStack(alignment: .top) {
                // 角色肖像与怀表立体徽章
                ZStack {
                    Circle()
                        .fill(Color.Mystic.obsidianElevated)
                        .frame(width: 52, height: 52)
                    
                    // 优先加载真实古典油画肖像，优雅降级为矢量符号
                    if let imageName = avatarImageName, NSImage(named: imageName) != nil {
                        Image(imageName)
                            .resizable()
                            .scaledToFill()
                            .frame(width: 52, height: 52)
                            .clipShape(Circle())
                    } else {
                        Image(systemName: "person.crop.circle.fill")
                            .font(.system(size: 34))
                            .foregroundStyle(Color.Mystic.brassGoldPrimary)
                    }
                    
                    // 维多利亚黄铜相框边缘描边与微光
                    Circle()
                        .stroke(
                            LinearGradient(
                                colors: [Color.Mystic.brassGoldPrimary, Color.Mystic.brassGoldHover, Color.Mystic.brassGoldBorder],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            ),
                            lineWidth: DesignTokens.Borders.standard
                        )
                        .frame(width: 52, height: 52)
                        .shadow(color: Color.Mystic.brassGoldPrimary.opacity(0.35), radius: 4)
                    
                    // 在线状态小绿点
                    Circle()
                        .fill(isOnline ? Color.Mystic.statusOnline : Color.Mystic.textTertiary)
                        .frame(width: 10, height: 10)
                        .overlay(Circle().stroke(Color.black, lineWidth: 2))
                        .offset(x: 18, y: 18)
                }
                
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: DesignTokens.Spacing.sm) {
                        Text(characterName)
                            .font(Font.Mystic.titleMedium)
                            .foregroundStyle(Color.Mystic.textPrimary)
                        
                        MysticBadge(pathwayTitle, tone: .gold, variant: .panel, isEmphasized: true)
                    }
                    
                    Text(occupation)
                        .font(Font.Mystic.bodyMedium)
                        .foregroundStyle(Color.Mystic.textSecondary)
                    
                    HStack(spacing: 4) {
                        Image(systemName: "mappin.and.ellipse")
                            .font(.system(size: 10))
                        Text(location)
                            .font(Font.Mystic.caption)
                    }
                    .foregroundStyle(Color.Mystic.textTertiary)
                }
                
                Spacer()
            }
            
            // 特质标签排布
            HStack(spacing: DesignTokens.Spacing.xs) {
                ForEach(traits, id: \.self) { trait in
                    MysticBadge(trait, tone: .neutral)
                }
            }
            
            MysticDivider()
            
            // 精神与灵性状态读数条
            HStack(spacing: DesignTokens.Spacing.lg) {
                // 灵性刻度
                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Text("灵性储量")
                            .font(Font.Mystic.caption)
                            .foregroundStyle(Color.Mystic.textTertiary)
                        Spacer()
                        Text("\(Int(spirituality * 100))%")
                            .font(Font.Mystic.monoBadge)
                            .foregroundStyle(Color.Mystic.spiritualBlue)
                    }
                    
                    MysticMetricBar(value: spirituality, tone: .azure)
                }
                
                // 理智/失控风险
                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Text("理智稳定度")
                            .font(Font.Mystic.caption)
                            .foregroundStyle(Color.Mystic.textTertiary)
                        Spacer()
                        Text("\(Int(sanityScore * 100))%")
                            .font(Font.Mystic.monoBadge)
                            .foregroundStyle(sanityScore < 0.3 ? Color.Mystic.statusDanger : Color.Mystic.statusOnline)
                    }
                    
                    MysticMetricBar(value: sanityScore, tone: .teal, criticalThreshold: 0.3)
                }
            }
            
            // 底部语音干预快捷入口（践行 Advice ≠ Command）
            HStack {
                Text("“非命令 · 意图建议”")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textTertiary)
                
                Spacer()
                
                Button {
                    onVoiceAdviceTapped?()
                } label: {
                    HStack(spacing: DesignTokens.Spacing.xs) {
                        Image(systemName: "waveform.badge.mic")
                        Text("向角色发起 Advice")
                    }
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)
                    .padding(.horizontal, DesignTokens.Spacing.md)
                    .padding(.vertical, DesignTokens.Spacing.xs)
                    .background(Color.Mystic.brassGoldBorder.opacity(0.3))
                    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
                    .overlay(
                        RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                            .stroke(Color.Mystic.brassGoldPrimary.opacity(0.6), lineWidth: DesignTokens.Borders.standard)
                    )
                }
                .mysticPressable()
            }
        }
        .padding(DesignTokens.Spacing.lg)
        .background(
            RoundedRectangle(cornerRadius: DesignTokens.Radii.lg)
                .fill(isHovered ? Color.Mystic.obsidianElevated : Color.Mystic.obsidianCard)
        )
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.lg))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radii.lg)
                .stroke(
                    isHovered ? Color.Mystic.brassGoldPrimary : Color.Mystic.brassGoldBorder,
                    lineWidth: DesignTokens.Borders.standard
                )
        )
        .shadow(color: Color.black.opacity(0.3), radius: 8, y: 3)
        .onHover { hovering in
            withAnimation(DesignTokens.Interaction.hoverAnimation) {
                isHovered = hovering
            }
        }
    }
}

#Preview("Character Codex Cards") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()
        
        VStack(spacing: DesignTokens.Spacing.lg) {
            CharacterCodexCard(
                characterName: "克莱恩·莫雷蒂",
                pathwayTitle: "占卜家途径 · 序列 9",
                occupation: "廷根市值夜者文职人员 / 莫雷蒂家次子",
                location: "佐特兰街36号 · 黑荆棘安保公司",
                spirituality: 0.88,
                sanityScore: 0.95,
                traits: ["极度谨慎", "同理心", "金镑执念", "灰雾庇护者"]
            )
            
            CharacterCodexCard(
                characterName: "邓恩·史密斯",
                pathwayTitle: "不眠者途径 · 序列 7：梦魇",
                occupation: "廷根市值夜者小队队长",
                location: "圣赛琳娜教堂地底 · 查尼斯门前",
                spirituality: 0.65,
                sanityScore: 0.72,
                traits: ["健忘但可靠", "坚守誓言", "守护同伴", "黑咖啡爱好者"]
            )
        }
        .padding(DesignTokens.Spacing.xl)
        .frame(width: 580)
    }
}
