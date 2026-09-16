import SwiftUI

/// 灵摆占卜推演状态
public enum ScryingResult: String, Sendable, CaseIterable {
    case inquiring = "占卜推演中"
    case affirmative = "启示：肯定 (Yes)"
    case negative = "启示：否定 (No)"
    case disturbed = "受阻：灵界干扰"
    
    public var accentColor: Color {
        switch self {
        case .inquiring: return Color.Mystic.brassGoldPrimary
        case .affirmative: return Color.Mystic.statusOnline
        case .negative: return Color.Mystic.crimsonStar
        case .disturbed: return Color.Mystic.statusWarning
        }
    }
}

/// 黄水晶吊坠 · 灵视占卜仪轨视窗组件
/// 深度融合《占卜家 · 克莱恩·莫雷蒂》正典写实黄水晶吊坠与红茶占卜水纹素材
public struct CitrinePendulumScryingCard: View {
    public let defaultStatement: String
    public var onScryingTriggered: (@MainActor (String) -> Void)?
    
    @State private var statement: String
    @State private var state: ScryingResult = .inquiring
    @State private var isPendulumRotating: Bool = false
    @State private var rotationAngle: Double = 0.0
    @State private var glowOpacity: Double = 0.4
    
    public init(
        defaultStatement: String = "《安提哥努斯家族笔记》仍遗留在廷根市内。",
        onScryingTriggered: (@MainActor (String) -> Void)? = nil
    ) {
        self.defaultStatement = defaultStatement
        self._statement = State(initialValue: defaultStatement)
        self.onScryingTriggered = onScryingTriggered
    }
    
    public var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
            // 顶部标题与非凡品阶标牌
            HStack(alignment: .center) {
                HStack(spacing: DesignTokens.Spacing.xs) {
                    Image(systemName: "sparkles")
                        .font(.system(size: 14))
                        .foregroundStyle(Color.Mystic.brassGoldPrimary)
                    
                    Text("黄水晶吊坠 · 灵摆占卜法")
                        .font(Font.Mystic.titleSmall)
                        .foregroundStyle(Color.Mystic.textPrimary)
                }
                
                Spacer()
                
                HStack(spacing: 4) {
                    Text("灵性消耗")
                        .font(.system(size: 10))
                        .foregroundStyle(Color.Mystic.textTertiary)
                    
                    Text("-5%")
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundStyle(Color.Mystic.azureResonanceColor)
                }
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.Mystic.obsidianCard)
                .clipShape(Capsule())
            }
            
            // 中央写实原画视窗（纯银细链、黄水晶透光吊坠与描金红茶杯）
            ZStack(alignment: .bottom) {
                // 真实原画展示
                if NSImage(named: "PendulumCitrine") != nil {
                    Image("PendulumCitrine")
                        .resizable()
                        .scaledToFill()
                        .frame(height: 260)
                        .frame(maxWidth: .infinity)
                        .clipped()
                        .overlay(
                            LinearGradient(
                                colors: [Color.clear, Color.Mystic.obsidianBase.opacity(0.8)],
                                startPoint: .center,
                                endPoint: .bottom
                            )
                        )
                } else {
                    // 纯代码矢量优雅降级背景
                    ZStack {
                        Color.Mystic.obsidianBase
                        Circle()
                            .stroke(Color.Mystic.brassGoldBorder, lineWidth: 1)
                            .frame(width: 140, height: 140)
                        Image(systemName: "circle.circle")
                            .font(.system(size: 48))
                            .foregroundStyle(Color.Mystic.brassGoldPrimary)
                    }
                    .frame(height: 260)
                }
                
                // 灵光动态光晕与顺/逆时针物理摆动提示
                VStack(spacing: DesignTokens.Spacing.xs) {
                    HStack(spacing: DesignTokens.Spacing.sm) {
                        Circle()
                            .fill(state.accentColor)
                            .frame(width: 8, height: 8)
                            .shadow(color: state.accentColor.opacity(0.8), radius: 6)
                        
                        Text(state.rawValue)
                            .font(Font.Mystic.bodyMedium)
                            .fontWeight(.semibold)
                            .foregroundStyle(state.accentColor)
                    }
                    .padding(.horizontal, DesignTokens.Spacing.md)
                    .padding(.vertical, 4)
                    .background(
                        Capsule()
                            .fill(Color.Mystic.obsidianElevated.opacity(0.92))
                            .overlay(
                                Capsule()
                                    .stroke(state.accentColor.opacity(0.4), lineWidth: 1)
                            )
                    )
                    
                    Text(guidanceText)
                        .font(Font.Mystic.caption)
                        .foregroundStyle(Color.Mystic.textSecondary)
                }
                .padding(.bottom, DesignTokens.Spacing.md)
            }
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
                    .stroke(Color.Mystic.brassGoldBorder, lineWidth: DesignTokens.Borders.standard)
            )
            
            // 待占卜语句与灵性启示交互条
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                Text("默念占卜语句 (7遍)：")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.brassGoldMuted)
                
                HStack(spacing: DesignTokens.Spacing.sm) {
                    TextField("输入占卜语句...", text: $statement)
                        .textFieldStyle(.plain)
                        .font(Font.Mystic.parchmentCursive)
                        .foregroundStyle(Color.Mystic.textPrimary)
                        .padding(.horizontal, DesignTokens.Spacing.md)
                        .padding(.vertical, DesignTokens.Spacing.sm)
                        .background(
                            RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                                .fill(Color.Mystic.obsidianCard)
                                .overlay(
                                    RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                                        .stroke(Color.Mystic.brassGoldBorder.opacity(0.5), lineWidth: 1)
                                )
                        )
                    
                    Button {
                        triggerScryingSimulation()
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "waveform.path")
                            Text("执链占卜")
                        }
                        .font(Font.Mystic.bodyMedium)
                        .fontWeight(.semibold)
                        .foregroundStyle(Color.Mystic.obsidianBase)
                        .padding(.horizontal, DesignTokens.Spacing.md)
                        .padding(.vertical, DesignTokens.Spacing.sm)
                        .background(
                            RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                                .fill(Color.Mystic.brassGoldPrimary)
                        )
                        .shadow(color: Color.Mystic.brassGoldPrimary.opacity(0.4), radius: 6)
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(DesignTokens.Spacing.lg)
        .background(
            Color.Mystic.obsidianElevated
                .overlay(
                    LinearGradient(
                        colors: [Color.Mystic.brassGoldMuted.opacity(0.05), Color.clear],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
        )
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.lg))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radii.lg)
                .stroke(Color.Mystic.brassGoldBorder, lineWidth: DesignTokens.Borders.standard)
        )
    }
    
    private var guidanceText: String {
        switch state {
        case .inquiring:
            return "手肘抵桌，持链悬垂，闭目默念七遍语句……"
        case .affirmative:
            return "灵摆呈顺时针规律旋转 · 灵界回馈为真"
        case .negative:
            return "灵摆呈逆时针剧烈旋转 · 灵界回馈为假"
        case .disturbed:
            return "灵摆杂乱无章震颤 · 涉及高位存在，无法直视"
        }
    }
    
    private func triggerScryingSimulation() {
        state = .inquiring
        withAnimation(DesignTokens.Motion.smoothSpring) {
            rotationAngle = 15.0
        }
        
        // 模拟 1.2 秒后得出占卜结论
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
            withAnimation(DesignTokens.Motion.smoothSpring) {
                state = .affirmative
                rotationAngle = 0
            }
            onScryingTriggered?(statement)
        }
    }
}

private extension Color.Mystic {
    static var azureResonanceColor: Color {
        Color(red: 74/255, green: 144/255, blue: 226/255)
    }
}

#Preview("Citrine Pendulum Scrying Card") {
    CitrinePendulumScryingCard()
        .frame(width: 420)
        .padding()
        .background(Color.Mystic.obsidianBase)
}
