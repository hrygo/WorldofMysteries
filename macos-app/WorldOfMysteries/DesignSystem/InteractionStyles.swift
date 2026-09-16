import SwiftUI

// MARK: - 统一交互样式与 UX 反馈体系 (Unified Interaction & UX Styles)

/// 维多利亚暗金微物理按下反馈 ButtonStyle
/// 实现轻微内缩 (Scale 0.98) 与平滑阻尼回弹，杜绝生硬跳变
public struct MysticPressableButtonStyle: ButtonStyle, Sendable {
    public let scale: CGFloat
    public let pressedOpacity: Double
    public let animation: Animation
    
    public init(
        scale: CGFloat = DesignTokens.Interaction.pressedScale,
        pressedOpacity: Double = DesignTokens.Interaction.pressedOpacity,
        animation: Animation = DesignTokens.Interaction.clickSpring
    ) {
        self.scale = scale
        self.pressedOpacity = pressedOpacity
        self.animation = animation
    }
    
    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed ? scale : 1.0)
            .opacity(configuration.isPressed ? pressedOpacity : 1.0)
            .animation(animation, value: configuration.isPressed)
    }
}

/// 卡片级选中高光与悬停微光修饰器
public struct MysticCardSelectionModifier: ViewModifier {
    public let isSelected: Bool
    public let isHovered: Bool
    public let cornerRadius: CGFloat
    
    public init(
        isSelected: Bool,
        isHovered: Bool = false,
        cornerRadius: CGFloat = DesignTokens.Radii.md
    ) {
        self.isSelected = isSelected
        self.isHovered = isHovered
        self.cornerRadius = cornerRadius
    }
    
    public func body(content: Content) -> some View {
        content
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(
                        isSelected
                            ? Color.Mystic.brassGoldPrimary
                            : (isHovered ? Color.Mystic.brassGoldHover.opacity(DesignTokens.Interaction.hoverBorderOpacity) : Color.clear),
                        lineWidth: isSelected ? DesignTokens.Interaction.selectedBorderWidth : DesignTokens.Borders.hairline
                    )
            )
            .shadow(
                color: isSelected
                    ? Color.Mystic.brassGoldPrimary.opacity(DesignTokens.Interaction.selectedGlowOpacity)
                    : (isHovered ? Color.Mystic.brassGoldGlow.opacity(0.15) : Color.clear),
                radius: isSelected ? DesignTokens.Interaction.selectedShadowRadius : 2
            )
            .animation(DesignTokens.Interaction.selectionSpring, value: isSelected)
            .animation(DesignTokens.Interaction.hoverAnimation, value: isHovered)
    }
}

/// 列表项与菜单行选中、悬停与左侧指示柱修饰器
public struct MysticRowItemModifier: ViewModifier {
    public let isSelected: Bool
    public let isHovered: Bool
    public let cornerRadius: CGFloat
    public let showsLeadingIndicator: Bool
    
    public init(
        isSelected: Bool,
        isHovered: Bool = false,
        cornerRadius: CGFloat = DesignTokens.Radii.sm,
        showsLeadingIndicator: Bool = true
    ) {
        self.isSelected = isSelected
        self.isHovered = isHovered
        self.cornerRadius = cornerRadius
        self.showsLeadingIndicator = showsLeadingIndicator
    }
    
    public func body(content: Content) -> some View {
        HStack(spacing: 0) {
            if showsLeadingIndicator {
                RoundedRectangle(cornerRadius: 1.5)
                    .fill(isSelected ? Color.Mystic.brassGoldPrimary : Color.clear)
                    .frame(width: 3, height: 16)
                    .shadow(
                        color: isSelected ? Color.Mystic.brassGoldPrimary.opacity(0.6) : .clear,
                        radius: 4
                    )
                    .padding(.trailing, DesignTokens.Spacing.sm)
            }
            
            content
        }
        .padding(.horizontal, DesignTokens.LayoutInsets.rowPaddingHorizontal)
        .padding(.vertical, DesignTokens.LayoutInsets.rowPaddingVertical)
        .background(
            RoundedRectangle(cornerRadius: cornerRadius)
                .fill(
                    isSelected
                        ? Color.Mystic.obsidianCard
                        : (isHovered ? Color.Mystic.obsidianCard.opacity(0.6) : Color.clear)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: cornerRadius)
                        .stroke(
                            isSelected
                                ? Color.Mystic.brassGoldBorder.opacity(0.8)
                                : (isHovered ? Color.Mystic.brassGoldBorder.opacity(DesignTokens.Interaction.hoverBorderOpacity) : Color.clear),
                            lineWidth: DesignTokens.Borders.hairline
                        )
                )
        )
        .animation(DesignTokens.Interaction.selectionSpring, value: isSelected)
        .animation(DesignTokens.Interaction.hoverAnimation, value: isHovered)
    }
}

// MARK: - View 扩展便捷语法糖

public extension View {
    /// 应用统一的维多利亚暗金点击按压反馈
    func mysticPressable(
        scale: CGFloat = DesignTokens.Interaction.pressedScale,
        pressedOpacity: Double = DesignTokens.Interaction.pressedOpacity
    ) -> some View {
        self.buttonStyle(MysticPressableButtonStyle(scale: scale, pressedOpacity: pressedOpacity))
    }
    
    /// 应用统一的卡片选中高光与悬停微光修饰
    func mysticCardSelection(
        isSelected: Bool,
        isHovered: Bool = false,
        cornerRadius: CGFloat = DesignTokens.Radii.md
    ) -> some View {
        self.modifier(MysticCardSelectionModifier(
            isSelected: isSelected,
            isHovered: isHovered,
            cornerRadius: cornerRadius
        ))
    }
    
    /// 应用统一的列表行项交互修饰
    func mysticRowItem(
        isSelected: Bool,
        isHovered: Bool = false,
        cornerRadius: CGFloat = DesignTokens.Radii.sm,
        showsLeadingIndicator: Bool = true
    ) -> some View {
        self.modifier(MysticRowItemModifier(
            isSelected: isSelected,
            isHovered: isHovered,
            cornerRadius: cornerRadius,
            showsLeadingIndicator: showsLeadingIndicator
        ))
    }
    
    /// 统一叙事正文文本排版（带标准行距 6.0 与舒适行距）
    func mysticNarrativeStyle() -> some View {
        self
            .font(Font.Mystic.narrativeSubtitle)
            .lineSpacing(DesignTokens.TypographyMetrics.narrativeLineSpacing)
            .tracking(DesignTokens.TypographyMetrics.titleTracking)
            .foregroundStyle(Color.Mystic.textPrimary)
    }
    
    /// 统一标题文本排版
    func mysticTitleStyle(font: Font = Font.Mystic.titleMedium, color: Color = Color.Mystic.textPrimary) -> some View {
        self
            .font(font)
            .lineSpacing(DesignTokens.TypographyMetrics.titleLineSpacing)
            .tracking(DesignTokens.TypographyMetrics.titleTracking)
            .foregroundStyle(color)
    }
    
    /// 统一紧凑标注文本排版
    func mysticCaptionStyle(color: Color = Color.Mystic.textSecondary) -> some View {
        self
            .font(Font.Mystic.caption)
            .lineSpacing(DesignTokens.TypographyMetrics.compactLineSpacing)
            .tracking(DesignTokens.TypographyMetrics.captionTracking)
            .foregroundStyle(color)
    }
}
