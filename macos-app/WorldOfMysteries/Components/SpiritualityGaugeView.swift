import SwiftUI

/// 维多利亚复古黄铜灵性与理智仪表盘 (Spirituality & Sanity Gauge)
public struct SpiritualityGaugeView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public let title: String
    /// 灵性值：0.0 (枯竭/失控) ~ 1.0 (充盈稳固)
    public let value: Double

    public init(
        title: String = "灵性存量 (Spirituality)",
        value: Double = 0.85
    ) {
        self.title = title
        self.value = value.isFinite ? min(max(value, 0.0), 1.0) : value
    }

    public var body: some View {
        VStack(spacing: DesignTokens.Spacing.xs) {
            ZStack {
                Circle()
                    .fill(Color.Mystic.obsidianCard)
                    .frame(
                        width: DesignTokens.ComponentMetrics.Gauge.diameter,
                        height: DesignTokens.ComponentMetrics.Gauge.diameter
                    )
                    .overlay(
                        Circle()
                            .stroke(Color.Mystic.brassGoldPrimary, lineWidth: DesignTokens.Borders.chamfer)
                    )
                    .shadow(
                        color: Color.Mystic.shadowBase.opacity(0.4),
                        radius: DesignTokens.ComponentMetrics.Gauge.shadowRadius
                    )

                Circle()
                    .fill(Color.Mystic.obsidianBase)
                    .frame(
                        width: DesignTokens.ComponentMetrics.Gauge.innerDiameter,
                        height: DesignTokens.ComponentMetrics.Gauge.innerDiameter
                    )

                scaleTrack
                    .frame(
                        width: DesignTokens.ComponentMetrics.Gauge.arcDiameter,
                        height: DesignTokens.ComponentMetrics.Gauge.arcDiameter
                    )

                if reading.fraction != nil {
                    Rectangle()
                        .fill(Color.Mystic.brassGoldHover)
                        .frame(
                            width: DesignTokens.ComponentMetrics.Gauge.needleWidth,
                            height: DesignTokens.ComponentMetrics.Gauge.needleLength
                        )
                        .offset(y: -DesignTokens.ComponentMetrics.Gauge.needleLength / 2)
                        .rotationEffect(.degrees(gaugeAngle))
                        .animation(reduceMotion ? nil : DesignTokens.Motion.smoothSpring, value: reading.geometryFraction)
                }

                Circle()
                    .fill(Color.Mystic.brassGoldPrimary)
                    .frame(
                        width: DesignTokens.ComponentMetrics.Gauge.hubDiameter,
                        height: DesignTokens.ComponentMetrics.Gauge.hubDiameter
                    )
            }

            VStack(spacing: DesignTokens.Spacing.xxs) {
                Text(reading.percentText)
                    .font(Font.Mystic.monoBadge)
                    .foregroundStyle(valueTextColor)

                Text(title)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(title)
        .accessibilityValue(reading.percentText)
    }

    // The scale and the needle use the same increasing, left-to-right fraction.
    // Rotating a trimmed Circle also rotated its gradient, reversing the old warning colors.
    @ViewBuilder
    private var scaleTrack: some View {
        if reading.fraction != nil {
            ZStack {
                ForEach(WOMGaugeBand.allCases, id: \.self) { band in
                    WOMGaugeScaleArc(fractions: band.fractions)
                        .stroke(
                            band.color,
                            style: StrokeStyle(
                                lineWidth: DesignTokens.ComponentMetrics.Gauge.arcLineWidth,
                                lineCap: .butt
                            )
                        )
                }
            }
        } else {
            // Unknown is neither safe nor dangerous. No severity band or needle is implied.
            WOMGaugeScaleArc(fractions: 0...1)
                .stroke(
                    Color.Mystic.textSecondary,
                    style: StrokeStyle(
                        lineWidth: DesignTokens.Borders.standard,
                        dash: [DesignTokens.Spacing.xxs, DesignTokens.Spacing.xxs]
                    )
                )
        }
    }

    var reading: WOMMetricReading { WOMMetricReading(value) }

    /// 0.0 映射到 -90 度，1.0 映射到 +90 度
    private var gaugeAngle: Double {
        DesignTokens.ComponentMetrics.Gauge.needleMinimumDegrees
            + reading.geometryFraction * (
                DesignTokens.ComponentMetrics.Gauge.needleMaximumDegrees
                    - DesignTokens.ComponentMetrics.Gauge.needleMinimumDegrees
            )
    }

    /// Danger remains visible in the gauge arc; the numeric value itself must remain readable.
    private var valueTextColor: Color {
        guard reading.fraction != nil else { return Color.Mystic.textSecondary }
        if reading.isBelow(DesignTokens.ComponentMetrics.Gauge.criticalThreshold) {
            return Color.Mystic.textPrimary
        } else if reading.isBelow(DesignTokens.ComponentMetrics.Gauge.warningThreshold) {
            return Color.Mystic.statusWarning
        } else {
            return Color.Mystic.spiritualBlue
        }
    }
}

/// Visual ranges only: reuse the existing scale thresholds, do not infer Domain state.
nonisolated enum WOMGaugeBand: CaseIterable, Hashable, Sendable {
    case critical, warning, reserve

    var fractions: ClosedRange<Double> {
        switch self {
        case .critical: 0...DesignTokens.ComponentMetrics.Gauge.criticalThreshold
        case .warning:
            DesignTokens.ComponentMetrics.Gauge.criticalThreshold...DesignTokens.ComponentMetrics.Gauge.warningThreshold
        case .reserve: DesignTokens.ComponentMetrics.Gauge.warningThreshold...1
        }
    }

    @MainActor
    var color: Color {
        switch self {
        case .critical: Color.Mystic.statusDanger
        case .warning: Color.Mystic.statusWarning
        case .reserve: Color.Mystic.spiritualBlue
        }
    }
}

/// Draw the upper semicircle directly in SwiftUI's top-left coordinate system.
/// Zero is the left endpoint; one is the right endpoint. No post-paint rotation is used.
nonisolated struct WOMGaugeScaleArc: Shape {
    let fractions: ClosedRange<Double>

    func path(in rect: CGRect) -> Path {
        let start = DesignTokens.ComponentMetrics.Gauge.arcStartDegrees
        let span = DesignTokens.ComponentMetrics.Gauge.arcEndDegrees - start
        var path = Path()
        path.addArc(
            center: CGPoint(x: rect.midX, y: rect.midY),
            radius: min(rect.width, rect.height) / 2,
            startAngle: .degrees(start + fractions.lowerBound * span),
            endAngle: .degrees(start + fractions.upperBound * span),
            clockwise: false
        )
        return path
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
