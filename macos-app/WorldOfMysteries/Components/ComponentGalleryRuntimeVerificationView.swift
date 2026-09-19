import Foundation
import SwiftUI

/// Component Gallery 的真实 macOS 运行时视觉 QA 面。
///
/// 采集脚本在 App 启动前通过 UserDefaults 选择场景与窗口尺寸；该模式只改变主窗口展示内容，
/// 不启动 Engine、不写领域事实，也不替代产品中的 ComponentGalleryView。所有 scenario 直接复用
/// 正式 production component，以便截图证据反映真实 SwiftUI / Asset Catalog / RealityKit 渲染结果。
struct ComponentGalleryRuntimeVerificationView: View {
    static let enabledPreferenceKey = "wom.gallery.verification.enabled"
    static let scenarioPreferenceKey = "wom.gallery.verification.scenario"
    static let widthPreferenceKey = "wom.gallery.verification.width"
    static let heightPreferenceKey = "wom.gallery.verification.height"

    @State private var selectedTarotStage = "尚未选择"
    @State private var selectedWorldline = "尚未选择"
    @State private var characterAdviceCount = 0

    private var scenario: ComponentGalleryVerificationScenario {
        let rawValue = UserDefaults.standard.string(forKey: Self.scenarioPreferenceKey)
        return rawValue.flatMap(ComponentGalleryVerificationScenario.init(rawValue:))
            ?? .pendulum
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
                verificationHeader
                scenarioContent
            }
            .padding(DesignTokens.LayoutInsets.panelPadding)
            .frame(maxWidth: 1180, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .topLeading)
        }
        .background(WOMWindowCanvas())
        .preferredColorScheme(.dark)
        .accessibilityIdentifier("wom.gallery.runtime-verification.\(scenario.rawValue)")
    }

    private var verificationHeader: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
                verificationIdentity
                Spacer(minLength: DesignTokens.Spacing.md)
                MysticBadge("REAL APP RUNTIME", tone: .teal, variant: .panel, systemIcon: "macwindow")
            }

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                verificationIdentity
                MysticBadge("REAL APP RUNTIME", tone: .teal, variant: .panel, systemIcon: "macwindow")
            }
        }
    }

    private var verificationIdentity: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
            Text("Component Gallery · Runtime Visual QA")
                .font(Font.Mystic.titleMedium)
                .foregroundStyle(Color.Mystic.textGoldAccent)

            Text("\(scenario.localizedTitle) · 真实 .app / SwiftUI / 运行时资产渲染")
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)
        }
    }

    @ViewBuilder
    private var scenarioContent: some View {
        switch scenario {
        case .pendulum:
            ComponentGallerySpecimenStage(
                title: "黄水晶吊坠 · 高保真仪轨",
                summary: "直接运行 PendulumCitrine 原画和正式 CitrinePendulumScryingCard；此画面可直接输入并触发真实摆动。",
                mode: .live
            ) {
                CitrinePendulumScryingCard(
                    defaultStatement: "《安提哥努斯家族笔记》仍遗留在廷根市内。"
                )
                .frame(maxWidth: 840, alignment: .leading)
            }

        case .tarot:
            ComponentGallerySpecimenStage(
                title: "塔罗发现态 · Collection",
                summary: "保持真实卡牌比例与正式发现状态，不用统一 Grid 把卡面压成缩略图。",
                mode: .stateMatrix
            ) {
                ScrollView(.horizontal, showsIndicators: false) {
                    LazyHStack(alignment: .top, spacing: DesignTokens.Spacing.lg) {
                        TarotCardView(stage: .unknown) {
                            selectedTarotStage = "未知 · Unknown"
                        }
                        TarotCardView(stage: .silhouette) {
                            selectedTarotStage = "轮廓 · Silhouette"
                        }
                        TarotCardView(stage: .identified) {
                            selectedTarotStage = "已识别 · Identified"
                        }
                        TarotCardView(stage: .established) {
                            selectedTarotStage = "已确立 · Established"
                        }
                    }
                    .padding(.vertical, DesignTokens.Spacing.xs)
                }

                MysticKeyValueRow(
                    key: "当前选择",
                    value: selectedTarotStage,
                    tone: selectedTarotStage == "尚未选择" ? .neutral : .gold,
                    systemIcon: "rectangle.portrait.on.rectangle.portrait"
                )
            }

        case .probabilityDie:
            ComponentGallerySpecimenStage(
                title: "Artifact Vault · 概率之骰工作台",
                summary: "运行完整 ArtifactShowcaseView；默认选中的概率之骰继续使用正式 RealityKit 交互与 Preview Resolver。",
                mode: .live
            ) {
                ArtifactShowcaseView()
            }

        case .worldline:
            ComponentGallerySpecimenStage(
                title: "世界线 · 因果分叉",
                summary: "正式 WorldlineNodeView 比较正典与活动分支；选择仅改变 QA 会话本地状态。",
                mode: .live
            ) {
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
                    WorldlineNodeView(
                        title: "正典主轴：廷根市的枪声",
                        worldTime: "第五纪 1349年 6月28日 晨",
                        status: .canonical,
                        causeSummary: "既定历史：克莱恩·莫雷蒂自杀苏醒，笔记不知所踪。",
                        turnIndex: 0,
                        onSelect: {
                            selectedWorldline = "正典主轴：廷根市的枪声"
                        }
                    )
                    WorldlineNodeView(
                        title: "分支 A：提前上报值夜者小队",
                        worldTime: "第五纪 1349年 6月28日 午",
                        status: .active,
                        causeSummary: "因果偏离：向邓恩汇报日记疑点，码头提前戒严。",
                        turnIndex: 3,
                        onSelect: {
                            selectedWorldline = "分支 A：提前上报值夜者小队"
                        }
                    )
                    MysticKeyValueRow(
                        key: "当前世界线",
                        value: selectedWorldline,
                        tone: selectedWorldline == "尚未选择" ? .neutral : .teal,
                        systemIcon: "point.topleft.down.to.point.bottomright.curvepath"
                    )
                }
            }

        case .characterCodex:
            ComponentGallerySpecimenStage(
                title: "Character Codex · 人物卷宗",
                summary: "人物档案保留正式 Advice 入口；右栏显式展示已测量/未探测两种数据库状态。",
                mode: .live
            ) {
                WOMAdaptivePair(
                    trailingIdealWidth: 260,
                    primaryIdealWidth: 540,
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
                        DatabaseStatusHUDCard(
                            role: .canon,
                            status: .measured(sizeText: "38.2 MB", isHealthy: true)
                        )
                        DatabaseStatusHUDCard(
                            role: .world,
                            status: .measured(sizeText: "14.6 MB", isHealthy: true)
                        )
                        DatabaseStatusHUDCard(role: .runtime)
                    }
                }
            }
        }
    }
}

nonisolated enum ComponentGalleryVerificationScenario: String, CaseIterable, Sendable {
    case pendulum
    case tarot
    case probabilityDie = "probability-die"
    case worldline
    case characterCodex = "character-codex"

    var localizedTitle: String {
        switch self {
        case .pendulum: "黄水晶吊坠"
        case .tarot: "塔罗发现态"
        case .probabilityDie: "概率之骰"
        case .worldline: "世界线"
        case .characterCodex: "人物卷宗"
        }
    }
}
