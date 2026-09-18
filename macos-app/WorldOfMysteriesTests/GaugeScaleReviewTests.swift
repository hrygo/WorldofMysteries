import AppKit
import SwiftUI
import Testing
@testable import WorldOfMysteriesCore

@Suite("Gauge Scale Review", .serialized)
struct GaugeScaleReviewTests {
    @Test("Scale bands reuse the same ordered thresholds as the reading")
    func scaleThresholds() {
        let low = WOMGaugeBand.critical.fractions
        let warning = WOMGaugeBand.warning.fractions
        let reserve = WOMGaugeBand.reserve.fractions
        #expect(low.lowerBound == 0)
        #expect(low.upperBound == DesignTokens.ComponentMetrics.Gauge.criticalThreshold)
        #expect(warning.lowerBound == low.upperBound)
        #expect(warning.upperBound == DesignTokens.ComponentMetrics.Gauge.warningThreshold)
        #expect(reserve.lowerBound == warning.upperBound)
        #expect(reserve.upperBound == 1)
        #expect(low.upperBound < warning.upperBound)
    }

    @Test("Native gauge pixels place danger at low reserves and blue at high reserves")
    @MainActor
    func scalePixels() throws {
        _ = NSApplication.shared
        for value in [0.1, 0.85] {
            let bitmap = try render(value: value)
            for band in WOMGaugeBand.allCases {
                let fraction = (band.fractions.lowerBound + band.fractions.upperBound) / 2
                let actual = try scalePixel(at: fraction, in: bitmap)
                // Sample a flat semantic swatch through the same native render pipeline.
                // Bridging a Color directly into NSColor can resolve a different working gamut.
                let expected = try referenceColor(band.color)
                print("GAUGE_SAMPLE value=\(value) band=\(band) actual=\(actual) reference=\(expected)")
                #expect(abs(actual.redComponent - expected.redComponent) < 0.02)
                #expect(abs(actual.greenComponent - expected.greenComponent) < 0.02)
                #expect(abs(actual.blueComponent - expected.blueComponent) < 0.02)
            }
        }
    }

    @Test("Unavailable readings do not paint a danger or healthy severity band")
    @MainActor
    func unavailableScalePixels() throws {
        _ = NSApplication.shared
        let bitmap = try render(value: .nan)
        // Dashed neutral track and backdrop are achromatic enough to exclude either
        // saturated danger red or spirituality blue, regardless of the dash phase.
        for fraction in [0.125, 0.375, 0.75] {
            let sample = try scalePixel(at: fraction, in: bitmap)
            let channels = [sample.redComponent, sample.greenComponent, sample.blueComponent]
            #expect((channels.max() ?? 0) - (channels.min() ?? 0) < 0.2)
        }
    }

    @MainActor
    private func render(value: Double) throws -> NSBitmapImageRep {
        let view = SpiritualityGaugeView(title: "灵性", value: value)
            .frame(width: DesignTokens.ComponentMetrics.Gauge.diameter)
            .background(Color.Mystic.obsidianBase)
            .environment(\.colorScheme, .dark)
            .transaction { $0.disablesAnimations = true }
        let renderer = ImageRenderer(content: view)
        renderer.scale = 2
        let bitmap = NSBitmapImageRep(cgImage: try #require(renderer.cgImage))
        if let output = ProcessInfo.processInfo.environment["WOM_VISUAL_QA_OUTPUT"] {
            let directory = URL(fileURLWithPath: output)
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let name = value.isFinite ? "gauge-\(value).png" : "gauge-unavailable.png"
            try #require(bitmap.representation(using: .png, properties: [:]))
                .write(to: directory.appendingPathComponent(name))
        }
        return bitmap
    }

    @MainActor
    private func referenceColor(_ color: Color) throws -> NSColor {
        let renderer = ImageRenderer(content: color.frame(width: 8, height: 8)
            .environment(\.colorScheme, .dark))
        renderer.scale = 2
        let bitmap = NSBitmapImageRep(cgImage: try #require(renderer.cgImage))
        return try #require(bitmap.colorAt(x: 8, y: 8)?.usingColorSpace(.sRGB))
    }

    @MainActor
    private func scalePixel(at fraction: Double, in bitmap: NSBitmapImageRep) throws -> NSColor {
        let scale = CGFloat(bitmap.pixelsWide) / DesignTokens.ComponentMetrics.Gauge.diameter
        let center = DesignTokens.ComponentMetrics.Gauge.diameter * scale / 2
        let radius = DesignTokens.ComponentMetrics.Gauge.arcDiameter * scale / 2
        let start = DesignTokens.ComponentMetrics.Gauge.arcStartDegrees
        let span = DesignTokens.ComponentMetrics.Gauge.arcEndDegrees - start
        let radians = (start + fraction * span) * .pi / 180
        let x = Int((center + CGFloat(cos(radians)) * radius).rounded())
        let y = Int((center + CGFloat(sin(radians)) * radius).rounded())
        return try #require(bitmap.colorAt(x: x, y: y)?.usingColorSpace(.sRGB))
    }
}
