import SwiftUI

/// 输入、调查、灵性与世界线：以玩家直接操作为核心的画廊分组。
struct ComponentGalleryInteractionGroup: View {
    var body: some View {
        ListeningAndAdviceGallerySection()
        CardsAndCluesGallerySection()
        SpiritualityAndPendulumGallerySection()
        WorldlineGallerySection()
    }
}

private struct ListeningAndAdviceGallerySection: View {
    @State private var adviceDraft = "小心身后的红月，屏住呼吸离开房间。"

    var body: some View {
        ComponentGallerySection(title: "01 · 声纹交互与干预输入 (Listening & Advice)") {
            VStack(spacing: DesignTokens.Spacing.lg) {
                HStack(spacing: DesignTokens.Spacing.xl) {
                    ListeningRingView(state: .idle)
                    ListeningRingView(state: .listening)
                    ListeningRingView(state: .deciding)
                    ListeningRingView(state: .speaking)
                }

                AdviceInputField(
                    text: $adviceDraft,
                    targetCharacter: "克莱恩·莫雷蒂"
                )
            }
        }
    }
}

private struct CardsAndCluesGallerySection: View {
    var body: some View {
        ComponentGallerySection(title: "02 · 容器材质与调查卷宗 (Cards & Clues)") {
            HStack(alignment: .top, spacing: DesignTokens.Spacing.lg) {
                VictorianCard(style: .obsidianGlass) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("黑曜石玻璃卡片")
                            .font(Font.Mystic.titleSmall)
                            .foregroundStyle(Color.Mystic.brassGoldPrimary)
                        Text("80% 不透明度磨砂亚克力微光材质。")
                            .font(Font.Mystic.bodyMedium)
                            .foregroundStyle(Color.Mystic.textSecondary)
                    }
                }

                CluePinboardNodeView(
                    title: "自杀的手枪",
                    note: "转轮手枪内缺少一颗子弹。弹壳掉落在书桌右侧脚垫旁。"
                )
            }
        }
    }
}

private struct SpiritualityAndPendulumGallerySection: View {
    var body: some View {
        ComponentGallerySection(title: "03 · 灵性状态与灵摆占卜 (Spirituality & Pendulum)") {
            HStack(alignment: .top, spacing: DesignTokens.Spacing.lg) {
                VStack(spacing: DesignTokens.Spacing.md) {
                    SpiritualityGaugeView(title: "灵性适中", value: 0.58)
                    SpiritualityGaugeView(title: "临界预警", value: 0.18)
                }
                .frame(width: 200)

                SpiritPendulumView(
                    statement: "安提哥努斯笔记在瑞尔·比伯手中。",
                    state: .affirmative
                )
            }
        }
    }
}

private struct WorldlineGallerySection: View {
    var body: some View {
        ComponentGallerySection(title: "04 · 世界线演化与因果分叉 (Worldline Nexus)") {
            VStack(spacing: DesignTokens.Spacing.md) {
                WorldlineNodeView(
                    title: "正典主轴：廷根市的枪声",
                    worldTime: "第五纪 1349年 6月28日 晨",
                    status: .canonical,
                    causeSummary: "既定历史：克莱恩·莫雷蒂自杀苏醒，笔记不知所踪。",
                    turnIndex: 0
                )
                WorldlineNodeView(
                    title: "分支 A：提前上报值夜者小队",
                    worldTime: "第五纪 1349年 6月28日 午",
                    status: .active,
                    causeSummary: "因果偏离：向邓恩汇报日记疑点，码头提前戒严。",
                    turnIndex: 3
                )
            }
        }
    }
}
