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
    @State private var lastRitualAction = "尚未触发"
    @State private var ritualActionCount = 0

    var body: some View {
        ComponentGallerySection(title: "05 · 灰雾深红星辰与仪式魔法 (Above Gray Fog & Ritual)") {
            ComponentGallerySpecimenStage(
                title: "灰雾祈祷与祭坛",
                summary: "深红星辰与祭坛都使用正式 callback；统一重置让祈祷、仪式与反馈可以反复从初始态验证。",
                mode: .live,
                controls: {
                    Button("重置仪式") {
                        lastRitualAction = "尚未触发"
                        ritualActionCount = 0
                    }
                    .buttonStyle(WOMButtonStyle(.secondary))
                }
            ) {
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
                LazyVGrid(
                    columns: [
                        GridItem(
                            .adaptive(minimum: 280, maximum: 420),
                            spacing: DesignTokens.Spacing.md
                        )
                    ],
                    alignment: .leading,
                    spacing: DesignTokens.Spacing.md
                ) {
                    CrimsonStarBeaconView(
                        starName: "深红星辰 · 正义小姐",
                        prayerPreview: "请求愚者先生指引贝克兰德非凡聚会情报...",
                        unheardEchoesCount: 2,
                        onTapStar: {
                            recordRitualAction("聆听正义小姐祈祷")
                        }
                    )
                    CrimsonStarBeaconView(
                        starName: "深红星辰 · 倒吊人",
                        prayerPreview: "苏尼亚海发现了幽灵船行踪...",
                        unheardEchoesCount: 0,
                        onTapStar: {
                            recordRitualAction("聆听倒吊人祈祷")
                        }
                    )
                }

                BronzeAltarPrayerCard(
                    deityTitle: "不属于这个时代的愚者",
                    domainName: "灰雾之上的神秘主宰",
                    blessingTitle: "执掌好运的黄黑之王",
                    onChantPrayer: {
                        recordRitualAction("吟诵愚者尊名")
                    }
                )

                MysticKeyValueRow(
                    key: "仪式回执",
                    value: "\(lastRitualAction) · \(ritualActionCount) 次",
                    tone: ritualActionCount == 0 ? .neutral : .crimson,
                    systemIcon: "sparkles"
                )
                }
            }
        }
    }

    private func recordRitualAction(_ title: String) {
        lastRitualAction = title
        ritualActionCount += 1
    }
}

private struct CodexAndDatabaseGallerySection: View {
    @State private var characterAdviceCount = 0

    var body: some View {
        ComponentGallerySection(title: "06 · 人物档案与四库内核 (Codex & Database)") {
            ComponentGallerySpecimenStage(
                title: "人物档案与数据状态",
                summary: "人物 Advice 使用真实入口；数据库卡片显式区分已测量与未探测，避免把演示状态误解为实时探针。",
                mode: .live,
                controls: {
                    Button("重置 Advice") {
                        characterAdviceCount = 0
                    }
                    .buttonStyle(WOMButtonStyle(.secondary))
                }
            ) {
                WOMAdaptivePair(
                trailingIdealWidth: 240,
                primaryIdealWidth: 520,
                spacing: DesignTokens.Spacing.lg
            ) {
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                    CharacterCodexCard(
                        characterName: "克莱恩·莫雷蒂",
                        pathwayTitle: "占卜家途径 · 序列 9",
                        occupation: "值夜者文职人员",
                        location: "佐特兰街36号",
                        onVoiceAdviceTapped: {
                            characterAdviceCount += 1
                        }
                    )

                    MysticKeyValueRow(
                        key: "Advice 入口",
                        value: characterAdviceCount == 0
                            ? "尚未触发"
                            : "已触发 \(characterAdviceCount) 次",
                        tone: characterAdviceCount == 0 ? .neutral : .teal,
                        systemIcon: "waveform.badge.mic"
                    )
                }
            } secondary: {
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                    // 组件样例：显式并列「探针已接入」与「未接入」两种合法状态，
                    // 生产页面在探针不可达时必须使用后者。
                    Text("组件样例 · 探针状态 (Probed / Not Probed)")
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.textTertiary)

                    DatabaseStatusHUDCard(
                        role: .canon,
                        status: .measured(sizeText: "38.2 MB", isHealthy: true)
                    )
                    DatabaseStatusHUDCard(
                        role: .world,
                        status: .measured(sizeText: "14.6 MB", isHealthy: true)
                    )
                    DatabaseStatusHUDCard(
                        role: .retrieval,
                        status: .measured(sizeText: "52.1 MB", isHealthy: true)
                    )
                    DatabaseStatusHUDCard(role: .runtime)
                }
            }
            }
        }
    }
}

private struct SidebarGallerySection: View {
    var body: some View {
        ComponentGallerySection(title: "07 · 侧边栏菜单系统 (Sidebar & Navigation Menu)") {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
                Text("两个样例都是真实绑定：可以点击导航项，也可以使用顶部按钮折叠或展开。状态变化只留在画廊会话，不改变 App 全局导航。")
                    .font(Font.Mystic.bodyMedium)
                    .foregroundStyle(Color.Mystic.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)

                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: DesignTokens.Spacing.xl) {
                        SidebarGallerySample(title: "展开起始态 (Expanded · 224pt)", isCollapsed: false)
                        SidebarGallerySample(title: "折叠起始态 (Collapsed · 68pt)", isCollapsed: true)
                    }

                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
                        SidebarGallerySample(title: "展开起始态 (Expanded · 224pt)", isCollapsed: false)
                        SidebarGallerySample(title: "折叠起始态 (Collapsed · 68pt)", isCollapsed: true)
                    }
                }
            }
        }
    }
}

private struct SidebarGallerySample: View {
    private static let badgeCounts: [NavigationItem: Int] = [.fate: 2, .worldline: 1, .cards: 4]

    let title: String
    private let initialCollapsed: Bool
    @State private var selection: NavigationItem = .fate
    @State private var isCollapsed: Bool

    init(title: String, isCollapsed: Bool) {
        self.title = title
        self.initialCollapsed = isCollapsed
        self._isCollapsed = State(initialValue: isCollapsed)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            HStack(spacing: DesignTokens.Spacing.sm) {
                Text(title)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.brassGoldMuted)

                Spacer(minLength: DesignTokens.Spacing.xs)

                MysticBadge(
                    isCollapsed ? "折叠" : "展开",
                    tone: isCollapsed ? .neutral : .teal,
                    systemIcon: isCollapsed ? "sidebar.right" : "sidebar.left"
                )

                Button {
                    selection = .fate
                    isCollapsed = initialCollapsed
                } label: {
                    WOMIcon(system: .retry, size: .compact, accessibilityLabel: "恢复侧边栏样例")
                }
                .buttonStyle(WOMToolbarButtonStyle(.tertiary))
                .help("恢复侧边栏样例的初始选择与折叠状态")
            }

            AppSidebarView(
                selection: $selection,
                isCollapsed: $isCollapsed,
                badgeCounts: Self.badgeCounts
            )
            .frame(height: 560)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
                    .stroke(Color.Mystic.brassGoldBorder.opacity(0.4), lineWidth: 1)
            )

            Text("当前选择：\(selection.localizedTitle)")
                .font(Font.Mystic.monoBadge)
                .foregroundStyle(Color.Mystic.textSecondary)
        }
    }
}

private struct CanonicalGeographyGallerySection: View {
    @State private var lastGeographySelection = "尚未选择"

    var body: some View {
        ComponentGallerySection(title: "08 · 原著正典地域档案 (Canonical Geography)") {
            ComponentGallerySpecimenStage(
                title: "地域与运行时场景",
                summary: "场景页头使用已批准 wideHeader；廷根与贝克兰德保持完整档案尺度，并通过正式选择回调验证地域交互。",
                mode: .live,
                controls: {
                    Button("重置地域") {
                        lastGeographySelection = "尚未选择"
                    }
                    .buttonStyle(WOMButtonStyle(.secondary))
                }
            ) {
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
                WOMSceneHeroHeader(
                    scene: .worldObservation,
                    icon: .asset(.world),
                    title: "世界观察 · 运行时场景页头"
                )

                Text("场景页头直接加载已批准的 wideHeader 派生图；地域组件保留完整档案尺度。黄水晶占卜已提升到 03 交互主展区，避免同一真实组件重复占据两个画廊层级。")
                    .font(Font.Mystic.bodyMedium)
                    .foregroundStyle(Color.Mystic.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)

                WOMAdaptivePair(
                    trailingIdealWidth: 420,
                    primaryIdealWidth: 420,
                    spacing: DesignTokens.Spacing.lg
                ) {
                    TingenCityDossierCard { location in
                        lastGeographySelection = "廷根 · \(location.rawValue)"
                    }
                    .frame(maxWidth: .infinity)
                } secondary: {
                    BacklundMetropolisCard { district in
                        lastGeographySelection = "贝克兰德 · \(district.rawValue)"
                    }
                    .frame(maxWidth: .infinity)
                }

                MysticKeyValueRow(
                    key: "地域选择",
                    value: lastGeographySelection,
                    tone: lastGeographySelection == "尚未选择" ? .neutral : .gold,
                    systemIcon: "map"
                )
                }
            }
        }
    }
}
