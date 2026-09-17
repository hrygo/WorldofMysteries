import SwiftUI

/// 世界、人物、系统导航与正典地域：展示持续世界信息架构的画廊分组。
struct ComponentGalleryWorldGroup: View {
    var body: some View {
        GrayFogAndRitualGallerySection()
        CodexAndDatabaseGallerySection()
        SidebarGallerySection()
        CanonicalGeographyGallerySection()
    }
}

private struct GrayFogAndRitualGallerySection: View {
    var body: some View {
        ComponentGallerySection(title: "05 · 灰雾深红星辰与仪式魔法 (Above Gray Fog & Ritual)") {
            VStack(spacing: DesignTokens.Spacing.lg) {
                HStack(spacing: DesignTokens.Spacing.md) {
                    CrimsonStarBeaconView(
                        starName: "深红星辰 · 正义小姐",
                        prayerPreview: "请求愚者先生指引贝克兰德非凡聚会情报...",
                        unheardEchoesCount: 2
                    )
                    CrimsonStarBeaconView(
                        starName: "深红星辰 · 倒吊人",
                        prayerPreview: "苏尼亚海发现了幽灵船行踪...",
                        unheardEchoesCount: 0
                    )
                }

                BronzeAltarPrayerCard(
                    deityTitle: "不属于这个时代的愚者",
                    domainName: "灰雾之上的神秘主宰",
                    blessingTitle: "执掌好运的黄黑之王"
                )
            }
        }
    }
}

private struct CodexAndDatabaseGallerySection: View {
    var body: some View {
        ComponentGallerySection(title: "06 · 人物档案与四库内核 (Codex & Database)") {
            HStack(alignment: .top, spacing: DesignTokens.Spacing.lg) {
                CharacterCodexCard(
                    characterName: "克莱恩·莫雷蒂",
                    pathwayTitle: "占卜家途径 · 序列 9",
                    occupation: "值夜者文职人员",
                    location: "佐特兰街36号"
                )

                VStack(spacing: DesignTokens.Spacing.sm) {
                    DatabaseStatusHUDCard(role: .canon, isHealthy: true, sizeText: "38.2 MB")
                    DatabaseStatusHUDCard(role: .world, isHealthy: true, sizeText: "14.6 MB")
                    DatabaseStatusHUDCard(role: .retrieval, isHealthy: true, sizeText: "52.1 MB")
                    DatabaseStatusHUDCard(role: .runtime, isHealthy: true, sizeText: "4.8 MB")
                }
                .frame(width: 220)
            }
        }
    }
}

private struct SidebarGallerySection: View {
    var body: some View {
        ComponentGallerySection(title: "07 · 侧边栏菜单系统 (Sidebar & Navigation Menu)") {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
                Text("支持展开（224pt，含 3 大语义分组、Badge 徽标与灵性状态微卡片）与紧凑折叠（68pt）双形态：")
                    .font(Font.Mystic.bodyMedium)
                    .foregroundStyle(Color.Mystic.textSecondary)

                HStack(alignment: .top, spacing: DesignTokens.Spacing.xl) {
                    SidebarGallerySample(title: "展开形态 (Expanded · 224pt)", isCollapsed: false)
                    SidebarGallerySample(title: "紧凑折叠 (Collapsed · 68pt)", isCollapsed: true)
                }
            }
        }
    }
}

private struct SidebarGallerySample: View {
    private static let badgeCounts: [NavigationItem: Int] = [.fate: 2, .worldline: 1, .cards: 4]

    let title: String
    let isCollapsed: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            Text(title)
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.brassGoldMuted)

            AppSidebarView(
                selection: .constant(.fate),
                isCollapsed: .constant(isCollapsed),
                badgeCounts: Self.badgeCounts
            )
            .frame(height: 560)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
                    .stroke(Color.Mystic.brassGoldBorder.opacity(0.4), lineWidth: 1)
            )
        }
    }
}

private struct CanonicalGeographyGallerySection: View {
    var body: some View {
        ComponentGallerySection(title: "08 · 原著正典地域与黄水晶占卜 (Citrine & Canonical Geography)") {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
                Text("基于《占卜家·克莱恩》正典原画与原著地理风貌打造的核心神秘学实体与据点卡片：")
                    .font(Font.Mystic.bodyMedium)
                    .foregroundStyle(Color.Mystic.textSecondary)

                CitrinePendulumScryingCard()
                    .frame(maxWidth: 580)

                HStack(alignment: .top, spacing: DesignTokens.Spacing.lg) {
                    TingenCityDossierCard()
                        .frame(maxWidth: .infinity)
                    BacklundMetropolisCard()
                        .frame(maxWidth: .infinity)
                }
            }
        }
    }
}
