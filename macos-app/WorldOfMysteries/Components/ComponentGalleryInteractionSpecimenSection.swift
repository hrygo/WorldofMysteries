import SwiftUI

struct InteractionAndTypographyGallerySection: View {
    @State private var isSelected = true
    @State private var clickCount = 0
    @State private var lastControlAction = "尚未触发"
    @State private var controlActionCount = 0

    var body: some View {
        ComponentGallerySection(title: "09 · 统一交互规范与排版标尺 (UX & Typography Specimen)") {
            VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
                HStack {
                    Text("交互实验台可重复验证选择、按压、按钮与长文本压力状态。")
                        .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                    Spacer(minLength: DesignTokens.Spacing.sm)
                    Button("重置 UX 样例") {
                        isSelected = true
                        clickCount = 0
                        lastControlAction = "尚未触发"
                        controlActionCount = 0
                    }
                    .buttonStyle(WOMButtonStyle(.secondary))
                }

                interactionStates
                controlAndIconSpecimen
                compactControlStressSpecimen
                typographySpecimen
            }
        }
    }

    private var interactionStates: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("交互状态展示 (Interaction States)：")
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)

            LazyVGrid(
                columns: [
                    GridItem(
                        .adaptive(minimum: 190, maximum: 300),
                        spacing: DesignTokens.LayoutInsets.stackSpacingMd
                    )
                ],
                alignment: .leading,
                spacing: DesignTokens.LayoutInsets.stackSpacingMd
            ) {
                defaultStateCard
                selectableStateCard
                pressFeedbackCard
            }
        }
    }

    private var defaultStateCard: some View {
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
    }

    private var selectableStateCard: some View {
        Button {
            withAnimation(DesignTokens.Interaction.selectionSpring) {
                isSelected.toggle()
            }
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(isSelected ? "已选中 (Selected)" : "未选中 (Unselected)")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(
                            isSelected ? Color.Mystic.brassGoldPrimary : Color.Mystic.textTertiary)
                    Spacer()
                    Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: 11))
                        .foregroundStyle(
                            isSelected ? Color.Mystic.brassGoldPrimary : Color.Mystic.textTertiary)
                }
                Text("1.5pt 暗金边框 · 6pt 呼吸微光 (点击切换)")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textPrimary)
            }
            .padding(DesignTokens.LayoutInsets.compactCardPadding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.Mystic.obsidianCard)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
            .mysticCardSelection(isSelected: isSelected, isHovered: false)
        }
        .mysticPressable()
    }

    private var pressFeedbackCard: some View {
        Button {
            clickCount += 1
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text("点击微物理反馈")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(Color.Mystic.statusOnline)
                    Spacer()
                    Text("x\(clickCount)")
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

    private var controlAndIconSpecimen: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("系统按钮与图标标尺 (Controls & Icons)：")
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)

            LazyVGrid(
                columns: [
                    GridItem(
                        .adaptive(minimum: 112, maximum: 180),
                        spacing: DesignTokens.Spacing.sm
                    )
                ],
                alignment: .leading,
                spacing: DesignTokens.Spacing.sm
            ) {
                specimenButton("主行动", icon: .add, variant: .primary)
                specimenButton("次行动", icon: .edit, variant: .secondary)
                specimenButton("仪式", icon: .favorite, variant: .ritual)
                specimenButton("危险", icon: .remove, variant: .danger)

                specimenButton("Disabled", icon: .close, variant: .secondary)
                    .disabled(true)
            }

            ViewThatFits(in: .horizontal) {
                HStack(spacing: DesignTokens.Spacing.md) {
                    iconSizeSamples
                    Spacer(minLength: DesignTokens.Spacing.sm)
                    toolbarControls
                }

                VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                    iconSizeSamples
                    toolbarControls
                }
            }

            MysticKeyValueRow(
                key: "最近交互",
                value: "\(lastControlAction) · \(controlActionCount) 次",
                tone: controlActionCount == 0 ? .neutral : .teal,
                systemIcon: "cursorarrow.click"
            )
        }
    }

    private var iconSizeSamples: some View {
        HStack(spacing: DesignTokens.Spacing.md) {
            iconSizeSpecimen("16", size: .compact)
            iconSizeSpecimen("20", size: .standard)
            iconSizeSpecimen("24", size: .prominent)
            iconSizeSpecimen("32", size: .large)
        }
    }

    private var toolbarControls: some View {
        HStack(spacing: DesignTokens.Spacing.sm) {
            Button {
                recordControlAction("搜索")
            } label: {
                WOMIcon(system: .search, size: .compact, accessibilityLabel: "搜索")
            }
            .buttonStyle(WOMIconButtonStyle(.secondary))
            .help("搜索")

            Button {
                recordControlAction("设置")
            } label: {
                WOMIcon(system: .settings, size: .compact, accessibilityLabel: "设置")
            }
            .buttonStyle(WOMToolbarButtonStyle(.tertiary))
            .help("设置")
        }
    }

    private var compactControlStressSpecimen: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("紧凑控件压力样例 (Compact Control Stress)：")
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)

            ViewThatFits(in: .horizontal) {
                HStack(spacing: DesignTokens.Spacing.sm) {
                    specimenButton(
                        "提交给当前世界线中的角色进行独立判断",
                        icon: .add,
                        variant: .primary
                    )
                    specimenButton(
                        "Review the full intervention evidence before continuing",
                        icon: .search,
                        variant: .secondary
                    )
                }

                VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                    specimenButton(
                        "提交给当前世界线中的角色进行独立判断",
                        icon: .add,
                        variant: .primary
                    )
                    specimenButton(
                        "Review the full intervention evidence before continuing",
                        icon: .search,
                        variant: .secondary
                    )
                }
            }

            HStack(spacing: DesignTokens.Spacing.sm) {
                MysticBadge("正典锁定", tone: .gold, systemIcon: "lock.fill")
                MysticBadge(
                    "高风险",
                    tone: .crimson,
                    variant: .panel,
                    systemIcon: "exclamationmark.octagon.fill",
                    isEmphasized: true
                )
                MysticStatusDot(tone: .amber, isPulsing: true, label: "等待确认")
            }

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                Text("临界状态计量条")
                    .mysticCaptionStyle(color: Color.Mystic.textTertiary)
                MysticMetricBar(
                    value: 0.18,
                    tone: .teal,
                    criticalThreshold: 0.25,
                    label: "灵性安全阈值"
                )
            }
            .frame(maxWidth: 360)
        }
        .padding(DesignTokens.LayoutInsets.compactCardPadding)
        .background(Color.Mystic.obsidianElevated)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
                .stroke(Color.Mystic.brassGoldBorder.opacity(0.45), lineWidth: DesignTokens.Borders.hairline)
        )
    }

    private func specimenButton(
        _ title: String,
        icon: WOMSystemIcon,
        variant: WOMButtonVariant
    ) -> some View {
        Button {
            recordControlAction(title)
        } label: {
            HStack(spacing: DesignTokens.Spacing.xs) {
                WOMIcon(system: icon, size: .compact)
                Text(title)
                    .font(Font.Mystic.caption)
                    .fontWeight(.semibold)
            }
        }
        .buttonStyle(WOMButtonStyle(variant))
    }

    private func iconSizeSpecimen(_ label: String, size: WOMIconSize) -> some View {
        VStack(spacing: DesignTokens.Spacing.xxs) {
            WOMIcon(system: .search, size: size)
                .foregroundStyle(Color.Mystic.textPrimary)
            Text(label)
                .font(Font.Mystic.monoBadge)
                .foregroundStyle(Color.Mystic.textTertiary)
        }
        .frame(width: 44)
    }

    private var typographySpecimen: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("排版度量衡标尺 (Typography Rhythm & Kerning)：")
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                Text("古典巨幕 (32pt 衬线 / Tracking +0.6pt / 严谨行距)")
                    .font(Font.Mystic.gothicDisplay)
                    .tracking(DesignTokens.TypographyMetrics.gothicDisplayTracking)
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)

                Text(
                    "沉浸叙事对白 (16pt 衬线 / 行间距 6.0pt / Tracking +0.25pt)：\n“我们在黑暗中守护光明，却也必须时刻警惕来自虚空的凝视。不属于这个时代的愚者，正在灰雾之上默默注视着命运轮转。”"
                )
                .mysticNarrativeStyle()

                Text("侦探草写便签 (14pt 楷体 / 行间距 5.0pt)：\n明斯克街15号夏洛克·莫里亚蒂侦探亲笔 —— 追查绝密赫密斯语手稿。")
                    .font(Font.Mystic.parchmentCursive)
                    .lineSpacing(DesignTokens.TypographyMetrics.parchmentLineSpacing)
                    .foregroundStyle(Color.Mystic.brassGoldMuted)

                ViewThatFits(in: .horizontal) {
                    HStack(spacing: DesignTokens.Spacing.lg) {
                        typographyMetadataSamples
                    }

                    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                        typographyMetadataSamples
                    }
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

    @ViewBuilder
    private var typographyMetadataSamples: some View {
        Text("机械等宽徽标 (Tracking +0.4pt): [SEQ-9-SEER-001]")
            .font(Font.Mystic.monoBadge)
            .tracking(DesignTokens.TypographyMetrics.monoTracking)
            .foregroundStyle(Color.Mystic.statusOnline)

        Text("紧凑元数据 (行间距 2.0pt / Tracking +0.2pt)")
            .mysticCaptionStyle(color: Color.Mystic.textTertiary)
    }

    private func recordControlAction(_ title: String) {
        lastControlAction = title
        controlActionCount += 1
    }
}
