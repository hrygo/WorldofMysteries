import SwiftUI

/// 工作区外壳：侧边栏 +（状态条 / 滚动工作区 / 语境化建议台）。
///
/// 布局契约：
/// - 只有承载 Advice 干预语义的页面才挂载常驻建议台（`NavigationItem.showsAdviceConsole`），
///   其余页面把高度全部还给可滚动工作区，避免卡片被常驻面板硬切；
/// - 事实契约：界面上的叙事数值来自 `DemoWorldSnapshot` 单一事实源，
///   连接状态来自 `AppState.connectionState`，二者都不在视图内另行编造。
public struct ContentView: View {
    @Environment(AppState.self) private var appState

    @Binding public var currentNavigation: NavigationItem
    @Binding public var isSidebarCollapsed: Bool

    /// 示例世界快照：侧边栏、状态条与工作区共用同一份事实。
    private let snapshot = DemoWorldSnapshot.current

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
                isCollapsed: $isSidebarCollapsed,
                snapshot: snapshot
            )

            WOMWorkspaceColumn {
                engineStatusBar
            } main: {
                workspaceScroll
            } bottom: {
                adviceConsole
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(WOMWindowCanvas())
        .frame(
            minWidth: WOMWindowMetrics.minimumWidth,
            minHeight: WOMWindowMetrics.minimumHeight
        )
        .preferredColorScheme(.dark)
        .task {
            if appState.connectionState == .idle {
                await appState.startAndConnect()
            }
        }
    }

    // MARK: - 状态条

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
        .frame(maxWidth: .infinity, alignment: .leading)
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
                status: connectionStatusIcon,
                size: .compact,
                accessibilityLabel: connectionStatusText
            )
            .foregroundStyle(connectionStatusColor)

            Text(connectionStatusText)
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            if let serviceStatus = appState.serviceStatusText {
                Text(serviceStatus)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
            }

            if appState.isShowingDemoData {
                demoDataChip
            }
        }
        .accessibilityElement(children: .combine)
    }

    /// 明确标注示例数据，避免用户把演示数值当成已接入的引擎事实。
    private var demoDataChip: some View {
        Text("示例数据")
            .font(Font.Mystic.caption)
            .foregroundStyle(Color.Mystic.parchmentInk)
            .padding(.horizontal, DesignTokens.LayoutInsets.badgePaddingHorizontal)
            .padding(.vertical, DesignTokens.LayoutInsets.badgePaddingVertical)
            .background(Capsule().fill(Color.Mystic.parchmentCard))
            .accessibilityLabel("当前界面展示的是示例数据，不是已读取的世界状态")
    }

    private var connectionStatusText: String {
        switch appState.connectionState {
        case .idle: "本地引擎未连接 · 正在准备"
        case .connecting: "正在连接本地引擎…"
        case .scaffoldPreview: "本地引擎未接入 · 界面为示例数据"
        case .unavailable: "此构建未包含本地引擎 · 界面为示例数据"
        case .transportReady: "本地引擎已连接 · 世界功能尚未开放"
        case .ready: "本地引擎已连接 · 世界功能可用"
        case .failed(let message): "本地引擎连接失败：\(message)"
        }
    }

    private var connectionStatusIcon: WOMStatusIcon {
        switch appState.connectionState {
        case .ready, .transportReady: .success
        case .idle, .connecting, .scaffoldPreview, .unavailable, .failed: .warning
        }
    }

    private var connectionStatusColor: Color {
        switch appState.connectionState {
        case .ready, .transportReady: Color.Mystic.statusOnline
        case .scaffoldPreview, .unavailable, .idle, .connecting: Color.Mystic.statusWarning
        case .failed: Color.Mystic.statusDanger
        }
    }

    private var worldTimeStatus: some View {
        HStack(spacing: DesignTokens.Spacing.xs) {
            WOMIcon(.world, size: .compact)
                .foregroundStyle(Color.Mystic.brassGoldMuted)
            Text(snapshot.worldTimeLabel)
                .font(Font.Mystic.monoBadge)
                .foregroundStyle(Color.Mystic.textGoldAccent)
        }
    }

    // MARK: - 工作区

    private var workspaceScroll: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
                sceneHeroHeader
                mainContentForCurrentNavigation
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(DesignTokens.Spacing.xl)
            .padding(.bottom, workspaceBottomInset)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// 场景页头：把已批准的 W1–W6 场景美术放进真实导航场景的入口。
    ///
    /// 命运页不在这里挂页头：`FateArtifactInterventionView` 的 scene 页头已经是同一场景的
    /// 入口，重复叠一张灰雾只会让同一场景出现两次身份条。
    @ViewBuilder
    private var sceneHeroHeader: some View {
        if let scene = WOMSceneArtworkRegistry.scene(for: currentNavigation) {
            WOMSceneHeroHeader(
                scene: scene,
                icon: currentNavigation.iconSource,
                title: currentNavigation.localizedTitle
            )
        }
    }

    /// 建议台存在时额外留出底部呼吸空间，滚动到底时最后一张卡片不会贴在面板边缘。
    ///
    /// 刻意不加「底部渐变遮罩」：在暗色卡片面上它会把下一行文字压成半透明的鬼影，
    /// 观感比干净的平台原生裁切更糟。滚动视口边界按 macOS 原生行为硬裁切即可。
    private var workspaceBottomInset: CGFloat {
        currentNavigation.showsAdviceConsole ? DesignTokens.Spacing.xxl : DesignTokens.Spacing.md
    }

    @ViewBuilder
    private var adviceConsole: some View {
        if currentNavigation.showsAdviceConsole {
            persistentAdviceBar
        }
    }

    private var persistentAdviceBar: some View {
        VStack(spacing: DesignTokens.Spacing.md) {
            // No live story/voice handler has been delivered yet. Keep the draft
            // editable, but never consume it or animate a fabricated accepted turn.
            AdviceInputField(
                text: $adviceDraft,
                targetCharacter: snapshot.characterName,
                onVoiceTapped: nil,
                onSubmitAdvice: nil
            )
            Text("建议与语音功能尚未开放，输入内容不会提交。")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
            ListeningRingView(state: .idle)
                .disabled(true)
        }
        .padding(.horizontal, DesignTokens.Spacing.xl)
        .padding(.top, DesignTokens.Spacing.md)
        .padding(.bottom, DesignTokens.Spacing.md)
        .frame(maxWidth: .infinity)
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
        case .character, .storyBook, .cards, .worldline, .notes:
            plannedModuleBlueprint
        }
    }

    // MARK: - 命运干预

    @ViewBuilder
    private var fateInterventionContent: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
            WOMAdaptivePair(
                trailingIdealWidth: WOMWorkspaceMetrics.fateAnchorWidth,
                primaryIdealWidth: WOMWorkspaceMetrics.fateSituationIdealWidth
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

            // 基线要求 Fate 页同时呈现「不确定性」与「压力」，而不只是已知事实。
            VictorianCard(style: .obsidianGlass) {
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
                    fieldRow(
                        "不确定性 (Uncertainty)",
                        "《安提哥努斯家族笔记》的持有人未知；红月效应的触发条件与持续时间不明。"
                    )

                    WOMDividerOrnament(opacity: 0.4)

                    fieldRow(
                        "压力 (Pressure)",
                        "值夜者的马车已在街口驻留；血迹与枪声会引来巡查，可行动的时间窗口正在收窄。"
                    )
                }
            }

            VictorianCard(style: .obsidianGlass) {
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
                    fieldRow(
                        "涉及人物 (Involved Characters)",
                        "克莱恩·莫雷蒂（当事人）· 韦尔奇（已亡）· 娜娅（已亡）· 黑夜教会值夜者（动向未知）"
                    )

                    WOMDividerOrnament(opacity: 0.4)

                    fieldRow(
                        "潜在后果 (Potential Consequences)",
                        "被发现身处案发现场而遭到盘查；或错失追回笔记的唯一窗口。"
                    )
                }
            }
        }
    }

    private func fieldRow(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
            Text(label)
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textTertiary)

            Text(value)
                .font(Font.Mystic.bodyMedium)
                .foregroundStyle(Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var characterAnchorCard: some View {
        VictorianCard(style: .brassFramed) {
            VStack(spacing: DesignTokens.Spacing.md) {
                Text("人物灵视与状态锚点")
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)
                    .fixedSize(horizontal: false, vertical: true)

                SpiritualityGaugeView(
                    title: "\(snapshot.characterShortName) · 灵性阈值",
                    value: snapshot.spirituality
                )

                WOMDividerOrnament(opacity: 0.45)

                VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                    fieldRow("当前序列", snapshot.sequenceDescription)
                    fieldRow("所处位置", snapshot.locationLabel)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: - 世界观察

    @ViewBuilder
    private var worldHomeContent: some View {
        WOMAdaptivePair(
            trailingIdealWidth: WOMWorkspaceMetrics.worldDossierIdealWidth,
            primaryIdealWidth: WOMWorkspaceMetrics.worldPulseIdealWidth
        ) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
                worldPulseCard
                observableEventsCard
            }
        } secondary: {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
                TingenCityDossierCard()
                worldObservationConsole
            }
        }
    }

    private var worldPulseCard: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
            HStack(spacing: DesignTokens.Spacing.sm) {
                WOMIcon(.world, size: .prominent)
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)
                Text("世界脉动 (World Observation)")
                    .font(Font.Mystic.titleMedium)
                    .foregroundStyle(Color.Mystic.textGoldAccent)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Text("廷根市正在晨雾与煤气灯余烬中苏醒，塔索克河上的轮船汽笛隐隐传来。世界正在独立演化，不因单次故事结束而重置。")
                .font(Font.Mystic.bodyLarge)
                .foregroundStyle(Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(DesignTokens.LayoutInsets.cardPadding)
        .womCardChrome(
            tone: .card,
            texture: .sacredSlate,
            cornerRadius: DesignTokens.Radii.lg
        )
    }

    private var observableEventsCard: some View {
        VictorianCard(style: .obsidianGlass) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
                Text("可观察事件 (World Pulse)")
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)

                VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                    observableEventRow("06:40", "明斯克街的煤气灯尚未熄灭，报童开始沿街叫卖。")
                    observableEventRow("07:15", "塔索克河码头卸下一批未申报的机械零件。")
                    observableEventRow("08:02", "值夜者的马车在明斯克街口驻留至今，未有人下车。")
                }
            }
        }
    }

    private func observableEventRow(_ time: String, _ text: String) -> some View {
        HStack(alignment: .top, spacing: DesignTokens.Spacing.sm) {
            Text(time)
                .font(Font.Mystic.monoBadge)
                .foregroundStyle(Color.Mystic.textGoldAccent)
                .frame(width: 48, alignment: .leading)

            Text(text)
                .font(Font.Mystic.bodyMedium)
                .foregroundStyle(Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Observe Voice：向世界发问的入口（基线 §11 的三种语音模式之一）。
    private var worldObservationConsole: some View {
        VictorianCard(style: .obsidianGlass) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
                Text("观察者询问 (Observe Voice)")
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)

                Text("世界询问与语音功能尚未开放；当前仅展示观察界面示例。")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)

                ListeningRingView(state: .idle)
                    .disabled(true)
                    .frame(maxWidth: .infinity)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: - 系统设置

    @ViewBuilder
    private var settingsContent: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
            HStack(spacing: DesignTokens.Spacing.sm) {
                WOMIcon(system: .settings, size: .prominent)
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)
                Text("系统设置与四库物理隔离监视 (Engine & Storage HUD)")
                    .font(Font.Mystic.titleMedium)
                    .foregroundStyle(Color.Mystic.textGoldAccent)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Text("四库容量与健康度只在 Local Engine 探针可达时呈现；探针不可达时一律显示「未接入」，不提供推测值。")
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 240), spacing: DesignTokens.Spacing.md)],
                spacing: DesignTokens.Spacing.md
            ) {
                ForEach(DatabaseRole.allCases) { role in
                    DatabaseStatusHUDCard(role: role)
                }
            }
        }
    }

    // MARK: - 规划中模块

    /// 规划中入口的落地页：说明该模块要解决的问题与已确定的能力边界，
    /// 而不是把工程自述丢给终端用户。
    @ViewBuilder
    private var plannedModuleBlueprint: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.lg) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                // 场景页头已经承担图标与标题的入口页，只补状态徽章：
                // 同一个模块名在首屏出现两次会把页头降级成装饰。
                if WOMSceneArtworkRegistry.scene(for: currentNavigation) == nil {
                    plannedModuleIdentityRow
                } else {
                    plannedModuleStatusBadge
                }

                Text(ModuleBlueprintCatalog.purpose(for: currentNavigation))
                    .font(Font.Mystic.bodyLarge)
                    .foregroundStyle(Color.Mystic.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            VictorianCard(style: .obsidianGlass) {
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
                    Text("已确定的能力边界 (Planned Scope)")
                        .font(Font.Mystic.titleSmall)
                        .foregroundStyle(Color.Mystic.brassGoldPrimary)

                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                        ForEach(
                            ModuleBlueprintCatalog.capabilities(for: currentNavigation),
                            id: \.self
                        ) { capability in
                            HStack(alignment: .top, spacing: DesignTokens.Spacing.sm) {
                                Rectangle()
                                    .fill(Color.Mystic.brassGoldMuted)
                                    .frame(width: 5, height: 5)
                                    .rotationEffect(.degrees(45))
                                    .padding(.top, 6)
                                    .accessibilityHidden(true)

                                Text(capability)
                                    .font(Font.Mystic.bodyMedium)
                                    .foregroundStyle(Color.Mystic.textSecondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
            }

            VictorianCard(style: .brassFramed) {
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
                    Text("当前可查看")
                        .font(Font.Mystic.titleSmall)
                        .foregroundStyle(Color.Mystic.brassGoldPrimary)

                    Text("命运干预与世界观察当前展示示例内容；系统连接状态来自实际探测，业务功能尚未开放。")
                        .font(Font.Mystic.bodyMedium)
                        .foregroundStyle(Color.Mystic.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)

                    Button("前往命运干预") {
                        currentNavigation = .fate
                    }
                    .buttonStyle(WOMButtonStyle(.secondary))
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    /// 未挂场景页头的规划页保留完整的图标 + 标题行。
    private var plannedModuleIdentityRow: some View {
        HStack(spacing: DesignTokens.Spacing.sm) {
            WOMIcon(
                source: currentNavigation.iconSource,
                size: .prominent,
                accessibilityLabel: currentNavigation.localizedTitle
            )
            .foregroundStyle(Color.Mystic.brassGoldPrimary)

            Text(currentNavigation.localizedTitle)
                .font(Font.Mystic.titleMedium)
                .foregroundStyle(Color.Mystic.textGoldAccent)
                .fixedSize(horizontal: false, vertical: true)

            plannedModuleStatusBadge
        }
    }

    private var plannedModuleStatusBadge: some View {
        Text("规划中")
            .font(Font.Mystic.caption)
            .foregroundStyle(Color.Mystic.parchmentInk)
            .padding(.horizontal, DesignTokens.LayoutInsets.badgePaddingHorizontal)
            .padding(.vertical, DesignTokens.LayoutInsets.badgePaddingVertical)
            .background(Capsule().fill(Color.Mystic.parchmentCard))
    }
}

/// 规划中模块的说明文本来源（对齐 `docs/05_UI/UI_交互基线_v1.0.md`）。
enum ModuleBlueprintCatalog {
    static func purpose(for item: NavigationItem) -> String {
        switch item {
        case .character: "查看一个持续存在的人，而不是一张 NPC 属性面板。"
        case .storyBook: "已完成的 Episode 沉淀为私人历史，可回看而不被重新编造。"
        case .cards: "卡牌是世界认知与遭遇记录，不是抽卡系统。"
        case .worldline: "1349 正典主轴与显式登记的世界线分叉。"
        case .notes: "管理非凡侦探线索、调查证据与灵摆占卜。"
        case .world, .fate, .gallery, .settings: "可查看界面与组件示例，业务能力以实际引擎状态为准。"
        }
    }

    static func capabilities(for item: NavigationItem) -> [String] {
        switch item {
        case .character:
            [
                "身份、当前状态与所在位置",
                "途径与序列（严格限制在用户已知范围内）",
                "关系、重要经历与传记片段",
                "已揭示的卡牌状态",
                "语音对话入口",
            ]
        case .storyBook:
            [
                "章节与叙事块，来自已提交的 NarrativeBlock",
                "关键干预记录与由此产生的世界变化",
                "已揭示知识与未解线索",
                "原声回放",
            ]
        case .cards:
            [
                "发现程度递进：未知 → 剪影 → 已辨识 → 部分揭示 → 完整传记",
                "卡牌详情：途径、序列与六维语义",
                "卡牌馆陈列与检索",
            ]
        case .worldline:
            [
                "1349 正典主轴时间盘",
                "世界线分叉的显式登记与隔离",
                "分叉差异对照",
            ]
        case .notes:
            [
                "案件线索钉板与暗红丝线拓扑关联",
                "钢笔手写笔记与未解线索列表",
                "灵摆占卜浮层",
                "以语音推演或追加调查日志",
            ]
        case .world, .fate, .gallery, .settings:
            []
        }
    }
}

#Preview {
    ContentView()
        .environment(AppState())
}
