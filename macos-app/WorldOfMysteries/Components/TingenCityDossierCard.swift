import SwiftUI

/// 廷根市区域关键地标。
public enum TingenLocation: String, CaseIterable, Identifiable, Sendable {
    case zotlandStreet = "佐特兰街 36 号"
    case daffodilStreet = "水仙花街"
    case welchBedroom = "韦尔奇卧房 (案发现场)"
    case hoyUniversity = "霍伊大学历史系"

    public var id: String { rawValue }

    public var note: String {
        switch self {
        case .zotlandStreet: "黑荆棘安保公司 · 地下查尼斯门"
        case .daffodilStreet: "班森与梅丽莎的家 · 水仙花寓意安宁"
        case .welchBedroom: "转轮手枪、未燃尽信件与红月"
        case .hoyUniversity: "古代赫密斯语与第四纪所罗门帝国文献"
        }
    }

    public var systemIcon: String {
        switch self {
        case .zotlandStreet: "shield.checkered"
        case .daffodilStreet: "house.fill"
        case .welchBedroom: "moon.stars.fill"
        case .hoyUniversity: "graduationcap.fill"
        }
    }
}

/// 廷根市 · 工业与大学之城调查卷宗卡。
public struct TingenCityDossierCard: View {
    public var onLocationSelected: (@MainActor (TingenLocation) -> Void)?

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var selectedLocation: TingenLocation = .zotlandStreet
    @State private var hoveredLocation: TingenLocation?

    public init(onLocationSelected: (@MainActor (TingenLocation) -> Void)? = nil) {
        self.onLocationSelected = onLocationSelected
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingMd) {
            dossierHeader
            statusSummary

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                HStack(spacing: DesignTokens.Spacing.xs) {
                    WOMIcon(.clue, size: .compact)
                        .foregroundStyle(Color.Mystic.brassGoldMuted)
                    Text("重要地标与驻点 (Key Locations)：")
                        .mysticCaptionStyle(color: Color.Mystic.textTertiary)
                }

                VStack(spacing: DesignTokens.Spacing.xs) {
                    ForEach(TingenLocation.allCases) { location in
                        locationRow(location)
                    }
                }
            }
        }
        .padding(DesignTokens.LayoutInsets.cardPadding)
        .background(
            WOMPanelBackground(
                tone: .panel,
                cornerRadius: DesignTokens.Radii.lg,
                texture: .sacredSlate,
                textureOpacity: 0.035
            )
        )
    }

    private var statusSummary: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: DesignTokens.LayoutInsets.stackSpacingMd) {
                sealStatus
                    .frame(maxWidth: .infinity)
                investigationStatus
                    .frame(maxWidth: .infinity)
            }

            VStack(spacing: DesignTokens.Spacing.sm) {
                sealStatus
                investigationStatus
            }
        }
    }

    private var sealStatus: some View {
        statusPill(
            title: "查尼斯门状态",
            value: "安宁 (圣赛缪尔骨灰封印)",
            source: .status(.locked),
            color: Color.Mystic.statusOnline
        )
    }

    private var investigationStatus: some View {
        statusPill(
            title: "当前核心调查",
            value: "追查《安提哥努斯笔记》",
            source: .system(.search),
            color: Color.Mystic.brassGoldPrimary
        )
    }

    private var dossierHeader: some View {
        ZStack(alignment: .bottomLeading) {
            ZStack {
                LinearGradient(
                    colors: [
                        Color(red: 45 / 255, green: 15 / 255, blue: 22 / 255),
                        Color.Mystic.obsidianElevated
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )

                WOMTextureLayer(.velvet, opacity: 0.18, blendMode: .multiply)

                HStack {
                    Spacer()
                    ZStack {
                        Circle()
                            .fill(Color.Mystic.crimsonGlow.opacity(0.25))
                            .frame(width: 120, height: 120)
                            .blur(radius: 20)

                        Image(systemName: "moon.fill")
                            .font(.system(size: 44, weight: .light))
                            .foregroundStyle(Color.Mystic.crimsonStar.opacity(0.8))
                            .shadow(color: Color.Mystic.crimsonStar.opacity(0.6), radius: 12)
                    }
                    .padding(.trailing, DesignTokens.Spacing.xl)
                    .accessibilityHidden(true)
                }
            }
            .frame(height: 110)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md, style: .continuous))

            VStack(alignment: .leading, spacing: DesignTokens.TypographyMetrics.compactLineSpacing) {
                HStack(spacing: 6) {
                    Text("鲁恩王国 · 阿霍瓦郡")
                        .mysticCaptionStyle(color: Color.Mystic.brassGoldMuted)

                    Circle()
                        .fill(Color.Mystic.crimsonStar)
                        .frame(width: 5, height: 5)
                        .accessibilityHidden(true)

                    Text("红月笼罩")
                        .font(Font.Mystic.monoBadge)
                        .foregroundStyle(Color.Mystic.textPrimary)
                }

                HStack(spacing: DesignTokens.Spacing.xs) {
                    WOMIcon(.codex, size: .standard)
                        .foregroundStyle(Color.Mystic.brassGoldPrimary)
                    Text("廷根市 · 调查据点卷宗")
                        .mysticTitleStyle(font: Font.Mystic.titleMedium)
                }

                Text("阿霍瓦细雨 · 煤气路灯长明 · 能见度 65%")
                    .mysticCaptionStyle(color: Color.Mystic.textSecondary)
            }
            .padding(DesignTokens.LayoutInsets.compactCardPadding)
        }
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radii.md, style: .continuous)
                .stroke(Color.Mystic.brassGoldBorder.opacity(0.6), lineWidth: DesignTokens.Borders.standard)
        )
    }

    @ViewBuilder
    private func statusPill(
        title: String,
        value: String,
        source: WOMIconSource,
        color: Color
    ) -> some View {
        HStack(spacing: DesignTokens.Spacing.xs) {
            WOMIcon(source: source, size: .compact)
                .foregroundStyle(color)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textTertiary)
                Text(value)
                    .font(Font.Mystic.caption)
                    .fontWeight(.semibold)
                    .foregroundStyle(color)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: DesignTokens.Spacing.xs)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, DesignTokens.LayoutInsets.badgePaddingHorizontal + 2)
        .padding(.vertical, 6)
        .background(
            WOMPanelBackground(
                tone: .card,
                cornerRadius: DesignTokens.Radii.sm,
                texture: .sacredSlate,
                textureOpacity: 0.018
            )
        )
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private func locationRow(_ location: TingenLocation) -> some View {
        let isSelected = selectedLocation == location
        let isHovered = hoveredLocation == location

        Button {
            withAnimation(reduceMotion ? nil : DesignTokens.Interaction.selectionSpring) {
                selectedLocation = location
            }
            onLocationSelected?(location)
        } label: {
            HStack(spacing: DesignTokens.Spacing.sm) {
                Image(systemName: location.systemIcon)
                    .font(.system(size: 12))
                    .foregroundStyle(
                        isSelected
                            ? Color.Mystic.brassGoldPrimary
                            : (isHovered ? Color.Mystic.textPrimary : Color.Mystic.textTertiary)
                    )
                    .frame(width: 18)
                    .accessibilityHidden(true)

                VStack(alignment: .leading, spacing: DesignTokens.TypographyMetrics.compactLineSpacing) {
                    Text(location.rawValue)
                        .font(Font.Mystic.bodyMedium)
                        .fontWeight(isSelected ? .semibold : .regular)
                        .foregroundStyle(
                            isSelected
                                ? Color.Mystic.textPrimary
                                : (isHovered ? Color.Mystic.textPrimary : Color.Mystic.textSecondary)
                        )
                        .tracking(DesignTokens.TypographyMetrics.bodyTracking)

                    Text(location.note)
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
        .buttonStyle(MysticPressableButtonStyle())
        .onHover { hovering in
            hoveredLocation = hovering ? location : nil
        }
        .accessibilityLabel(location.rawValue)
        .accessibilityValue(location.note)
    }
}

#Preview("Tingen City Dossier Card") {
    TingenCityDossierCard()
        .frame(width: 440)
        .padding()
        .background(Color.Mystic.obsidianBase)
}
