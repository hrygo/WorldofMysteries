import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Metric Reading Review")
struct MetricReadingReviewTests {
    @Test("Non-finite readings are unavailable, not zero or full reserves", arguments: [Double.nan, .infinity, -.infinity])
    func unavailable(value: Double) {
        let reading = WOMMetricReading(value)
        #expect(reading.fraction == nil)
        #expect(reading.geometryFraction == 0)
        #expect(reading.percentText == "读数不可用")
        #expect(!reading.isBelow(0.25))
    }

    @Test("Finite input retains existing normalized clamping behavior")
    func finiteValues() {
        for (value, expected) in [(-1.0, 0.0), (0, 0), (0.25, 0.25), (0.85, 0.85), (1, 1), (2, 1), (Double.greatestFiniteMagnitude, 1)] {
            let reading = WOMMetricReading(value)
            #expect(reading.fraction == expected)
            #expect(reading.percentText == "\(Int(expected * 100))%")
        }
    }

    @Test("Critical threshold uses the same normalized reading as the fill")
    func criticalBoundary() {
        #expect(WOMMetricReading(0).isBelow(0.25))
        #expect(WOMMetricReading(0.2499).isBelow(0.25))
        #expect(!WOMMetricReading(0.25).isBelow(0.25))
        #expect(!WOMMetricReading(1).isBelow(0.25))
        for invalid in [Double.nan, .infinity, -.infinity, -0.1, 1.1] {
            #expect(!WOMMetricReading(0.1).isBelow(invalid))
        }
        #expect(!WOMMetricReading(0.1).isBelow(nil))
    }

    @Test("Decorative gradients cannot contradict the critical warning")
    @MainActor
    func criticalOverridesGradient() {
        let critical = MysticMetricBar(value: 0.1, tone: .teal, criticalThreshold: 0.25, gradientTones: [.teal, .gold])
        #expect(critical.isCritical)
        #expect(critical.resolvedTone == .crimson)
        #expect(!critical.usesGradient)
        let healthy = MysticMetricBar(value: 0.8, tone: .teal, criticalThreshold: 0.25, gradientTones: [.teal, .gold])
        #expect(!healthy.isCritical)
        #expect(healthy.resolvedTone == .teal)
        #expect(healthy.usesGradient)
    }

    @Test("Gauge and metric agree on unknown data without invoking Int on NaN")
    @MainActor
    func unavailableViews() {
        for value in [Double.nan, .infinity, -.infinity] {
            let gauge = SpiritualityGaugeView(value: value)
            let bar = MysticMetricBar(value: value, criticalThreshold: 0.25, gradientTones: [.teal, .gold])
            #expect(gauge.reading.percentText == "读数不可用")
            #expect(gauge.reading == bar.reading)
            #expect(bar.resolvedTone == .neutral)
            #expect(!bar.usesGradient)
        }
    }

    @Test("Gauge and metric use the safe reading for visible and assistive output")
    func readingWiring() throws {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("WorldOfMysteries/Components")
        let gauge = try String(contentsOf: root.appendingPathComponent("SpiritualityGaugeView.swift"), encoding: .utf8)
        let primitives = try String(contentsOf: root.appendingPathComponent("MysticPrimitives.swift"), encoding: .utf8)
        #expect(gauge.contains("Text(reading.percentText)"))
        #expect(gauge.contains("if reading.fraction != nil"))
        for source in [gauge, primitives] {
            #expect(source.contains(".accessibilityValue(reading.percentText)"))
            #expect(!source.contains("Int(value * 100)"))
            #expect(!source.contains("Int(clampedValue * 100)"))
        }
    }
}
