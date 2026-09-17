import SwiftUI

public struct ContentView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

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
            AppSidebarView(
                selection: $currentNavigation,
                isCollapsed: $isSidebarCollapsed
            )

            VStack(spacing: 0) {
                engineStatusBar

                ScrollView {
                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
                        mainContentForCurrentNavigation
                    }
                    .padding(DesignTokens.Spacing.xl)
                }

                persistentAdviceBar
            }
        }
        .background(
            Color.Mystic.obsidianBase
                .overlay(WOMTextureLayer(.sacredSlate, opacity: 0.012))
        )
        .frame(
            minWidth: WOMWindowMetrics.minimumWidth,
            minHeight: WOMWindowMetrics.minimumHeight
        )
        .task {
            if !appState.isEngineReady {
                await appState.startAndConnect()
            }
        }
    }

    private var engineStatusBar: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: DesignTokens.Spacing.md) {
                engineConnectionStatus
                Spacer(minLength: DesignTokens.Spacing.md)
                worldTimeStatus
            }

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                engineConnectionStatus
                worldTimeStatus
            }
        }
        .padding(.horizontal, DesignTokens.Spacing.xl)
        .padding(.vertical, DesignTokens.Spacing.md)
        .background(
            WOMPanelBackground(
                tone: .floating,
                cornerRadius: 0,
                texture: .sacredSlate,
                textureOpacity: 0.018
            )
        )
    }

    private var engineConnectionStatus: some View {
        HStack(spacing: DesignTokens.Spacing.sm) {
            WOMIcon(
                status: appState.isEngineReady ? .success : .warning,
                size: .compact,
                accessibilityLabel: appState.isEngineReady ? "本地引擎已就绪" : "本地引擎未连接"
            )
            .foregroundStyle(
                appState.isEngineReady
                    ? Color.Mystic.statusOnline
                    : Color.Mystic.statusWarning
            )

            Text(appState.isEngineReady ? "本地引擎已就绪 · IPC 活跃" : "本地引擎未连接 (演示模式)")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var worldTimeStatus: some View {
        HStack(spacing: DesignTokens.Spacing.xs) {
            WOMIcon(.world, size: .compact)
                .foregroundStyle(Color.Mystic.brassGoldMuted)
            Text("第五纪 · 1349 年 · 廷根市")
                .font(Font.Mystic.monoBadge)
                .foregroundStyle(Color.Mystic.textGoldAccent)
        }
    }

    private var persistentAdviceBar: some View {
        VStack(spacing: DesignTokens.Spacing.md) {
            AdviceInputField(
                text: $adviceDraft,
                targetCharacter: "克莱恩·莫雷蒂",
                onVoiceTapped: {
                    withAnimation(reduceMotion ? nil : DesignTokens.Motion.smoothSpring) {
                        ringState = ringState == .idle ? .listening : .idle
                    }
                },
                onSubmitAdvice: { _ in
                    withAnimation(reduceMotion ? nil : DesignTokens.Motion.smoothSpring) {
                        ringState = .deciding
                    }
                }
            )

            ListeningRingView(state: ringState) {
                withAnimation(reduceMotion ? nil : DesignTokens.Motion.smoothSpring) {
                    ringState = ringState == .idle ? .listening : .idle
                }
            }
        }
        .padding(.horizontal, DesignTokens.Spacing.xl)
        .padding(.bottom, DesignTokens.Spacing.lg)
        .padding(.top, DesignTokens.Spacing.sm)
        .background(
            WOMPanelBackground(
                tone: .floating,
                cornerRadius: 0,
                texture: .sacredSlate,
                textureOpacity: 0.018
            )
        )
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
            WOMAdaptivePair(
                trailingIdealWidth: WOMWorkspaceMetrics.fateAnchorWidth
            ) {
                situationColumn
            } secondary: {
                characterAnchorCard
            }

            FateArtifactInterventionView()
        }
    }

    private var situationColumn: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
            Text("命运干预 · 局势卷宗 (Current Situation)")
                .font(Font.Mystic.titleMedium)
                .foregroundStyle(Color.Mystic.textGoldAccent)
                .fixedSize(horizontal: false, vertical: true)

            VictorianCard(style: .obsidianGlass) {
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                    Text("当前危局：韦尔奇卧室内的红月案发")
                        .font(Font.Mystic.titleSmall)
                        .foregroundStyle(Color.Mystic.brassGoldPrimary)
                        .fixedSize(horizontal: false, vertical: true)

                    Text("克莱恩在枪声与血迹中苏醒，桌上散落着转轮手枪、黄铜怀表与未燃尽的信件。红月光晕正穿透窗帘，灵性直觉提示危险正在临近。")
                        .font(Font.Mystic.bodyMedium)
                        .foregroundStyle(Color.Mystic.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
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
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private var characterAnchorCard: some View {
        VictorianCard(style: .brassFramed) {
            VStack(spacing: DesignTokens.Spacing.md) {
                Text("人物灵视与状态锚点")
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)
                    .fixedSize(horizontal: false, vertical: true)

                SpiritualityGaugeView(title: "克莱恩 · 灵性阈值", value: 0.78)

                WOMDividerOrnament(opacity: 0.45)

                ViewThatFits(in: .horizontal) {
                    HStack {
                        Text("当前序列")
                            .font(Font.Mystic.caption)
                            .foregroundStyle(Color.Mystic.textSecondary)
                        Spacer(minLength: DesignTokens.Spacing.sm)
                        Text("未服食魔药 (凡人)")
                            .font(Font.Mystic.monoBadge)
                            .foregroundStyle(Color.Mystic.textGoldAccent)
                    }

                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                        Text("当前序列")
                            .font(Font.Mystic.caption)
                            .foregroundStyle(Color.Mystic.textSecondary)
                        Text("未服食魔药 (凡人)")
                            .font(Font.Mystic.monoBadge)
                            .foregroundStyle(Color.Mystic.textGoldAccent)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var worldHomeContent: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
            HStack(spacing: DesignTokens.Spacing.sm) {
                WOMIcon(.world, size: .prominent)
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)
                Text("世界脉动 (World Observation)")
                    .font(Font.Mystic.titleMedium)
                    .foregroundStyle(Color.Mystic.textGoldAccent)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Text("贝克兰德正在晨雾与蒸汽烟囱中苏醒，塔索克河上的轮船汽笛隐隐传来。世界正在独立演化，不因单次故事结束而重置。")
                .font(Font.Mystic.bodyLarge)
                .foregroundStyle(Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(DesignTokens.LayoutInsets.cardPadding)
        .womCardChrome(
            tone: .card,
            texture: .sacredSlate,
            cornerRadius: DesignTokens.Radii.lg
        )
    }

    @ViewBuilder
    private var settingsContent: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
            HStack(spacing: DesignTokens.Spacing.sm) {
                WOMIcon(system: .settings, size: .prominent)
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)
                Text("系统设置与四库物理隔离监视 (Engine & Storage HUD)")
                    .font(Font.Mystic.titleMedium)
                    .foregroundStyle(Color.Mystic.textGoldAccent)
                    .fixedSize(horizontal: false, vertical: true)
            }

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 240), spacing: DesignTokens.Spacing.md)],
                spacing: DesignTokens.Spacing.md
            ) {
                DatabaseStatusHUDCard(role: .canon, isHealthy: true, sizeText: "38.2 MB")
                DatabaseStatusHUDCard(role: .world, isHealthy: true, sizeText: "14.6 MB")
                DatabaseStatusHUDCard(role: .retrieval, isHealthy: true, sizeText: "52.1 MB")
                DatabaseStatusHUDCard(role: .runtime, isHealthy: true, sizeText: "4.8 MB")
            }
        }
    }

    @ViewBuilder
    private var genericWorkspacePlaceholder: some View {
        VStack(spacing: DesignTokens.Spacing.md) {
            WOMIcon(
                source: currentNavigation.iconSource,
                size: .large,
                accessibilityLabel: currentNavigation.localizedTitle
            )
            .foregroundStyle(Color.Mystic.brassGoldPrimary)

            Text("\(currentNavigation.localizedTitle) 视图模块就绪")
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.textPrimary)

            Text("该入口当前仍是功能占位；视觉系统已就绪，但不会将未实现功能标记为生产完成。")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, minHeight: 280)
        .padding(DesignTokens.LayoutInsets.cardPadding)
        .womCardChrome(
            tone: .card,
            texture: .sacredSlate,
            cornerRadius: DesignTokens.Radii.lg
        )
    }
}

#Preview {
    ContentView()
        .environment(AppState())
}
