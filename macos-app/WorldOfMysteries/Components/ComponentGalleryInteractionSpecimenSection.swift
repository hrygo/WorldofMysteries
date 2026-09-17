import SwiftUI

struct InteractionAndTypographyGallerySection: View {
    @State private var isSelected = true
    @State private var clickCount = 0

    var body: some View {
        ComponentGallerySection(title: "09 · 统一交互规范与排版标尺 (UX & Typography Specimen)") {
            VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
                interactionStates
                typographySpecimen
            }
        }
    }

    private var interactionStates: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("交互状态展示 (Interaction States)：")
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)

            HStack(spacing: DesignTokens.LayoutInsets.stackSpacingMd) {
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
