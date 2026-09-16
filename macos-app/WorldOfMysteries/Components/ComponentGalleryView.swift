import SwiftUI

/// 组件全景画廊视图（单页集中预览与调试全部 14 大核心 UI 组件）
/// 彻底解决频繁切换不同文件时 Xcode Previews 反复冷启动与进程重建的性能痛点
public struct ComponentGalleryView: View {
    @State private var adviceDraft: String = "小心身后的红月，屏住呼吸离开房间。"
    @State private var ringState: ListeningRingState = .listening
    @State private var pendulumState: PendulumState = .affirmative
    @State private var isPraying: Bool = false
    
    public init() {}
    
    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxl) {
                // 画廊顶部标牌
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                    Text("《诡秘世界》UI 组件全景画廊")
                        .font(Font.Mystic.gothicDisplay)
                        .foregroundStyle(Color.Mystic.brassGoldPrimary)
                    
                    Text("集中展示 14 大核心组件 · 单一 Canvas 会话 · 零重复冷启动开销")
                        .font(Font.Mystic.bodyMedium)
                        .foregroundStyle(Color.Mystic.textSecondary)
                }
                .padding(.bottom, DesignTokens.Spacing.md)
                
                // 1. 声纹交互与干预输入
                gallerySection(title: "01 · 声纹交互与干预输入 (Listening & Advice)") {
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
                
                // 2. 维多利亚卡片与卷宗便签
                gallerySection(title: "02 · 容器材质与调查卷宗 (Cards & Clues)") {
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
                
                // 3. 灵性计量与黄水晶占卜
                gallerySection(title: "03 · 灵性状态与灵摆占卜 (Spirituality & Pendulum)") {
                    HStack(alignment: .top, spacing: DesignTokens.Spacing.lg) {
                        VStack(spacing: DesignTokens.Spacing.md) {
                            SpiritualityGaugeView(title: "灵性适中", value: 0.58)
                            SpiritualityGaugeView(title: "临界预警", value: 0.18)
                        }
                        .frame(width: 200)
                        
                        SpiritPendulumView(
                            statement: "安提哥努斯笔记在瑞尔·比伯手中。",
                            state: pendulumState
                        )
                    }
                }
                
                // 4. 世界线因果节点
                gallerySection(title: "04 · 世界线演化与因果分叉 (Worldline Nexus)") {
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
                
                // 5. 灰雾之上与仪式魔法
                gallerySection(title: "05 · 灰雾深红星辰与仪式魔法 (Above Gray Fog & Ritual)") {
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
                
                // 6. 人物卷宗与数据内核
                gallerySection(title: "06 · 人物档案与四库内核 (Codex & Database)") {
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
                
                // 7. 侧边栏与系统菜单
                gallerySection(title: "07 · 侧边栏菜单系统 (Sidebar & Navigation Menu)") {
                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
                        Text("支持展开（224pt，含 3 大语义分组、Badge 徽标与灵性状态微卡片）与紧凑折叠（68pt）双形态：")
                            .font(Font.Mystic.bodyMedium)
                            .foregroundStyle(Color.Mystic.textSecondary)
                        
                        HStack(alignment: .top, spacing: DesignTokens.Spacing.xl) {
                            // 展开态展示
                            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                                Text("展开形态 (Expanded · 224pt)")
                                    .font(Font.Mystic.caption)
                                    .foregroundStyle(Color.Mystic.brassGoldMuted)
                                
                                AppSidebarView(
                                    selection: .constant(.fate),
                                    isCollapsed: .constant(false),
                                    badgeCounts: [.fate: 2, .worldline: 1, .cards: 4]
                                )
                                .frame(height: 560)
                                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
                                .overlay(
                                    RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
                                        .stroke(Color.Mystic.brassGoldBorder.opacity(0.4), lineWidth: 1)
                                )
                            }
                            
                            // 折叠态展示
                            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                                Text("紧凑折叠 (Collapsed · 68pt)")
                                    .font(Font.Mystic.caption)
                                    .foregroundStyle(Color.Mystic.brassGoldMuted)
                                
                                AppSidebarView(
                                    selection: .constant(.fate),
                                    isCollapsed: .constant(true),
                                    badgeCounts: [.fate: 2, .worldline: 1, .cards: 4]
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
                }
                
                // 8. 原著正典地域与黄水晶占卜
                gallerySection(title: "08 · 原著正典地域与黄水晶占卜 (Citrine & Canonical Geography)") {
                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
                        Text("基于《占卜家·克莱恩》正典原画与原著地理风貌打造的核心神秘学实体与据点卡片：")
                            .font(Font.Mystic.bodyMedium)
                            .foregroundStyle(Color.Mystic.textSecondary)
                        
                        // 黄水晶吊坠灵摆占卜法
                        CitrinePendulumScryingCard()
                            .frame(maxWidth: 580)
                        
                        // 廷根市与贝克兰德态势卡
                        HStack(alignment: .top, spacing: DesignTokens.Spacing.lg) {
                            TingenCityDossierCard()
                                .frame(maxWidth: .infinity)
                            
                            BacklundMetropolisCard()
                                .frame(maxWidth: .infinity)
                        }
                    }
                }
            }
            .padding(DesignTokens.Spacing.xxl)
        }
        .background(Color.Mystic.obsidianBase.ignoresSafeArea())
    }
    
    @ViewBuilder
    private func gallerySection<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
            HStack(spacing: DesignTokens.Spacing.xs) {
                Rectangle()
                    .fill(Color.Mystic.brassGoldPrimary)
                    .frame(width: 3, height: 16)
                Text(title)
                    .font(Font.Mystic.titleMedium)
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)
            }
            
            content()
            
            Divider()
                .background(Color.Mystic.brassGoldBorder.opacity(0.3))
                .padding(.top, DesignTokens.Spacing.md)
        }
    }
}

#Preview("Component Gallery (14 Components)") {
    ComponentGalleryView()
        .frame(minWidth: 800, minHeight: 900)
}
