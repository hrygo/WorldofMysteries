import SwiftUI

/// 人物档案状态卷宗卡片（对应 02 人物档案 Character Codex）。
/// 严格遵循 Invariant #2（角色先于剧情，稳定身份特质）与 Invariant #6（零知识越界）。
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

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var isHovered = false

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
            identityHeader
            traitBadges
            WOMDividerOrnament(opacity: 0.45)
            stateMetrics
            adviceAction
        }
        .padding(DesignTokens.Spacing.lg)
        .womCardChrome(
            tone: .card,
            texture: .velvet,
            isHovered: isHovered,
            cornerRadius: DesignTokens.Radii.lg
        )
        .onHover { hovering in
            withAnimation(reduceMotion ? nil : DesignTokens.Interaction.hoverAnimation) {
                isHovered = hovering
            }
        }
    }

    private var identityHeader: some View {
        HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
            portrait

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: DesignTokens.Spacing.sm) {
                        identityTitle
                        MysticBadge(pathwayTitle, tone: .gold, variant: .panel, isEmphasized: true)
                    }

                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                        identityTitle
                        MysticBadge(pathwayTitle, tone: .gold, variant: .panel, isEmphasized: true)
                    }
                }

                Text(occupation)
                    .font(Font.Mystic.bodyMedium)
                    .foregroundStyle(Color.Mystic.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)

                HStack(alignment: .firstTextBaseline, spacing: DesignTokens.Spacing.xs) {
                    Image(systemName: "mappin.and.ellipse")
                        .font(.system(size: 11, weight: .medium))
                    Text(location)
                        .font(Font.Mystic.caption)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .foregroundStyle(Color.Mystic.textTertiary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var identityTitle: some View {
        HStack(spacing: DesignTokens.Spacing.sm) {
            WOMIcon(navigation: .character, size: .standard)
                .foregroundStyle(Color.Mystic.brassGoldPrimary)

            Text(characterName)
                .font(Font.Mystic.titleMedium)
                .foregroundStyle(Color.Mystic.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var portrait: some View {
        ZStack {
            Circle()
                .fill(Color.Mystic.obsidianElevated)
                .frame(width: 52, height: 52)

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

            Circle()
                .stroke(
                    LinearGradient(
                        colors: [
                            Color.Mystic.brassGoldPrimary,
                            Color.Mystic.brassGoldHover,
                            Color.Mystic.brassGoldBorder
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    lineWidth: DesignTokens.Borders.standard
                )
                .frame(width: 52, height: 52)
                .shadow(color: Color.Mystic.brassGoldPrimary.opacity(0.35), radius: 4)

            Circle()
                .fill(isOnline ? Color.Mystic.statusOnline : Color.Mystic.textTertiary)
                .frame(width: 10, height: 10)
                .overlay(Circle().stroke(Color.black, lineWidth: 2))
                .offset(x: 18, y: 18)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(characterName)，\(isOnline ? "在线" : "离线")")
    }

    private var traitBadges: some View {
        LazyVGrid(
            columns: [GridItem(.adaptive(minimum: 96), spacing: DesignTokens.Spacing.xs, alignment: .leading)],
            alignment: .leading,
            spacing: DesignTokens.Spacing.xs
        ) {
            ForEach(traits, id: \.self) { trait in
                MysticBadge(trait, tone: .neutral)
            }
        }
    }

    private var stateMetrics: some View {
        HStack(alignment: .top, spacing: DesignTokens.Spacing.lg) {
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: DesignTokens.Spacing.xs) {
                    WOMIcon(.spirituality, size: .compact)
                        .foregroundStyle(Color.Mystic.spiritualBlue)
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
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("灵性储量")
            .accessibilityValue("\(Int(spirituality * 100))%")

            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text("理智稳定度")
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.textTertiary)
                    Spacer()
                    Text("\(Int(sanityScore * 100))%")
                        .font(Font.Mystic.monoBadge)
                        .foregroundStyle(
                            sanityScore < 0.3
                                ? Color.Mystic.textPrimary
                                : Color.Mystic.statusOnline
                        )
                }

                MysticMetricBar(value: sanityScore, tone: .teal, criticalThreshold: 0.3)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("理智稳定度")
            .accessibilityValue("\(Int(sanityScore * 100))%")
        }
    }

    private var adviceAction: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: DesignTokens.Spacing.md) {
                adviceDisclaimer
                Spacer(minLength: DesignTokens.Spacing.sm)
                adviceButton
            }

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                adviceDisclaimer
                adviceButton
            }
        }
    }

    private var adviceDisclaimer: some View {
        Text("“非命令 · 意图建议”")
            .font(Font.Mystic.caption)
            .foregroundStyle(Color.Mystic.textTertiary)
    }

    private var adviceButton: some View {
        Button {
            onVoiceAdviceTapped?()
        } label: {
            HStack(spacing: DesignTokens.Spacing.xs) {
                WOMIcon(system: .voiceAdvice, size: .standard)
                Text("向角色发起 Advice")
                    .font(Font.Mystic.titleSmall)
            }
        }
        .buttonStyle(WOMButtonStyle(.secondary))
        .accessibilityLabel("向 \(characterName) 发起 Advice")
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
