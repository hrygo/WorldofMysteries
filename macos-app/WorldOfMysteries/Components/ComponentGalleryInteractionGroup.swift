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
    private let initialAdviceDraft = "小心身后的红月，屏住呼吸离开房间。"
    @State private var adviceDraft = "小心身后的红月，屏住呼吸离开房间。"
    @State private var lastInteraction = "尚未触发"
    @State private var interactionCount = 0

    var body: some View {
        ComponentGallerySection(title: "01 · 声纹交互与干预输入 (Listening & Advice)") {
            ComponentGallerySpecimenStage(
                title: "声纹状态与 Advice 输入",
                summary: "四个 ListeningRing 正式状态与 AdviceInputField 在同一会话中真实响应；重置会恢复初始草稿和交互回执。",
                mode: .live,
                controls: {
                    Button("重置输入") {
                        adviceDraft = initialAdviceDraft
                        lastInteraction = "尚未触发"
                        interactionCount = 0
                    }
                    .buttonStyle(WOMButtonStyle(.secondary))
                }
            ) {
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
                LazyVGrid(
                    columns: [
                        GridItem(
                            .adaptive(minimum: 112, maximum: 148),
                            spacing: DesignTokens.Spacing.md
                        )
                    ],
                    alignment: .leading,
                    spacing: DesignTokens.Spacing.md
                ) {
                    ListeningRingView(state: .idle) {
                        recordInteraction("静息语音环")
                    }
                    ListeningRingView(state: .listening) {
                        recordInteraction("监听语音环")
                    }
                    ListeningRingView(state: .deciding) {
                        recordInteraction("思考语音环")
                    }
                    ListeningRingView(state: .speaking) {
                        recordInteraction("播报语音环")
                    }
                }

                AdviceInputField(
                    text: $adviceDraft,
                    targetCharacter: "克莱恩·莫雷蒂",
                    onVoiceTapped: {
                        recordInteraction("语音建议入口")
                    },
                    onSubmitAdvice: { _ in
                        recordInteraction("提交 Advice")
                    }
                )

                MysticKeyValueRow(
                    key: "最近交互",
                    value: "\(lastInteraction) · \(interactionCount) 次",
                    tone: interactionCount == 0 ? .neutral : .teal,
                    systemIcon: "waveform"
                )
                }
            }
        }
    }

    private func recordInteraction(_ title: String) {
        lastInteraction = title
        interactionCount += 1
    }
}

private struct CardsAndCluesGallerySection: View {
    @State private var selectedClue = "尚未选择"
    @State private var selectedTarotStage = "尚未选择"

    var body: some View {
        ComponentGallerySection(title: "02 · 容器材质与调查卷宗 (Cards & Clues)") {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
                ComponentGallerySpecimenStage(
                    title: "调查线索与材质容器",
                    summary: "线索节点使用正式点击回调；VictorianCard 保持材质展示尺度，不用缩略图替代。",
                    mode: .live,
                    controls: {
                        Button("重置线索") {
                            selectedClue = "尚未选择"
                        }
                        .buttonStyle(WOMButtonStyle(.secondary))
                    }
                ) {
                WOMAdaptivePair(
                    trailingIdealWidth: 320,
                    primaryIdealWidth: 360
                ) {
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
                } secondary: {
                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                        CluePinboardNodeView(
                            title: "自杀的手枪",
                            note: "转轮手枪内缺少一颗子弹。弹壳掉落在书桌右侧脚垫旁。",
                            onNodeTapped: {
                                selectedClue = "自杀的手枪"
                            }
                        )

                        MysticKeyValueRow(
                            key: "调查选择",
                            value: selectedClue,
                            tone: selectedClue == "尚未选择" ? .neutral : .gold,
                            systemIcon: "pin.fill"
                        )
                    }
                }
                }

                ComponentGallerySpecimenStage(
                    title: "塔罗发现态",
                    summary: "固定比例卡牌用横向舞台保留完整构图；四个正式发现阶段都可以实际点击与聚焦。",
                    mode: .stateMatrix,
                    controls: {
                        Button("重置选择") {
                            selectedTarotStage = "尚未选择"
                        }
                        .buttonStyle(WOMButtonStyle(.secondary))
                    }
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
                        key: "卡牌选择",
                        value: selectedTarotStage,
                        tone: selectedTarotStage == "尚未选择" ? .neutral : .gold,
                        systemIcon: "rectangle.portrait.on.rectangle.portrait"
                    )
                }
            }
        }
    }
}

private struct SpiritualityAndPendulumGallerySection: View {
    @State private var scryCount = 0
    @State private var latestStatement = "尚未执链"
    @State private var scrySessionID = UUID()

    var body: some View {
        ComponentGallerySection(title: "03 · 灵性状态与灵摆占卜 (Spirituality & Pendulum)") {
            ComponentGallerySpecimenStage(
                title: "黄水晶吊坠 · 实际仪轨",
                summary: "直接运行 PendulumCitrine 高保真原画、正式输入与灵摆摆动。重置会重建整个卡片会话，便于反复验证从静止到启示的完整过程。",
                mode: .live,
                controls: {
                    Button("重置仪轨") {
                        scrySessionID = UUID()
                        scryCount = 0
                        latestStatement = "尚未执链"
                    }
                    .buttonStyle(WOMButtonStyle(.secondary))
                }
            ) {
                WOMAdaptivePair(
                    trailingIdealWidth: 220,
                    primaryIdealWidth: 620,
                    spacing: DesignTokens.Spacing.xl
                ) {
                    CitrinePendulumScryingCard(
                        defaultStatement: "《安提哥努斯家族笔记》仍遗留在廷根市内。",
                        onScryingTriggered: { statement in
                            scryCount += 1
                            latestStatement = statement
                        }
                    )
                    .id(scrySessionID)
                    .frame(maxWidth: .infinity, alignment: .leading)
                } secondary: {
                    spiritualityCompanionPanel
                }
            }
        }
    }

    private var spiritualityCompanionPanel: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
            Text("灵性读数与交互回执")
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.textPrimary)

            SpiritualityGaugeView(title: "灵性适中", value: 0.58)
            SpiritualityGaugeView(title: "临界预警", value: 0.18)

            WOMDividerOrnament(opacity: 0.45)

            MysticKeyValueRow(
                key: "已触发",
                value: "\(scryCount) 次",
                tone: scryCount == 0 ? .neutral : .gold,
                systemIcon: "hand.point.up.left"
            )

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                Text("最近占卜语句")
                    .mysticCaptionStyle(color: Color.Mystic.textTertiary)
                Text(latestStatement)
                    .font(Font.Mystic.bodyMedium)
                    .foregroundStyle(Color.Mystic.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(DesignTokens.LayoutInsets.compactCardPadding)
        .background(
            WOMPanelBackground(
                tone: .card,
                cornerRadius: DesignTokens.Radii.md,
                texture: .sacredSlate,
                textureOpacity: 0.018
            )
        )
    }
}

private struct WorldlineGallerySection: View {
    @State private var selectedWorldline = "尚未选择"
    @State private var chronicleReplayCount = 0

    var body: some View {
        ComponentGallerySection(title: "04 · 世界线演化与因果分叉 (Worldline Nexus)") {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
                ComponentGallerySpecimenStage(
                    title: "世界线选择",
                    summary: "使用正式 WorldlineNodeView 比较正典与分支状态；选择只更新画廊会话，不写入世界事实。",
                    mode: .live,
                    controls: {
                        Button("重置选择") {
                            selectedWorldline = "尚未选择"
                        }
                        .buttonStyle(WOMButtonStyle(.secondary))
                    }
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

                WOMDividerOrnament(opacity: 0.42)

                VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                    Text("已提交叙事 · Chronicle")
                        .font(Font.Mystic.titleSmall)
                        .foregroundStyle(Color.Mystic.textPrimary)

                    NarrativeChronicleView(
                        role: .character("克莱恩·莫雷蒂"),
                        content: "“这不是梦境……那颗子弹确实穿过了我的太阳穴。先确认桌面、手枪和那本失踪的笔记。”",
                        timestamp: "1349-06-28 · 晨",
                        isAudioPlaying: chronicleReplayCount.isMultiple(of: 2) == false,
                        onReplayAudio: {
                            chronicleReplayCount += 1
                        }
                    )

                    MysticKeyValueRow(
                        key: "原声回放",
                        value: chronicleReplayCount == 0
                            ? "尚未触发"
                            : "已触发 \(chronicleReplayCount) 次",
                        tone: chronicleReplayCount == 0 ? .neutral : .azure,
                        systemIcon: "speaker.wave.2"
                    )
                }
            }
        }
    }
}
