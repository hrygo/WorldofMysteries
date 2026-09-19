import SwiftUI

/// Visual regression and design-system showcase for the World of Mysteries visual asset stack.
struct VisualSystemGallerySection: View {
    @State private var isCardHovered = false
    @State private var lastVisualAction = "尚未触发"
    @State private var visualActionCount = 0
    @State private var advancedMode: AdvancedMode = .overview
    @FocusState private var accessibilityFocus: AccessibilityFocusTarget?

    private enum AccessibilityFocusTarget: Hashable {
        case primaryButton
    }

    private enum AdvancedMode: Hashable {
        case overview
        case evidence
        case ritual
    }

    var body: some View {
        ComponentGallerySection(title: "11 · 视觉资产系统 (Visual Asset System)") {
            VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
                customIconGrid
                WOMDividerOrnament()
                platformIconRows
                WOMDividerOrnament()
                buttonVariants
                WOMDividerOrnament()
                surfaceSamples
                WOMDividerOrnament()
                overlayFeedbackSamples
                WOMDividerOrnament()
                accessibilitySamples
                WOMDividerOrnament()
                advancedInteractionSamples
                WOMDividerOrnament()
                visualQAStressSamples
            }
        }
    }

    private var customIconGrid: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("世界观矢量资产")
                .womSectionHeaderStyle()

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 70, maximum: 84), spacing: DesignTokens.Spacing.sm)],
                alignment: .leading,
                spacing: DesignTokens.Spacing.sm
            ) {
                ForEach(WOMIconAsset.allCases, id: \.rawValue) { asset in
                    VStack(spacing: DesignTokens.Spacing.xs) {
                        WOMIcon(asset, size: .prominent)
                            .foregroundStyle(Color.Mystic.brassGoldPrimary)

                        Text(assetLabel(asset.rawValue))
                            .font(Font.Mystic.caption)
                            .foregroundStyle(Color.Mystic.textSecondary)
                            .lineLimit(1)
                    }
                    .frame(maxWidth: .infinity, minHeight: 58)
                    .background(
                        WOMPanelBackground(
                            tone: .card,
                            cornerRadius: DesignTokens.Radii.sm
                        )
                    )
                }
            }
        }
    }

    private var platformIconRows: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
            iconGrid(
                title: "平台行为",
                items: WOMSystemIcon.allCases.map { icon in
                    (icon.rawValue, WOMIconSource.system(icon), Color.Mystic.textPrimary)
                }
            )

            iconGrid(
                title: "状态语义",
                items: WOMStatusIcon.allCases.map { icon in
                    (icon.rawValue, WOMIconSource.status(icon), statusColor(icon))
                }
            )
        }
    }

    private func iconGrid(
        title: String,
        items: [(String, WOMIconSource, Color)]
    ) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text(title)
                .womSectionHeaderStyle()

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 34, maximum: 42), spacing: DesignTokens.Spacing.sm)],
                alignment: .leading,
                spacing: DesignTokens.Spacing.sm
            ) {
                ForEach(items, id: \.0) { item in
                    WOMIcon(source: item.1, size: .standard, accessibilityLabel: item.0)
                        .foregroundStyle(item.2)
                        .frame(width: 32, height: 32)
                }
            }
        }
    }

    private var buttonVariants: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("按钮语义与密度")
                .womSectionHeaderStyle()

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 108, maximum: 150), spacing: DesignTokens.Spacing.sm)],
                alignment: .leading,
                spacing: DesignTokens.Spacing.sm
            ) {
                Button("主操作") { recordVisualAction("主操作") }
                    .buttonStyle(WOMButtonStyle(.primary))
                Button("次操作") { recordVisualAction("次操作") }
                    .buttonStyle(WOMButtonStyle(.secondary))
                Button("低干扰") { recordVisualAction("低干扰") }
                    .buttonStyle(WOMButtonStyle(.tertiary))
                Button("危险") { recordVisualAction("危险") }
                    .buttonStyle(WOMButtonStyle(.danger))
                Button("仪式") { recordVisualAction("仪式") }
                    .buttonStyle(WOMButtonStyle(.ritual))

                Button {
                    recordVisualAction("更多")
                } label: {
                    WOMIcon(system: .more, size: .standard, accessibilityLabel: "更多")
                }
                .buttonStyle(WOMIconButtonStyle())

                Button {
                    recordVisualAction("搜索")
                } label: {
                    WOMIcon(system: .search, size: .compact, accessibilityLabel: "搜索")
                }
                .buttonStyle(WOMToolbarButtonStyle())
            }

            MysticKeyValueRow(
                key: "最近操作",
                value: "\(lastVisualAction) · \(visualActionCount) 次",
                tone: visualActionCount == 0 ? .neutral : .teal,
                systemIcon: "cursorarrow.click"
            )
        }
    }

    private var surfaceSamples: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("Surface + Texture")
                .womSectionHeaderStyle()

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 126, maximum: 160), spacing: DesignTokens.Spacing.md)],
                alignment: .leading,
                spacing: DesignTokens.Spacing.md
            ) {
                surfaceSample("Panel", tone: .panel, texture: .sacredSlate)
                surfaceSample("Card", tone: .card, texture: .velvet)
                surfaceSample("Floating", tone: .floating, texture: .foolVeil)
                surfaceSample("Ritual", tone: .ritual, texture: .foolVeil)
                surfaceSample("Codex", tone: .parchment, texture: .parchment)
            }

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                Label("Hover / selection chrome", systemImage: "sparkles")
                    .foregroundStyle(Color.Mystic.textPrimary)
                Text("该卡片验证 CardChrome 的 hover 边框与微光。")
                    .mysticCaptionStyle()
            }
            .padding(DesignTokens.LayoutInsets.compactCardPadding)
            .womCardChrome(
                tone: .card,
                texture: .gold,
                isSelected: false,
                isHovered: isCardHovered
            )
            .onHover { isCardHovered = $0 }
        }
    }

    private var overlayFeedbackSamples: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
            Text("Overlay / Feedback Chrome")
                .womSectionHeaderStyle()

            Text("以下只展示内容 chrome；真实 Sheet / Popover / Inspector 的生命周期仍由 SwiftUI 系统 API 管理。")
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 150, maximum: 210), spacing: DesignTokens.Spacing.sm)],
                alignment: .leading,
                spacing: DesignTokens.Spacing.sm
            ) {
                overlaySample("Inspector", role: .inspector)
                overlaySample("Popover", role: .popover)
                overlaySample("Sheet", role: .sheet)
                overlaySample("HUD", role: .hud)
            }

            VStack(spacing: DesignTokens.Spacing.xs) {
                WOMStatusBanner(
                    tone: .info,
                    title: "世界状态已刷新",
                    message: "新的已提交世界事实可用于后续叙事。"
                )
                WOMStatusBanner(
                    tone: .success,
                    title: "本地引擎已连接",
                    message: "IPC 通道与状态同步均可用。"
                )
                WOMStatusBanner(
                    tone: .warning,
                    title: "上下文接近预算",
                    message: "后续请求将优先收敛到当前场景所需事实。"
                )
                WOMStatusBanner(
                    tone: .danger,
                    title: "提交被拒绝",
                    message: "领域约束未通过，世界事实没有写入。",
                    actionTitle: "查看原因"
                ) { recordVisualAction("查看拒绝原因") }
            }

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 260, maximum: 340), spacing: DesignTokens.Spacing.md)],
                alignment: .leading,
                spacing: DesignTokens.Spacing.md
            ) {
                WOMLoadingState(
                    title: "正在同步世界状态",
                    message: "等待 Local Engine 返回最新已提交事实。",
                    source: .asset(.grayFog),
                    tone: .info
                )

                WOMEmptyState(
                    source: .asset(.clue),
                    title: "尚无线索",
                    message: "当真实调查数据产生后，线索会在这里按世界状态呈现。",
                    tone: .info,
                    actionTitle: "返回世界"
                ) { recordVisualAction("返回世界") }
            }
        }
    }

    private var accessibilitySamples: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("辅助功能状态 · Accessibility States")
                .womSectionHeaderStyle()

            Text("使用 Tab/Shift-Tab 检查键盘焦点；并可在系统辅助功能中切换增强对比度、不使用颜色进行区分、减少动态效果和降低透明度，观察本区域的实时退化与增强效果。")
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 120, maximum: 170), spacing: DesignTokens.Spacing.sm)],
                alignment: .leading,
                spacing: DesignTokens.Spacing.sm
            ) {
                Button("键盘焦点目标") { recordVisualAction("键盘焦点目标") }
                    .buttonStyle(WOMButtonStyle(.primary))
                    .focused($accessibilityFocus, equals: .primaryButton)

                Button("聚焦主按钮") {
                    accessibilityFocus = .primaryButton
                }
                .buttonStyle(WOMButtonStyle(.secondary))

                Button("禁用操作") {}
                    .buttonStyle(WOMButtonStyle(.secondary))
                    .disabled(true)

                Button("危险操作") { recordVisualAction("辅助功能危险操作") }
                    .buttonStyle(WOMButtonStyle(.danger))

                Button("仪式操作") { recordVisualAction("辅助功能仪式操作") }
                    .buttonStyle(WOMButtonStyle(.ritual))
            }

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 240, maximum: 300), spacing: DesignTokens.Spacing.md)],
                alignment: .leading,
                spacing: DesignTokens.Spacing.md
            ) {
                accessibilityCard(
                    title: "Selected",
                    detail: "开启“不使用颜色进行区分”后，选中态增加第二层几何描边。",
                    selected: true
                )
                accessibilityCard(
                    title: "Unselected",
                    detail: "作为同组基准，验证 selected 不只依赖颜色差异。",
                    selected: false
                )
            }
        }
    }

    private var advancedInteractionSamples: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
            Text("Advanced Interaction / World-State Chrome")
                .womSectionHeaderStyle()

            Text("Segmented 使用原生 Picker 语义；关系、成就与冷却仅呈现外部世界状态，不在视觉组件内部制造领域事实、计时器或关系分数。")
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                Text("Adaptive Segmented Picker")
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.textPrimary)

                WOMAdaptiveSegmentedPicker(
                    "观察模式",
                    selection: $advancedMode,
                    options: advancedModeOptions
                )

                WOMAdaptiveSegmentedPicker(
                    "窄 Inspector 模式",
                    selection: $advancedMode,
                    options: advancedModeOptions
                )
                .frame(maxWidth: 220, alignment: .leading)

                Text("第二个样例限制宽度，用于确认 segmented 在空间不足时由系统 Picker 自动降级为 menu，而不是缩小文字或互相覆盖。")
                    .mysticCaptionStyle(color: Color.Mystic.textTertiary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(DesignTokens.LayoutInsets.compactCardPadding)
            .womCardChrome(
                tone: .card,
                texture: .sacredSlate,
                cornerRadius: DesignTokens.Radii.md
            )

            Text("Relationship")
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.textPrimary)

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 190, maximum: 300), spacing: DesignTokens.Spacing.sm)],
                alignment: .leading,
                spacing: DesignTokens.Spacing.sm
            ) {
                WOMRelationBadge("阿兹克·艾格斯", role: .trusted, detail: "长期可靠联系")
                WOMRelationBadge("值夜者小队", role: .aligned, detail: "当前目标一致")
                WOMRelationBadge("陌生调查对象", role: .neutral)
                WOMRelationBadge("身份不明的目击者", role: .wary, detail: "需要进一步验证")
                WOMRelationBadge(
                    "极光会高危目标 / Extremely long hostile entity label",
                    role: .hostile,
                    detail: "长标题压力：仍需保持清晰、换行和几何边界。"
                )
            }

            Text("Achievement / Discovery")
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.textPrimary)

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 230, maximum: 340), spacing: DesignTokens.Spacing.md)],
                alignment: .leading,
                spacing: DesignTokens.Spacing.md
            ) {
                WOMAchievementSeal(
                    title: "尚未触及的隐秘",
                    detail: "锁定状态也必须保持标题与说明可读。",
                    state: .locked
                )
                WOMAchievementSeal(
                    title: "发现：廷根地下查尼斯门",
                    detail: "发现态使用图标、边界与文字共同表达。",
                    state: .discovered,
                    systemImage: "eye.fill"
                )
                WOMAchievementSeal(
                    title: "完成：在极端长本地化标题下仍保持文字可读且布局不重叠的世界调查成就",
                    detail: "Completed state does not rely on gold alone.",
                    state: .completed
                )
            }

            Text("Cooldown / Availability")
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.textPrimary)

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 220, maximum: 320), spacing: DesignTokens.Spacing.md)],
                alignment: .leading,
                spacing: DesignTokens.Spacing.md
            ) {
                WOMCooldownIndicator("灵性占卜", state: .ready)
                WOMCooldownIndicator(
                    "灰雾仪式",
                    state: .cooling(progress: 0.38, remainingLabel: "剩余时间由 Runtime 提供 · 12s")
                )
                WOMCooldownIndicator(
                    "高位权柄调用",
                    state: .locked(reason: "当前世界状态未满足使用条件；视觉层不会自行解除锁定。")
                )
            }
        }
    }

    private var advancedModeOptions: [WOMSegmentedOption<AdvancedMode>] {
        [
            .init(value: .overview, title: "世界概览", systemImage: "rectangle.grid.1x2"),
            .init(value: .evidence, title: "调查证据与关系网络", systemImage: "doc.text.magnifyingglass"),
            .init(value: .ritual, title: "仪式与灵性状态", systemImage: "sparkles")
        ]
    }

    private var visualQAStressSamples: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
            Text("Visual QA Stress · 可读性与布局压力")
                .womSectionHeaderStyle()

            Text("用于人工检查长中英文、密集标签、最小内容宽度和长状态文案。窗口缩到应用最小宽度时，本区域不应出现文字互相覆盖、按钮遮挡或结构溢出。")
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 260, maximum: 360), spacing: DesignTokens.Spacing.md)],
                alignment: .leading,
                spacing: DesignTokens.Spacing.md
            ) {
                stressTextCard(
                    title: "超长中文标题压力：调查卷宗与世界状态在极端内容长度下仍应保持完整层级与清晰对齐",
                    detail: "这是用于验证多行标题、正文换行和底部操作区不会互相覆盖的压力文本。任何布局都不应依赖缩小字体来逃避空间不足。"
                )

                stressTextCard(
                    title: "Extremely long English heading for layout collision and baseline regression verification",
                    detail: "Long localized content must wrap predictably while keeping readable type sizes, consistent spacing, and a stable visual rhythm."
                )
            }

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 92, maximum: 150), spacing: DesignTokens.Spacing.xs)],
                alignment: .leading,
                spacing: DesignTokens.Spacing.xs
            ) {
                ForEach(
                    ["正典约束", "世界线隔离", "灵性高负载", "需要人工确认", "Long Metadata", "Awaiting Context"],
                    id: \.self
                ) { label in
                    MysticBadge(label, tone: .neutral, variant: .panel, isEmphasized: true)
                }
            }

            WOMStatusBanner(
                tone: .warning,
                title: "长状态文案压力测试",
                message: "当状态信息包含更长的中文说明、英文标识符与后续动作提示时，Banner 必须增长高度而不是覆盖右侧操作或将正文压缩到不可辨认的窄列。",
                actionTitle: "查看完整诊断"
            ) { recordVisualAction("查看完整诊断") }
        }
    }

    private func stressTextCard(title: String, detail: String) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text(title)
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.textPrimary)
                .fixedSize(horizontal: false, vertical: true)

            Text(detail)
                .font(Font.Mystic.bodyMedium)
                .foregroundStyle(Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)

            Button("保持标准字号的操作按钮") {
                recordVisualAction("压力样例操作")
            }
                .buttonStyle(WOMButtonStyle(.secondary))
        }
        .padding(DesignTokens.LayoutInsets.cardPadding)
        .womCardChrome(
            tone: .card,
            texture: .sacredSlate,
            cornerRadius: DesignTokens.Radii.md
        )
    }

    private func overlaySample(_ title: String, role: WOMOverlayRole) -> some View {
        WOMOverlayPanel(role: role) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                Text(title)
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.textPrimary)
                Text(role.rawValue)
                    .font(Font.Mystic.monoBadge)
                    .foregroundStyle(Color.Mystic.textTertiary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func accessibilityCard(
        title: String,
        detail: String,
        selected: Bool
    ) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            Text(title)
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.textPrimary)
            Text(detail)
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(DesignTokens.LayoutInsets.compactCardPadding)
        .frame(minHeight: 86, alignment: .leading)
        .womCardChrome(
            tone: .card,
            texture: .sacredSlate,
            isSelected: selected,
            cornerRadius: DesignTokens.Radii.md
        )
        .accessibilityElement(children: .combine)
        .accessibilityValue(selected ? "已选中" : "未选中")
    }

    private func surfaceSample(
        _ title: String,
        tone: WOMSurfaceTone,
        texture: WOMTextureAsset
    ) -> some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            Text(title)
                .font(Font.Mystic.caption)
                .foregroundStyle(
                    tone == .parchment
                        ? Color.Mystic.parchmentInk
                        : Color.Mystic.textPrimary
                )
            Text(texture.rawValue)
                .font(.system(size: 10, weight: .medium, design: .monospaced))
                .foregroundStyle(
                    tone == .parchment
                        ? Color.Mystic.parchmentInkSecondary
                        : Color.Mystic.textTertiary
                )
        }
        .padding(DesignTokens.LayoutInsets.compactCardPadding)
        .frame(maxWidth: .infinity, minHeight: 72, alignment: .leading)
        .background(
            WOMPanelBackground(
                tone: tone,
                cornerRadius: DesignTokens.Radii.sm,
                texture: texture,
                textureOpacity: 0.08
            )
        )
    }

    private func recordVisualAction(_ title: String) {
        lastVisualAction = title
        visualActionCount += 1
    }

    private func assetLabel(_ rawValue: String) -> String {
        rawValue
            .replacingOccurrences(of: "wom.icon.", with: "")
            .replacingOccurrences(of: "grayfog", with: "gray fog")
    }

    private func statusColor(_ icon: WOMStatusIcon) -> Color {
        switch icon {
        case .info:
            Color.Mystic.spiritualBlue
        case .warning:
            Color.Mystic.statusWarning
        case .success:
            Color.Mystic.statusOnline
        case .danger:
            Color.Mystic.statusDanger
        case .locked, .unknown, .concealed:
            Color.Mystic.textSecondary
        case .active:
            Color.Mystic.brassGoldPrimary
        case .cooldown:
            Color.Mystic.spiritualBlue
        }
    }
}
