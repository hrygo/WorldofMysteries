import SwiftUI

public struct ContentView: View {
    @Environment(AppState.self) private var appState
    @Binding public var currentNavigation: NavigationItem
    @Binding public var isSidebarCollapsed: Bool
    
    @State private var ringState: ListeningRingState = .idle
    @State private var adviceDraft: String = ""

    public init(
        currentNavigation: Binding<NavigationItem> = .constant(.fate),
        isSidebarCollapsed: Binding<Bool> = .constant(false)
    ) {
        self._currentNavigation = currentNavigation
        self._isSidebarCollapsed = isSidebarCollapsed
    }

    public var body: some View {
        HStack(spacing: 0) {
            // 8+1 栏沉浸式侧边栏菜单（支持折叠/展开、徽标与状态微卡片）
            AppSidebarView(
                selection: $currentNavigation,
                isCollapsed: $isSidebarCollapsed
            )

            // 主内容视图区
            VStack(spacing: 0) {
                // 顶部状态栏
                HStack(spacing: DesignTokens.Spacing.md) {
                    HStack(spacing: DesignTokens.Spacing.sm) {
                        Circle()
                            .fill(appState.isEngineReady ? Color.Mystic.statusOnline : Color.Mystic.statusWarning)
                            .frame(width: 8, height: 8)
                            .shadow(color: appState.isEngineReady ? Color.Mystic.statusOnline : Color.Mystic.statusWarning, radius: 4)

                        Text(appState.isEngineReady ? "本地引擎已就绪 · IPC 活跃" : "本地引擎未连接 (演示模式)")
                            .font(Font.Mystic.caption)
                            .foregroundStyle(Color.Mystic.textSecondary)
                    }

                    Spacer()

                    Text("第五纪 · 1349 年 · 廷根市")
                        .font(Font.Mystic.monoBadge)
                        .foregroundStyle(Color.Mystic.textGoldAccent)
                }
                .padding(.horizontal, DesignTokens.Spacing.xl)
                .padding(.vertical, DesignTokens.Spacing.md)
                .background(Color.Mystic.obsidianElevated)

                // 中间主体工作区
                ScrollView {
                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
                        mainContentForCurrentNavigation
                    }
                    .padding(DesignTokens.Spacing.xl)
                }

                // 底部常驻 Advice 输入与 Listening Ring 交互栏
                VStack(spacing: DesignTokens.Spacing.md) {
                    AdviceInputField(
                        text: $adviceDraft,
                        targetCharacter: "克莱恩·莫雷蒂",
                        onVoiceTapped: {
                            withAnimation(DesignTokens.Motion.smoothSpring) {
                                ringState = ringState == .idle ? .listening : .idle
                            }
                        },
                        onSubmitAdvice: { _ in
                            withAnimation(DesignTokens.Motion.smoothSpring) {
                                ringState = .deciding
                            }
                        }
                    )

                    ListeningRingView(state: ringState) {
                        withAnimation(DesignTokens.Motion.smoothSpring) {
                            ringState = ringState == .idle ? .listening : .idle
                        }
                    }
                }
                .padding(.horizontal, DesignTokens.Spacing.xl)
                .padding(.bottom, DesignTokens.Spacing.lg)
                .padding(.top, DesignTokens.Spacing.sm)
                .background(Color.Mystic.obsidianElevated.opacity(0.85))
            }
        }
        .background(Color.Mystic.obsidianBase)
        .frame(minWidth: 960, minHeight: 640)
        .task {
            if !appState.isEngineReady {
                await appState.startAndConnect()
            }
        }
    }

    @ViewBuilder
    private var mainContentForCurrentNavigation: some View {
        switch currentNavigation {
        case .fate:
            fateInterventionContent
        case .world:
            worldHomeContent
        case .gallery:
            ComponentGalleryView()
        case .settings:
            settingsContent
        default:
            genericWorkspacePlaceholder
        }
    }

    @ViewBuilder
    private var fateInterventionContent: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
            HStack(alignment: .top, spacing: DesignTokens.Spacing.lg) {
                // 左栏：六维态势卷宗
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
                    Text("命运干预 · 局势卷宗 (Current Situation)")
                        .font(Font.Mystic.titleMedium)
                        .foregroundStyle(Color.Mystic.textGoldAccent)

                    VictorianCard(style: .obsidianGlass) {
                        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                            Text("当前危局：韦尔奇卧室内的红月案发")
                                .font(Font.Mystic.titleSmall)
                                .foregroundStyle(Color.Mystic.brassGoldPrimary)

                            Text("克莱恩在枪声与血迹中苏醒，桌上散落着转轮手枪、黄铜怀表与未燃尽的信件。红月光晕正穿透窗帘，灵性直觉提示危险正在临近。")
                                .font(Font.Mystic.bodyMedium)
                                .foregroundStyle(Color.Mystic.textSecondary)
                        }
                    }

                    VictorianCard(style: .parchment) {
                        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                            Text("【已知事实与线索】")
                                .font(Font.Mystic.caption)
                                .foregroundStyle(Color.Mystic.parchmentInk)
                            Text("• 《安提哥努斯家族笔记》已被某人带走。\n• 韦尔奇与娜娅已确认身亡，死因与自杀手枪一致。\n• 窗外街道有黑夜教会值夜者的马车驻留声。")
                                .font(Font.Mystic.parchmentCursive)
                                .foregroundStyle(Color.Mystic.parchmentInk)
                        }
                    }
                }
                .frame(maxWidth: .infinity)

                // 右栏：非凡状态仪表与人物锚点
                VictorianCard(style: .brassFramed) {
                    VStack(spacing: DesignTokens.Spacing.md) {
                        Text("人物灵视与状态锚点")
                            .font(Font.Mystic.titleSmall)
                            .foregroundStyle(Color.Mystic.brassGoldPrimary)

                        SpiritualityGaugeView(title: "克莱恩 · 灵性阈值", value: 0.78)

                        Divider().background(Color.Mystic.brassGoldBorder)

                        HStack {
                            Text("当前序列")
                                .font(Font.Mystic.caption)
                                .foregroundStyle(Color.Mystic.textSecondary)
                            Spacer()
                            Text("未服食魔药 (凡人)")
                                .font(Font.Mystic.monoBadge)
                                .foregroundStyle(Color.Mystic.textGoldAccent)
                        }
                    }
                }
                .frame(width: 280)
            }

            // 特殊物品作为命运干预工具有机嵌入 Fate，而不是新增一级“道具背包”导航。
            FateArtifactInterventionView()
        }
    }

    @ViewBuilder
    private var worldHomeContent: some View {
        VictorianCard(style: .obsidianGlass) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
                Text("世界脉动 (World Observation)")
                    .font(Font.Mystic.titleMedium)
                    .foregroundStyle(Color.Mystic.textGoldAccent)

                Text("贝克兰德正在晨雾与蒸汽烟囱中苏醒，塔索克河上的轮船汽笛隐隐传来。世界正在独立演化，不因单次故事结束而重置。")
                    .font(Font.Mystic.bodyLarge)
                    .foregroundStyle(Color.Mystic.textSecondary)
            }
        }
    }

    @ViewBuilder
    private var settingsContent: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
            Text("系统设置与四库物理隔离监视 (Engine & Storage HUD)")
                .font(Font.Mystic.titleMedium)
                .foregroundStyle(Color.Mystic.textGoldAccent)

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: DesignTokens.Spacing.md) {
                DatabaseStatusHUDCard(role: .canon, isHealthy: true, sizeText: "38.2 MB")
                DatabaseStatusHUDCard(role: .world, isHealthy: true, sizeText: "14.6 MB")
                DatabaseStatusHUDCard(role: .retrieval, isHealthy: true, sizeText: "52.1 MB")
                DatabaseStatusHUDCard(role: .runtime, isHealthy: true, sizeText: "4.8 MB")
            }
        }
    }

    @ViewBuilder
    private var genericWorkspacePlaceholder: some View {
        VictorianCard(style: .obsidianGlass) {
            VStack(spacing: DesignTokens.Spacing.md) {
                Image(systemName: currentNavigation.systemIcon)
                    .font(.system(size: 40))
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)
                Text("\(currentNavigation.localizedTitle) 视图模块就绪")
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.textPrimary)
                Text("遵循 DesignTokens 与 Invariant #12，UI 严格通过 UDS IPC 驱动。")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
            }
            .frame(maxWidth: .infinity, minHeight: 280)
        }
    }
}

#Preview {
    ContentView()
        .environment(AppState())
}
