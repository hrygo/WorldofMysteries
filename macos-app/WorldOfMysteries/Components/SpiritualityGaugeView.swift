import SwiftUI

/// 维多利亚复古黄铜灵性与理智仪表盘 (Spirituality & Sanity Gauge)
public struct SpiritualityGaugeView: View {
    public let title: String
    /// 灵性值：0.0 (枯竭/失控) ~ 1.0 (充盈稳固)
    public let value: Double
    
    public init(
        title: String = "灵性存量 (Spirituality)",
        value: Double = 0.85
    ) {
        self.title = title
        self.value = min(max(value, 0.0), 1.0)
    }
    
    public var body: some View {
        VStack(spacing: DesignTokens.Spacing.xs) {
            ZStack {
                // 外层黄铜铆钉表圈
                Circle()
                    .fill(Color.Mystic.obsidianCard)
                    .frame(width: 88, height: 88)
                    .overlay(
                        Circle()
                            .stroke(Color.Mystic.brassGoldPrimary, lineWidth: DesignTokens.Borders.chamfer)
                    )
                    .shadow(color: Color.black.opacity(0.4), radius: 6)
                
                // 表盘内底纹
                Circle()
                    .fill(Color.Mystic.obsidianBase)
                    .frame(width: 74, height: 74)
                
                // 警戒弧线 (0 ~ 180度)
                Circle()
                    .trim(from: 0.0, to: 0.5)
                    .stroke(
                        AngularGradient(
                            gradient: Gradient(colors: [
                                Color.Mystic.statusDanger,
                                Color.Mystic.statusWarning,
                                Color.Mystic.spiritualBlue
                            ]),
                            center: .center,
                            startAngle: .degrees(180),
                            endAngle: .degrees(360)
                        ),
                        style: StrokeStyle(lineWidth: 4, lineCap: .round)
                    )
                    .frame(width: 60, height: 60)
                    .rotationEffect(.degrees(180))
                
                // 黄铜指针
                Rectangle()
                    .fill(Color.Mystic.brassGoldHover)
                    .frame(width: 2, height: 26)
                    .offset(y: -13)
                    .rotationEffect(.degrees(gaugeAngle))
                    .animation(DesignTokens.Motion.smoothSpring, value: value)
                
                // 表心黄铜铆钉
                Circle()
                    .fill(Color.Mystic.brassGoldPrimary)
                    .frame(width: 8, height: 8)
            }
            
            // 仪表数值与标题
            VStack(spacing: DesignTokens.Spacing.xxs) {
                Text("\(Int(value * 100))%")
                    .font(Font.Mystic.monoBadge)
                    .foregroundStyle(valueColor)
                
                Text(title)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
            }
        }
    }
    
    /// 0.0 映射到 -90 度，1.0 映射到 +90 度
    private var gaugeAngle: Double {
        -90.0 + (value * 180.0)
    }
    
    private var valueColor: Color {
        if value < 0.25 {
            return Color.Mystic.statusDanger
        } else if value < 0.5 {
            return Color.Mystic.statusWarning
        } else {
            return Color.Mystic.spiritualBlue
        }
    }
}

#Preview("Spirituality Gauge") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()
        HStack(spacing: DesignTokens.Spacing.xl) {
            SpiritualityGaugeView(title: "枯竭临界", value: 0.15)
            SpiritualityGaugeView(title: "灵性适中", value: 0.55)
            SpiritualityGaugeView(title: "充盈稳固", value: 0.92)
        }
    }
    .frame(width: 480, height: 180)
}
