import SwiftUI

/// 贝克兰德五大城区与势力分布
public enum BacklundDistrict: String, CaseIterable, Identifiable, Sendable {
    case cherwood = "乔伍德区 (Cherwood)"
    case bridge = "贝克兰德桥区 (Bridge Area)"
    case eastEnd = "东区 (East End)"
    case empress = "皇后区与北区 (Empress & North)"

    public var id: String { rawValue }

    public var description: String {
        switch self {
        case .cherwood: return "明斯克街 15 号 · 夏洛克·莫里亚蒂侦探事务所"
        case .bridge: return "铁门街勇敢者酒吧 · 非凡聚会与地下线人"
        case .eastEnd: return "蒸汽工厂巨型烟囱 · 大雾霾核心与黑帮暗流"
        case .empress: return "伯爵府邸贵族沙龙 · 圣赛缪尔大教堂主教座"
        }
    }

    public var dangerLevel: String {
        switch self {
        case .cherwood: return "中度警戒"
        case .bridge: return "非凡混杂"
        case .eastEnd: return "高危贫民窟"
        case .empress: return "官方重兵"
        }
    }

    public var dangerColor: Color {
        tone.accent
    }

    public var tone: MysticTone {
        switch self {
        case .cherwood: return .gold
        case .bridge: return .amber
        case .eastEnd: return .crimson
        case .empress: return .teal
        }
    }
}

/// 贝克兰德 · 万都之都全景态势卡
public struct BacklundMetropolisCard: View {
    public var onDistrictSelected: (@MainActor (BacklundDistrict) -> Void)?

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var selectedDistrict: BacklundDistrict = .cherwood
    @State private var hoveredDistrict: BacklundDistrict? = nil
    @State private var smogLevel: Double = 0.78

    public init(onDistrictSelected: (@MainActor (BacklundDistrict) -> Void)? = nil) {
        self.onDistrictSelected = onDistrictSelected
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingMd) {
            cityHeader
            operationalStatus

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                Text("重点城区与暗线据点 (Boroughs & Safehouses)：")
                    .mysticCaptionStyle(color: Color.Mystic.textTertiary)

                VStack(spacing: DesignTokens.Spacing.xs) {
                    ForEach(BacklundDistrict.allCases) { district in
                        districtRow(district)
                    }
                }
            }
        }
        .padding(DesignTokens.LayoutInsets.cardPadding)
        .background(
            Color.Mystic.obsidianElevated
                .overlay(
                    LinearGradient(
                        colors: [Color.Mystic.brassGoldMuted.opacity(0.04), Color.clear],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
        )
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.lg))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radii.lg)
                .stroke(Color.Mystic.brassGoldBorder, lineWidth: DesignTokens.Borders.standard)
        )
    }

    private var cityHeader: some View {
        ZStack(alignment: .bottomLeading) {
            ZStack {
                LinearGradient(
                    colors: [
                        Color(red: 16/255, green: 28/255, blue: 44/255),
                        Color.Mystic.obsidianElevated
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )

                if NSImage(named: "TextureFoolVeil") != nil {
                    Image("TextureFoolVeil")
                        .resizable(resizingMode: .tile)
                        .blendMode(.screen)
                        .opacity(0.12)
                }

                HStack {
                    Spacer()
                    ZStack(alignment: .bottomTrailing) {
                        Circle()
                            .fill(Color.Mystic.spiritualBlue.opacity(0.2))
                            .frame(width: 140, height: 140)
                            .blur(radius: 24)

                        Image(systemName: "building.columns.circle")
                            .font(.system(size: 64, weight: .ultraLight))
                            .foregroundStyle(Color.Mystic.brassGoldPrimary.opacity(0.35))
                    }
                    .padding(.trailing, DesignTokens.Spacing.lg)
                    .accessibilityHidden(true)
                }
            }
            .frame(height: 120)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))

            VStack(alignment: .leading, spacing: DesignTokens.TypographyMetrics.compactLineSpacing) {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: DesignTokens.Spacing.sm) {
                        Text("鲁恩王国首都 · 万都之都")
                            .mysticCaptionStyle(color: Color.Mystic.brassGoldMuted)
                        Text("Hope & Fall")
                            .font(Font.Mystic.monoBadge)
                            .foregroundStyle(Color.Mystic.textSecondary)
                    }

                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
                        Text("鲁恩王国首都 · 万都之都")
                            .mysticCaptionStyle(color: Color.Mystic.brassGoldMuted)
                        Text("Hope & Fall")
                            .font(Font.Mystic.monoBadge)
                            .foregroundStyle(Color.Mystic.textSecondary)
                    }
                }

                Text("贝克兰德 · 全景态势视窗")
                    .mysticTitleStyle(font: Font.Mystic.titleMedium)
                    .fixedSize(horizontal: false, vertical: true)

                Text("塔索克河水雾 · 蒸汽烟囱轰鸣 · 500 万人口之城")
                    .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(DesignTokens.LayoutInsets.compactCardPadding)
        }
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
                .stroke(Color.Mystic.brassGoldBorder.opacity(0.6), lineWidth: DesignTokens.Borders.standard)
        )
    }

    private var operationalStatus: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: DesignTokens.LayoutInsets.stackSpacingMd) {
                smogStatus
                    .frame(maxWidth: .infinity)
                riverStatus
                    .frame(maxWidth: .infinity)
            }

            VStack(spacing: DesignTokens.Spacing.sm) {
                smogStatus
                riverStatus
            }
        }
    }

    private var smogStatus: some View {
        VStack(alignment: .leading, spacing: 3) {
            MysticKeyValueRow(
                key: "贝克兰德大雾霾",
                value: "\(Int(smogLevel * 100))%",
                tone: .amber,
                isMonospaced: true,
                systemIcon: "smoke.fill"
            )

            MysticMetricBar(
                value: smogLevel,
                tone: .amber,
                gradientTones: [.amber, .crimson]
            )
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(DesignTokens.Spacing.sm)
        .background(Color.Mystic.obsidianCard)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
    }

    private var riverStatus: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            MysticKeyValueRow(
                key: "塔索克河航运",
                value: "通畅",
                tone: .teal,
                systemIcon: "water.waves"
            )

            Text("代罚者与军情九处巡航中")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textTertiary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(DesignTokens.Spacing.sm)
        .background(Color.Mystic.obsidianCard)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
    }

    @ViewBuilder
    private func districtRow(_ district: BacklundDistrict) -> some View {
        let isSelected = selectedDistrict == district
        let isHovered = hoveredDistrict == district

        Button {
            withAnimation(reduceMotion ? nil : DesignTokens.Interaction.selectionSpring) {
                selectedDistrict = district
            }
            onDistrictSelected?(district)
        } label: {
            HStack(alignment: .top, spacing: DesignTokens.Spacing.sm) {
                VStack(alignment: .leading, spacing: DesignTokens.TypographyMetrics.compactLineSpacing) {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: DesignTokens.Spacing.sm) {
                            districtTitle(district, isSelected: isSelected, isHovered: isHovered)
                            MysticBadge(district.dangerLevel, tone: district.tone, isEmphasized: true)
                        }

                        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                            districtTitle(district, isSelected: isSelected, isHovered: isHovered)
                            MysticBadge(district.dangerLevel, tone: district.tone, isEmphasized: true)
                        }
                    }

                    Text(district.description)
                        .mysticCaptionStyle(
                            color: isSelected ? Color.Mystic.brassGoldMuted : Color.Mystic.textTertiary
                        )
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: DesignTokens.Spacing.xs)

                if isSelected {
                    Circle()
                        .fill(Color.Mystic.brassGoldPrimary)
                        .frame(width: 6, height: 6)
                        .shadow(color: Color.Mystic.brassGoldPrimary, radius: 4)
                        .accessibilityHidden(true)
                }
            }
            .mysticRowItem(
                isSelected: isSelected,
                isHovered: isHovered,
                cornerRadius: DesignTokens.Radii.sm,
                showsLeadingIndicator: true
            )
        }
        .mysticPressable()
        .onHover { hovering in
            hoveredDistrict = hovering ? district : nil
        }
        .accessibilityLabel(district.rawValue)
        .accessibilityValue("\(district.dangerLevel)，\(district.description)")
    }

    private func districtTitle(
        _ district: BacklundDistrict,
        isSelected: Bool,
        isHovered: Bool
    ) -> some View {
        Text(district.rawValue)
            .font(Font.Mystic.bodyMedium)
            .fontWeight(isSelected ? .semibold : .regular)
            .foregroundStyle(
                isSelected
                    ? Color.Mystic.textPrimary
                    : (isHovered ? Color.Mystic.textPrimary : Color.Mystic.textSecondary)
            )
            .tracking(DesignTokens.TypographyMetrics.bodyTracking)
            .fixedSize(horizontal: false, vertical: true)
    }
}

#Preview("Backlund Metropolis Card") {
    BacklundMetropolisCard()
        .frame(width: 460)
        .padding()
        .background(Color.Mystic.obsidianBase)
}
