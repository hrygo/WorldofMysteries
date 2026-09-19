import AppKit
import Foundation
import SwiftUI
import Testing
@testable import WorldOfMysteriesCore

/// 贴边语义竖条 (`WOMLeadingRail`) 与面板圆角轮廓的拟合度回归。
///
/// 渲染真实的 `WOMStatusBanner` 后逐像素核对几何契约：
///
/// 1. 无外溢：竖条像素全部落在面板轮廓之内（旧实现会在圆角处悬垂到面板轮廓之外）；
/// 2. 无缝隙：直边段的竖条最左像素贴住面板左缘；
/// 3. 端点与厚度：竖条盖满整条左缘（含上下圆角）却不沿上下边缘延伸，直边段厚度等于语义令牌。
///
/// 圆角段的外缘像素会被抗锯齿摊开半像素，因此缝隙判定只取几何上确实竖直的直边段，
/// 圆角段由「不出轮廓 + 端点到位」两条断言覆盖。
@Suite("Leading Rail Fit")
@MainActor
struct LeadingRailFitTests {
    private static let scale: CGFloat = 2
    private static let proposedWidth: CGFloat = 320
    private static let colorTolerance: CGFloat = 0.04
    /// 抗锯齿会把轮廓边缘摊到半像素内，判定按像素外边界放宽这一点余量。
    private static let edgeAllowance: CGFloat = 0.5
    /// 直边段识别：轮廓左缘与面板最左点重合即视为竖直段。
    private static let straightSectionTolerance: CGFloat = 0.1
    private static let flushTolerance: CGFloat = 1.0
    private static let thicknessTolerance: CGFloat = 0.75
    private static let railEndTolerance: CGFloat = 1.0

    @Test(arguments: [WOMFeedbackTone.info, .success, .warning, .danger])
    func leadingRailFitsPanelContour(tone: WOMFeedbackTone) throws {
        try assertRailFits(tone: tone)
    }

    private func assertRailFits(tone: WOMFeedbackTone) throws {
        _ = NSApplication.shared
        let bitmap = try renderBanner(tone: tone)
        let accent = try referenceColor(feedbackAccentColor(tone))
        let canvas = SampledImage(
            bitmap: bitmap,
            accent: accent,
            scale: Self.scale,
            colorTolerance: Self.colorTolerance
        )

        let panel = try #require(canvas.opaqueBounds, "\(tone)：面板没有渲染出来")
        let radius = DesignTokens.Radii.md
        let contour = Path(roundedRect: panel, cornerRadius: radius, style: .continuous).cgPath
        let reachable = Path(
            roundedRect: panel.insetBy(dx: -Self.edgeAllowance, dy: -Self.edgeAllowance),
            cornerRadius: radius + Self.edgeAllowance,
            style: .continuous
        ).cgPath

        var violations: [String] = []
        let rows = canvas.railColumns.sorted { $0.key < $1.key }
        if rows.isEmpty {
            violations.append("竖条没有渲染出来")
        }

        let cornerLimit = (panel.minX + radius * 2) * Self.scale
        var straightSectionRows = 0
        for (row, columns) in rows {
            let y = (CGFloat(row) + 0.5) / Self.scale
            let panelEdge = leftmostContourX(of: contour, atRow: y, within: panel)
            let railEdge = (CGFloat(columns.min() ?? 0) + 0.5) / Self.scale

            // 契约 1：竖条不允许出现在面板轮廓之外。
            for column in columns where !reachable.contains(
                CGPoint(x: (CGFloat(column) + 0.5) / Self.scale, y: y),
                using: .winding
            ) {
                violations.append("越出面板轮廓 (row \(row), column \(column))")
            }

            // 契约 2：直边段的最左竖条像素必须贴住面板左缘。
            if panelEdge - panel.minX <= Self.straightSectionTolerance {
                straightSectionRows += 1
                if railEdge - panelEdge > Self.flushTolerance {
                    violations.append("直边段与面板左缘留缝 (row \(row): rail \(railEdge)pt, panel \(panelEdge)pt)")
                }
            }

            // 契约 3a：端点收在圆角内，不沿上下边缘延伸。
            guard y < panel.minY + 1 || y > panel.maxY - 1 else { continue }
            if let rightmost = columns.max(), CGFloat(rightmost) > cornerLimit {
                violations.append("沿上下边缘越过圆角 (row \(row), column \(rightmost))")
            }
        }

        // 契约 3b：竖条盖满整条左缘，端点落在上下圆角切点上。
        let railTop = (CGFloat(rows.first?.key ?? 0) + 0.5) / Self.scale
        let railBottom = (CGFloat(rows.last?.key ?? 0) + 0.5) / Self.scale
        if railTop - panel.minY > Self.railEndTolerance {
            violations.append("竖条顶端 \(railTop)pt 未到达上圆角切点")
        }
        if panel.maxY - railBottom > Self.railEndTolerance {
            violations.append("竖条底端 \(railBottom)pt 未到达下圆角切点")
        }

        // 契约 3c：直边段厚度等于语义厚度令牌（沿轮廓法线方向恒定）。
        let middleRow = Int(panel.midY * Self.scale)
        let thickness = CGFloat(leadingRun(of: canvas.railColumns[middleRow] ?? [])) / Self.scale
        let expected = DesignTokens.ComponentMetrics.LeadingRail.thickness
        if abs(thickness - expected) > Self.thicknessTolerance {
            violations.append("直边段厚度 \(thickness)pt 偏离令牌 \(expected)pt")
        }

        if straightSectionRows == 0 {
            violations.append("没有采到直边段，缝隙判定未生效")
        }

        #expect(violations.isEmpty, "\(tone)：\(violations.prefix(6).joined(separator: "；"))")
    }

    // MARK: - Render

    private func renderBanner(tone: WOMFeedbackTone) throws -> NSBitmapImageRep {
        let banner = WOMStatusBanner(
            tone: tone,
            title: "世界状态已刷新",
            message: "新的已提交世界事实可用于后续叙事。"
        )
        .environment(\.colorScheme, .dark)
        .transaction { $0.disablesAnimations = true }

        let renderer = ImageRenderer(content: banner)
        renderer.scale = Self.scale
        renderer.proposedSize = ProposedViewSize(width: Self.proposedWidth, height: nil)
        return NSBitmapImageRep(cgImage: try #require(renderer.cgImage))
    }

    /// 用同一条渲染管线取语义色参考值：直接把 `Color` 桥成 `NSColor` 可能解析到别的色彩空间。
    private func referenceColor(_ color: Color) throws -> NSColor {
        let renderer = ImageRenderer(
            content: color
                .frame(width: 8, height: 8)
                .environment(\.colorScheme, .dark)
        )
        renderer.scale = Self.scale
        let bitmap = NSBitmapImageRep(cgImage: try #require(renderer.cgImage))
        return try #require(bitmap.colorAt(x: 8, y: 8)?.usingColorSpace(.sRGB))
    }

    private func leftmostContourX(of contour: CGPath, atRow y: CGFloat, within panel: CGRect) -> CGFloat {
        var x = panel.minX
        while x <= panel.maxX {
            if contour.contains(CGPoint(x: x, y: y), using: .winding) { return x }
            x += 0.05
        }
        return panel.maxX
    }

    private func leadingRun(of columns: [Int]) -> Int {
        guard let start = columns.min() else { return 0 }
        var run = 0
        var cursor = start
        while columns.contains(cursor) {
            run += 1
            cursor += 1
        }
        return run
    }
}

/// 一次渲染的采样结果：不透明像素边界 + 语义色像素分布。
@MainActor
private struct SampledImage {
    let railColumns: [Int: [Int]]
    let opaqueBounds: CGRect?

    init(bitmap: NSBitmapImageRep, accent: NSColor, scale: CGFloat, colorTolerance: CGFloat) {
        let accentComponents = [accent.redComponent, accent.greenComponent, accent.blueComponent]
        var railColumns: [Int: [Int]] = [:]
        var minColumn = Int.max
        var maxColumn = Int.min
        var minRow = Int.max
        var maxRow = Int.min

        for row in 0..<bitmap.pixelsHigh {
            for column in 0..<bitmap.pixelsWide {
                guard let color = bitmap.colorAt(x: column, y: row)?.usingColorSpace(.sRGB) else { continue }
                guard color.alphaComponent >= 0.95 else { continue }

                minColumn = min(minColumn, column)
                maxColumn = max(maxColumn, column)
                minRow = min(minRow, row)
                maxRow = max(maxRow, row)

                let components = [color.redComponent, color.greenComponent, color.blueComponent]
                let matchesAccent = zip(components, accentComponents)
                    .allSatisfy { abs($0 - $1) <= colorTolerance }
                if matchesAccent {
                    railColumns[row, default: []].append(column)
                }
            }
        }

        self.railColumns = railColumns
        opaqueBounds = minColumn <= maxColumn
            ? CGRect(
                x: CGFloat(minColumn) / scale,
                y: CGFloat(minRow) / scale,
                width: CGFloat(maxColumn - minColumn + 1) / scale,
                height: CGFloat(maxRow - minRow + 1) / scale
            )
            : nil
    }
}
