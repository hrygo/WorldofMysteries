import SwiftUI

/// Visual regression and design-system showcase for the World of Mysteries visual asset stack.
struct VisualSystemGallerySection: View {
    @State private var isCardHovered = false
    @FocusState private var accessibilityFocus: AccessibilityFocusTarget?

    private enum AccessibilityFocusTarget: Hashable {
        case primaryButton
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
            }
        }
    }

    private var customIconGrid: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("世界观矢量资产")
                .womSectionHeaderStyle()

            LazyVGrid(
                columns: Array(
                    repeating: GridItem(.fixed(74), spacing: DesignTokens.Spacing.sm),
                    count: 6
                ),
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
                    .frame(width: 70, height: 58)
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
        HStack(alignment: .top, spacing: DesignTokens.Spacing.xl) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                Text("平台行为")
                    .womSectionHeaderStyle()

                HStack(spacing: DesignTokens.Spacing.md) {
                    ForEach(WOMSystemIcon.allCases, id: \.rawValue) { icon in
                        WOMIcon(system: icon, size: .standard, accessibilityLabel: icon.rawValue)
                            .foregroundStyle(Color.Mystic.textPrimary)
                            .frame(width: 28, height: 28)
                    }
                }
            }

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                Text("状态语义")
                    .womSectionHeaderStyle()

                HStack(spacing: DesignTokens.Spacing.md) {
                    ForEach(WOMStatusIcon.allCases, id: \.rawValue) { icon in
                        WOMIcon(status: icon, size: .standard, accessibilityLabel: icon.rawValue)
                            .foregroundStyle(statusColor(icon))
                            .frame(width: 28, height: 28)
                    }
                }
            }
        }
    }

    private var buttonVariants: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("按钮语义与密度")
                .womSectionHeaderStyle()

            HStack(spacing: DesignTokens.Spacing.sm) {
                Button("主操作") {}
                    .buttonStyle(WOMButtonStyle(.primary))
                Button("次操作") {}
                    .buttonStyle(WOMButtonStyle(.secondary))
                Button("低干扰") {}
                    .buttonStyle(WOMButtonStyle(.tertiary))
                Button("危险") {}
                    .buttonStyle(WOMButtonStyle(.danger))
                Button("仪式") {}
                    .buttonStyle(WOMButtonStyle(.ritual))

                Button {} label: {
                    WOMIcon(system: .more, size: .standard, accessibilityLabel: "更多")
                }
                .buttonStyle(WOMIconButtonStyle())

                Button {} label: {
                    WOMIcon(system: .search, size: .compact, accessibilityLabel: "搜索")
                }
                .buttonStyle(WOMToolbarButtonStyle())
            }
        }
    }

    private var surfaceSamples: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("Surface + Texture")
                .womSectionHeaderStyle()

            HStack(spacing: DesignTokens.Spacing.md) {
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

            HStack(alignment: .top, spacing: DesignTokens.Spacing.sm) {
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
                ) {}
            }

            HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
                WOMLoadingState(
                    title: "正在同步世界状态",
                    message: "等待 Local Engine 返回最新已提交事实。",
                    source: .asset(.grayFog),
                    tone: .info
                )
                .frame(maxWidth: 320)

                WOMEmptyState(
                    source: .asset(.clue),
                    title: "尚无线索",
                    message: "当真实调查数据产生后，线索会在这里按世界状态呈现。",
                    tone: .info,
                    actionTitle: "返回世界"
                ) {}
                .frame(maxWidth: 320)
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

            HStack(spacing: DesignTokens.Spacing.sm) {
                Button("键盘焦点目标") {}
                    .buttonStyle(WOMButtonStyle(.primary))
                    .focused($accessibilityFocus, equals: .primaryButton)

                Button("聚焦主按钮") {
                    accessibilityFocus = .primaryButton
                }
                .buttonStyle(WOMButtonStyle(.secondary))

                Button("禁用操作") {}
                    .buttonStyle(WOMButtonStyle(.secondary))
                    .disabled(true)

                Button("危险操作") {}
                    .buttonStyle(WOMButtonStyle(.danger))

                Button("仪式操作") {}
                    .buttonStyle(WOMButtonStyle(.ritual))
            }

            HStack(spacing: DesignTokens.Spacing.md) {
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
        .frame(width: 150)
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
        .frame(
            minWidth: 260,
            maxWidth: 260,
            minHeight: 86,
            alignment: .leading
        )
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
                .font(.system(size: 9, design: .monospaced))
                .foregroundStyle(
                    tone == .parchment
                        ? Color.Mystic.parchmentInkSecondary
                        : Color.Mystic.textTertiary
                )
        }
        .padding(DesignTokens.LayoutInsets.compactCardPadding)
        .frame(width: 126, height: 72, alignment: .leading)
        .background(
            WOMPanelBackground(
                tone: tone,
                cornerRadius: DesignTokens.Radii.sm,
                texture: texture,
                textureOpacity: 0.08
            )
        )
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
        case .locked:
            Color.Mystic.textSecondary
        case .active:
            Color.Mystic.brassGoldPrimary
        case .cooldown:
            Color.Mystic.spiritualBlue
        }
    }
}
