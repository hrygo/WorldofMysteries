import SwiftUI

/// 灵摆占卜状态枚举
public enum PendulumState: String, Sendable, CaseIterable {
    case still = "静止垂落"
    case scrying = "灵性推演中"
    case affirmative = "顺时针·肯定"
    case negative = "逆时针·否定"
    
    public var guidanceText: String {
        switch self {
        case .still: return "手持纯银细链，凝神默念占卜语句七遍..."
        case .scrying: return "灵性共鸣中，黄水晶感知未知的启示..."
        case .affirmative: return "灵摆顺时针回旋：灵性肯定，此结论属实。"
        case .negative: return "灵摆逆时针回旋：灵性否定，存在致命危险或谬误。"
        }
    }
    
    public var auraColor: Color {
        switch self {
        case .still: return Color.Mystic.spiritualBlue.opacity(0.4)
        case .scrying: return Color.Mystic.spiritualBlue
        case .affirmative: return Color.Mystic.brassGoldPrimary
        case .negative: return Color.Mystic.crimsonStar
        }
    }
}

/// 交互式黄水晶灵摆占卜组件（对应 09 调查笔记 Notes & Divination）
public struct SpiritPendulumView: View {
    public let statement: String
    public let state: PendulumState
    public var onTriggerScry: (@MainActor () -> Void)?
    
    @State private var swingAngle: Double = 0
    @State private var rippleScale: CGFloat = 1.0
    @State private var rotationPhase: Double = 0
    
    public init(
        statement: String,
        state: PendulumState = .still,
        onTriggerScry: (@MainActor () -> Void)? = nil
    ) {
        self.statement = statement
        self.state = state
        self.onTriggerScry = onTriggerScry
    }
    
    public var body: some View {
        VStack(spacing: DesignTokens.Spacing.lg) {
            // 占卜语句输入与展示框
            VictorianCard(style: .parchment) {
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                    HStack {
                        Image(systemName: "sparkles")
                            .foregroundStyle(state.auraColor)
                        Text("占卜语句 (Divination Statement)")
                            .font(Font.Mystic.titleSmall)
                            .foregroundStyle(Color.Mystic.parchmentInk)
                        Spacer()
                        Text(state.rawValue)
                            .font(Font.Mystic.caption)
                            .padding(.horizontal, DesignTokens.Spacing.xs)
                            .padding(.vertical, 2)
                            .background(state.auraColor.opacity(0.15))
                            .foregroundStyle(state.auraColor)
                            .clipShape(Capsule())
                    }
                    
                    Text("“\(statement)”")
                        .font(Font.Mystic.parchmentCursive)
                        .foregroundStyle(Color.Mystic.parchmentInk)
                        .lineSpacing(DesignTokens.TypographyMetrics.parchmentLineSpacing)
                        .padding(.vertical, 4)
                }
            }
            
            // 中央灵摆悬挂与物理运动区域
            ZStack(alignment: .top) {
                // 底部灵性回旋水波纹
                Circle()
                    .stroke(state.auraColor.opacity(0.3), lineWidth: 1.5)
                    .frame(width: 140, height: 140)
                    .scaleEffect(rippleScale)
                    .opacity(state == .still ? 0.2 : 0.8)
                    .padding(.top, 120)
                
                // 灵摆物理组件 (顶部挂钩 -> 银链 -> 黄水晶)
                VStack(spacing: 0) {
                    // 纯银手持戒环
                    Circle()
                        .stroke(Color.white.opacity(0.8), lineWidth: 2)
                        .frame(width: 12, height: 12)
                        .shadow(color: Color.white.opacity(0.4), radius: 2)
                    
                    // 纯银细链
                    Rectangle()
                        .fill(
                            LinearGradient(
                                colors: [Color.white.opacity(0.8), Color.gray.opacity(0.6), Color.white.opacity(0.9)],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                        .frame(width: 1.5, height: 90)
                    
                    // 六棱天然黄水晶吊坠 (Citrine Pendant)
                    CitrineCrystalShape()
                        .fill(
                            LinearGradient(
                                colors: [
                                    Color(red: 255/255, green: 224/255, blue: 130/255), // 亮黄水晶面
                                    Color.Mystic.brassGoldPrimary,                       // 金黄核心
                                    Color(red: 180/255, green: 130/255, blue: 40/255)   // 暗金切面
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .frame(width: 24, height: 42)
                        .overlay(
                            CitrineCrystalShape()
                                .stroke(Color.white.opacity(0.5), lineWidth: 1)
                        )
                        .shadow(color: state.auraColor.opacity(0.6), radius: 10)
                }
                .rotationEffect(.degrees(swingAngle), anchor: .top)
                .offset(
                    x: state == .affirmative ? cos(rotationPhase) * 24 : (state == .negative ? -cos(rotationPhase) * 24 : 0),
                    y: state == .affirmative || state == .negative ? sin(rotationPhase) * 12 : 0
                )
            }
            .frame(height: 190)
            
            // 启示指引说明与触发操作
            HStack {
                Text(state.guidanceText)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
                
                Spacer()
                
                if let onTriggerScry {
                    Button {
                        onTriggerScry()
                    } label: {
                        HStack(spacing: DesignTokens.Spacing.xs) {
                            Image(systemName: "arrow.counterclockwise")
                            Text("默念七遍并占卜")
                        }
                        .font(Font.Mystic.titleSmall)
                        .foregroundStyle(Color.Mystic.obsidianBase)
                        .padding(.horizontal, DesignTokens.Spacing.md)
                        .padding(.vertical, DesignTokens.Spacing.sm)
                        .background(Color.Mystic.brassGoldPrimary)
                        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(DesignTokens.Spacing.lg)
        .background(Color.Mystic.obsidianCard)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.lg))
        .overlay(
            RoundedRectangle(cornerRadius: DesignTokens.Radii.lg)
                .stroke(Color.Mystic.brassGoldBorder, lineWidth: DesignTokens.Borders.standard)
        )
        .onAppear {
            applyStateAnimations()
        }
        .onChange(of: state) {
            applyStateAnimations()
        }
    }
    
    private func applyStateAnimations() {
        switch state {
        case .still:
            withAnimation(.easeInOut(duration: 1.0)) {
                swingAngle = 0
                rippleScale = 1.0
            }
        case .scrying:
            withAnimation(.easeInOut(duration: 1.6).repeatForever(autoreverses: true)) {
                swingAngle = 14
                rippleScale = 1.2
            }
        case .affirmative:
            swingAngle = 0
            withAnimation(.linear(duration: 2.0).repeatForever(autoreverses: false)) {
                rotationPhase = .pi * 2
                rippleScale = 1.35
            }
        case .negative:
            swingAngle = 0
            withAnimation(.linear(duration: 2.0).repeatForever(autoreverses: false)) {
                rotationPhase = .pi * 2
                rippleScale = 1.35
            }
        }
    }
}

/// 六棱天然黄水晶几何形
nonisolated struct CitrineCrystalShape: Shape {
    nonisolated func path(in rect: CGRect) -> Path {
        var path = Path()
        let top = CGPoint(x: rect.midX, y: rect.minY)
        let upperLeft = CGPoint(x: rect.minX, y: rect.height * 0.3)
        let upperRight = CGPoint(x: rect.maxX, y: rect.height * 0.3)
        let lowerLeft = CGPoint(x: rect.minX + rect.width * 0.15, y: rect.height * 0.75)
        let lowerRight = CGPoint(x: rect.maxX - rect.width * 0.15, y: rect.height * 0.75)
        let bottom = CGPoint(x: rect.midX, y: rect.maxY)
        
        path.move(to: top)
        path.addLine(to: upperRight)
        path.addLine(to: lowerRight)
        path.addLine(to: bottom)
        path.addLine(to: lowerLeft)
        path.addLine(to: upperLeft)
        path.closeSubpath()
        return path
    }
}

#Preview("Spirit Pendulum States") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()
        
        VStack(spacing: DesignTokens.Spacing.xl) {
            SpiritPendulumView(
                statement: "安提哥努斯家族笔记在瑞尔·比伯手中。",
                state: .affirmative
            )
            
            SpiritPendulumView(
                statement: "今晚独自调查东区废弃仓库是安全的。",
                state: .negative
            )
        }
        .padding(DesignTokens.Spacing.xl)
        .frame(width: 560)
    }
}
