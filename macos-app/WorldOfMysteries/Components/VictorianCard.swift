import SwiftUI

public enum VictorianCardStyle: Sendable {
    case obsidianGlass
    case parchment
    case brassFramed
}

/// 维多利亚暗金/羊皮纸通用容器卡片（遵循同心圆角法则）
public struct VictorianCard<Content: View>: View {
    public let style: VictorianCardStyle
    public let cornerRadius: CGFloat
    public let content: Content
    
    public init(
        style: VictorianCardStyle = .obsidianGlass,
        cornerRadius: CGFloat = DesignTokens.Radii.lg,
        @ViewBuilder content: () -> Content
    ) {
        self.style = style
        self.cornerRadius = cornerRadius
        self.content = content()
    }
    
    public var body: some View {
        content
            .padding(DesignTokens.Spacing.lg)
            .background(backgroundView)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
            .overlay(
                RoundedRectangle(cornerRadius: cornerRadius)
                    .stroke(borderStrokeColor, lineWidth: borderWidth)
            )
            .shadow(color: shadowColor, radius: shadowRadius, y: 3)
    }
    
    @ViewBuilder
    private var backgroundView: some View {
        switch style {
        case .obsidianGlass:
            Color.Mystic.obsidianGlass
        case .parchment:
            ZStack {
                Color.Mystic.parchmentBase
                
                if NSImage(named: "TextureParchment") != nil {
                    Image("TextureParchment")
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .blendMode(.multiply)
                        .opacity(0.88)
                }
            }
            .compositingGroup()
        case .brassFramed:
            Color.Mystic.obsidianCard
        }
    }
    
    private var borderStrokeColor: Color {
        switch style {
        case .obsidianGlass:
            return Color.Mystic.brassGoldBorder.opacity(0.4)
        case .parchment:
            return Color.Mystic.parchmentBorder
        case .brassFramed:
            return Color.Mystic.brassGoldPrimary
        }
    }
    
    private var borderWidth: CGFloat {
        switch style {
        case .obsidianGlass:
            return DesignTokens.Borders.hairline
        case .parchment:
            return DesignTokens.Borders.standard
        case .brassFramed:
            return DesignTokens.Borders.chamfer
        }
    }
    
    private var shadowColor: Color {
        switch style {
        case .obsidianGlass:
            return Color.black.opacity(0.3)
        case .parchment:
            return Color.black.opacity(0.15)
        case .brassFramed:
            return Color.Mystic.brassGoldGlow
        }
    }
    
    private var shadowRadius: CGFloat {
        switch style {
        case .obsidianGlass: return 8
        case .parchment: return 4
        case .brassFramed: return 10
        }
    }
}

#Preview("Victorian Cards") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()
        
        VStack(spacing: DesignTokens.Spacing.lg) {
            VictorianCard(style: .obsidianGlass) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("当前局势 (Current Situation)")
                        .font(Font.Mystic.titleSmall)
                        .foregroundStyle(Color.Mystic.brassGoldPrimary)
                    Text("韦尔奇卧室内的枪声打破了红月的静谧，安提哥努斯笔记不翼而飞。")
                        .font(Font.Mystic.bodyMedium)
                        .foregroundStyle(Color.Mystic.textSecondary)
                }
            }
            
            VictorianCard(style: .parchment) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("侦探案件笔记 · 卷宗 #1349")
                        .font(Font.Mystic.titleSmall)
                        .foregroundStyle(Color.Mystic.parchmentInk)
                    Text("“所有人都会死，包括我。”——韦尔奇遗留字条")
                        .font(Font.Mystic.parchmentCursive)
                        .foregroundStyle(Color.Mystic.parchmentInk)
                }
            }
            
            VictorianCard(style: .brassFramed) {
                HStack {
                    Text("序列 9：占卜家 (Seer)")
                        .font(Font.Mystic.titleMedium)
                        .foregroundStyle(Color.Mystic.textGoldAccent)
                    Spacer()
                    Text("魔药消化度: 68%")
                        .font(Font.Mystic.monoBadge)
                        .foregroundStyle(Color.Mystic.statusOnline)
                }
            }
        }
        .padding(DesignTokens.Spacing.xl)
        .frame(width: 460)
    }
}
