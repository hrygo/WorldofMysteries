import SwiftUI

/// 组件全景画廊视图（单页集中预览与调试全部 14 大核心 UI 组件）
/// 彻底解决频繁切换不同文件时 Xcode Previews 反复冷启动与进程重建的性能痛点
public struct ComponentGalleryView: View {
    @State private var adviceDraft: String = "小心身后的红月，屏住呼吸离开房间。"
    @State private var ringState: ListeningRingState = .listening
    @State private var pendulumState: PendulumState = .affirmative
    @State private var isPraying: Bool = false
    @State private var testSelectedCard: Bool = true
    @State private var testClickCount: Int = 0
    
    public init() {}
    
    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxl) {
                // 画廊顶部标牌
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                    Text("《诡秘世界》UI 组件全景画廊")
                        .font(Font.Mystic.gothicDisplay)
                        .foregroundStyle(Color.Mystic.brassGoldPrimary)
                    
                    Text("集中展示 16 大核心组件与 8 项通用原语 · 单一 Canvas 会话 · 零重复冷启动开销")
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
                
                // 9. 统一交互规范与排版标尺
                gallerySection(title: "09 · 统一交互规范与排版标尺 (UX & Typography Specimen)") {
                    VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
                        // 1. 交互状态展示栏
                        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                            Text("交互状态展示 (Interaction States)：")
                                .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                            
                            HStack(spacing: DesignTokens.LayoutInsets.stackSpacingMd) {
                                // 常态卡片
                                VStack(alignment: .leading, spacing: 4) {
                                    Text("常态 (Default)")
                                        .font(.system(size: 10, weight: .bold))
                                        .foregroundStyle(Color.Mystic.textTertiary)
                                    Text("黑曜石底板 · 细发丝边框")
                                        .font(Font.Mystic.caption)
                                        .foregroundStyle(Color.Mystic.textSecondary)
                                }
                                .padding(DesignTokens.LayoutInsets.compactCardPadding)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(Color.Mystic.obsidianCard)
                                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
                                .mysticCardSelection(isSelected: false, isHovered: false)
                                
                                // 选中态卡片（带高亮轮廓与微发光）
                                Button {
                                    withAnimation(DesignTokens.Interaction.selectionSpring) {
                                        testSelectedCard.toggle()
                                    }
                                } label: {
                                    VStack(alignment: .leading, spacing: 4) {
                                        HStack {
                                            Text(testSelectedCard ? "已选中 (Selected)" : "未选中 (Unselected)")
                                                .font(.system(size: 10, weight: .bold))
                                                .foregroundStyle(testSelectedCard ? Color.Mystic.brassGoldPrimary : Color.Mystic.textTertiary)
                                            Spacer()
                                            Image(systemName: testSelectedCard ? "checkmark.circle.fill" : "circle")
                                                .font(.system(size: 11))
                                                .foregroundStyle(testSelectedCard ? Color.Mystic.brassGoldPrimary : Color.Mystic.textTertiary)
                                        }
                                        Text("1.5pt 暗金边框 · 6pt 呼吸微光 (点击切换)")
                                            .font(Font.Mystic.caption)
                                            .foregroundStyle(Color.Mystic.textPrimary)
                                    }
                                    .padding(DesignTokens.LayoutInsets.compactCardPadding)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .background(Color.Mystic.obsidianCard)
                                    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
                                    .mysticCardSelection(isSelected: testSelectedCard, isHovered: false)
                                }
                                .mysticPressable()
                                
                                // 按压微物理反馈测试按钮
                                Button {
                                    testClickCount += 1
                                } label: {
                                    VStack(alignment: .leading, spacing: 4) {
                                        HStack {
                                            Text("点击微物理反馈")
                                                .font(.system(size: 10, weight: .bold))
                                                .foregroundStyle(Color.Mystic.statusOnline)
                                            Spacer()
                                            Text("x\(testClickCount)")
                                                .font(.system(size: 10, weight: .bold, design: .monospaced))
                                                .foregroundStyle(Color.Mystic.statusOnline)
                                        }
                                        Text("Scale 0.98 阻尼回弹 · 点击体验")
                                            .font(Font.Mystic.caption)
                                            .foregroundStyle(Color.Mystic.textPrimary)
                                    }
                                    .padding(DesignTokens.LayoutInsets.compactCardPadding)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .background(Color.Mystic.obsidianCard)
                                    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
                                            .stroke(Color.Mystic.statusOnline.opacity(0.4), lineWidth: 1)
                                    )
                                }
                                .mysticPressable()
                            }
                        }
                        
                        // 2. 排版度量衡标尺
                        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                            Text("排版度量衡标尺 (Typography Rhythm & Kerning)：")
                                .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                            
                            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                                Text("古典巨幕 (32pt 衬线 / Tracking +0.6pt / 严谨行距)")
                                    .font(Font.Mystic.gothicDisplay)
                                    .tracking(DesignTokens.TypographyMetrics.gothicDisplayTracking)
                                    .foregroundStyle(Color.Mystic.brassGoldPrimary)
                                
                                Text("沉浸叙事对白 (16pt 衬线 / 行间距 6.0pt / Tracking +0.25pt)：\n“我们在黑暗中守护光明，却也必须时刻警惕来自虚空的凝视。不属于这个时代的愚者，正在灰雾之上默默注视着命运轮转。”")
                                    .mysticNarrativeStyle()
                                
                                Text("侦探草写便签 (14pt 楷体 / 行间距 5.0pt)：\n明斯克街15号夏洛克·莫里亚蒂侦探亲笔 —— 追查绝密赫密斯语手稿。")
                                    .font(Font.Mystic.parchmentCursive)
                                    .lineSpacing(DesignTokens.TypographyMetrics.parchmentLineSpacing)
                                    .foregroundStyle(Color.Mystic.brassGoldMuted)
                                
                                HStack(spacing: DesignTokens.Spacing.lg) {
                                    Text("机械等宽徽标 (Tracking +0.4pt): [SEQ-9-SEER-001]")
                                        .font(Font.Mystic.monoBadge)
                                        .tracking(DesignTokens.TypographyMetrics.monoTracking)
                                        .foregroundStyle(Color.Mystic.statusOnline)
                                    
                                    Text("紧凑元数据 (行间距 2.0pt / Tracking +0.2pt)")
                                        .mysticCaptionStyle(color: Color.Mystic.textTertiary)
                                }
                            }
                            .padding(DesignTokens.LayoutInsets.cardPadding)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.Mystic.obsidianElevated)
                            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
                            .overlay(
                                RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
                                    .stroke(Color.Mystic.brassGoldBorder.opacity(0.6), lineWidth: 1)
                            )
                        }
                    }
                }
                
                // 10. 通用原语组装
                gallerySection(title: "10 · 通用原语组装 (Primitives Assembly)") {
                    VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
                        // 语义色调徽章
                        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                            Text("语义色调徽章 (MysticTone × MysticBadge)：")
                                .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                            
                            HStack(spacing: DesignTokens.LayoutInsets.stackSpacingSm) {
                                ForEach(MysticTone.allCases, id: \.rawValue) { tone in
                                    MysticBadge(tone.semanticLabel, tone: tone, systemIcon: "circle.fill")
                                }
                            }
                            
                            HStack(spacing: DesignTokens.LayoutInsets.stackSpacingSm) {
                                MysticBadge("正典锁定", tone: .gold, variant: .panel, systemIcon: "lock.shield")
                                MysticBadge("幂等可重建", tone: .teal, variant: .panel, systemIcon: "arrow.triangle.2.circlepath")
                                MysticBadge("受阻：灵界干扰", tone: .amber, variant: .panel, systemIcon: "exclamationmark.triangle")
                            }
                        }
                        
                        // 计量条与状态点
                        HStack(alignment: .top, spacing: DesignTokens.Spacing.xl) {
                            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                                Text("计量条与临界阈值 (MysticMetricBar)：")
                                    .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                                MysticMetricBar(value: 0.88, tone: .azure)
                                MysticMetricBar(value: 0.52, tone: .gold)
                                MysticMetricBar(value: 0.18, tone: .teal, criticalThreshold: 0.25)
                            }
                            .frame(width: 220)
                            
                            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                                Text("呼吸状态点 (MysticStatusDot)：")
                                    .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                                MysticStatusDot(tone: .teal, label: "引擎在线")
                                MysticStatusDot(tone: .amber, isPulsing: true, label: "推演进行中")
                                MysticStatusDot(tone: .crimson, label: "通路中断")
                                MysticStatusDot(tone: .neutral, diameter: 6, label: "未激活")
                            }
                        }
                        
                        // 键值行与图标命令按钮
                        HStack(alignment: .top, spacing: DesignTokens.Spacing.xl) {
                            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                                MysticKeyValueRow(key: "引擎", value: "AgentScope 2.0.8", isMonospaced: true, systemIcon: "cpu")
                                MysticKeyValueRow(key: "运行时", value: "Python 3.14.7", isMonospaced: true, systemIcon: "terminal")
                                MysticKeyValueRow(key: "当前分支", value: "main", tone: .teal, systemIcon: "arrow.triangle.branch")
                            }
                            .frame(width: 300)
                            
                            HStack(spacing: DesignTokens.Spacing.sm) {
                                MysticIconButton(systemIcon: "arrow.triangle.2.circlepath", title: "重建投影", tone: .teal, helpText: "retrieval.db 100% 幂等重建") {}
                                MysticIconButton(systemIcon: "speaker.wave.2.fill", title: "原声回放") {}
                                MysticIconButton(systemIcon: "square.and.arrow.up", tone: .neutral, helpText: "导出本章证据") {}
                            }
                        }
                        
                        // 空态占位
                        MysticEmptyState(
                            systemIcon: "text.book.closed",
                            title: "尚无已提交章回",
                            message: "章回只在 COMMIT 之后进入故事书；表达层重试不会回写已提交事实。",
                            tone: .gold,
                            actionTitle: "查看世界脉动",
                            onAction: {}
                        )
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
            MysticSectionHeader(title: title, isProminent: true)
            
            content()
            
            MysticDivider()
                .padding(.top, DesignTokens.Spacing.md)
        }
    }
}

#Preview("Component Gallery (14 Components)") {
    ComponentGalleryView()
        .frame(minWidth: 800, minHeight: 900)
}
