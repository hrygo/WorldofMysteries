import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Visual Contrast Contracts")
struct VisualContrastContractTests {
    @Test("approved readable token pairs keep their WCAG contrast floors")
    func approvedReadablePairs() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/DesignTokens.swift")

        let pairs: [(foreground: String, background: String, minimum: Double)] = [
            ("textPrimary", "obsidianBase", 7.0),
            ("textPrimary", "obsidianCard", 7.0),
            ("textPrimary", "deepVoid", 7.0),
            ("textSecondary", "obsidianBase", 7.0),
            ("textSecondary", "obsidianCard", 7.0),
            ("textSecondary", "deepVoid", 4.5),
            ("textTertiary", "obsidianBase", 4.5),
            // 10-11pt 元数据（快捷键提示、容量、时间戳）大量落在卡片面上，底线从 AA 提到 6:1。
            ("textTertiary", "obsidianCard", 6.0),
            ("textGoldAccent", "obsidianCard", 7.0),
            ("textGoldAccent", "deepVoid", 7.0),
            ("brassGoldPrimary", "obsidianCard", 7.0),
            // 元数据金色同样承担小字号文本，不再停留在「贴线通过」。
            ("brassGoldMuted", "obsidianCard", 5.0),
            // 可辨识边界（输入框轮廓、hover/选中描边）必须满足 1.4.11 的 3:1。
            ("brassGoldBoundary", "obsidianBase", 3.0),
            ("brassGoldBoundary", "obsidianCard", 3.0),
            ("spiritualBlue", "obsidianCard", 4.5),
            ("statusOnline", "obsidianCard", 4.5),
            ("statusWarning", "obsidianCard", 4.5),
            ("textPrimary", "crimsonThread", 4.5),
            ("parchmentInk", "parchmentCard", 7.0),
            ("parchmentInkSecondary", "parchmentCard", 7.0),
            ("parchmentInkTertiary", "parchmentCard", 4.5),
        ]

        var failures: [String] = []
        for pair in pairs {
            let foreground = try color(named: pair.foreground, in: source)
            let background = try color(named: pair.background, in: source)
            let ratio = contrastRatio(foreground, background)

            if ratio + 0.0001 < pair.minimum {
                failures.append(
                    "\(pair.foreground) on \(pair.background): "
                        + String(format: "%.2f", ratio)
                        + ":1 < required "
                        + String(format: "%.1f", pair.minimum)
                        + ":1"
                )
            }
        }

        for failure in failures {
            print("VISUAL_QA_CONTRAST: \(failure)")
        }
        #expect(failures.isEmpty)
    }

    @Test("danger button semantic pair remains explicitly high contrast")
    func dangerButtonPair() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/DesignTokens.swift")
        let foreground = try color(named: "textPrimary", in: source)
        let background = try color(named: "crimsonThread", in: source)

        #expect(contrastRatio(foreground, background) >= 4.5)
    }

    @Test("count badge keeps white numerals readable on its own fill")
    func countBadgePair() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/DesignTokens.swift")
        let badgeFill = try color(named: "crimsonBadge", in: source)
        // 徽标是 10pt 白字，必须用自己的实底承载，禁止直接用装饰性的 crimsonStar。
        #expect(
            contrastRatio(RGB(red: 1, green: 1, blue: 1), badgeFill) >= 4.5,
            "crimsonBadge must carry white numerals at AA or better"
        )
    }

    @Test("sidebar count badge uses the dedicated readable fill")
    func sidebarBadgeUsesReadableFill() throws {
        let sidebar = try source("macos-app/WorldOfMysteries/Components/AppSidebarView.swift")

        #expect(sidebar.contains("Color.Mystic.crimsonBadge"))
        #expect(!sidebar.contains("Capsule().fill(Color.Mystic.crimsonStar"))
    }

    @Test("parchment hierarchy keeps readable primary secondary and tertiary ink")
    func parchmentHierarchy() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/DesignTokens.swift")
        let background = try color(named: "parchmentCard", in: source)

        #expect(contrastRatio(try color(named: "parchmentInk", in: source), background) >= 7.0)
        #expect(contrastRatio(try color(named: "parchmentInkSecondary", in: source), background) >= 7.0)
        #expect(contrastRatio(try color(named: "parchmentInkTertiary", in: source), background) >= 4.5)
    }

    // MARK: - WCAG math

    private struct RGB {
        let red: Double
        let green: Double
        let blue: Double
    }

    private func color(named name: String, in source: String) throws -> RGB {
        let escapedName = NSRegularExpression.escapedPattern(for: name)
        let pattern = "public\\s+static\\s+let\\s+\(escapedName)\\s*=\\s*Color\\(\\s*red:\\s*([0-9.]+)\\s*/\\s*255\\s*,\\s*green:\\s*([0-9.]+)\\s*/\\s*255\\s*,\\s*blue:\\s*([0-9.]+)\\s*/\\s*255\\s*\\)"
        let regex = try NSRegularExpression(pattern: pattern)
        let range = NSRange(source.startIndex..<source.endIndex, in: source)

        guard let match = regex.firstMatch(in: source, range: range) else {
            throw NSError(
                domain: "VisualContrastContractTests",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "Missing RGB token: \(name)"]
            )
        }

        return RGB(
            red: try capture(1, from: match, source: source) / 255.0,
            green: try capture(2, from: match, source: source) / 255.0,
            blue: try capture(3, from: match, source: source) / 255.0
        )
    }

    private func capture(
        _ index: Int,
        from match: NSTextCheckingResult,
        source: String
    ) throws -> Double {
        guard let range = Range(match.range(at: index), in: source),
              let value = Double(source[range])
        else {
            throw NSError(
                domain: "VisualContrastContractTests",
                code: 2,
                userInfo: [NSLocalizedDescriptionKey: "Invalid RGB capture at index \(index)"]
            )
        }
        return value
    }

    private func contrastRatio(_ lhs: RGB, _ rhs: RGB) -> Double {
        let left = relativeLuminance(lhs)
        let right = relativeLuminance(rhs)
        return (max(left, right) + 0.05) / (min(left, right) + 0.05)
    }

    private func relativeLuminance(_ color: RGB) -> Double {
        0.2126 * linearized(color.red)
            + 0.7152 * linearized(color.green)
            + 0.0722 * linearized(color.blue)
    }

    private func linearized(_ component: Double) -> Double {
        if component <= 0.04045 {
            return component / 12.92
        }
        return pow((component + 0.055) / 1.055, 2.4)
    }

    private func file(_ relativePath: String) throws -> String {
        try String(
            contentsOf: repositoryRoot.appendingPathComponent(relativePath),
            encoding: .utf8
        )
    }

    private func source(_ relativePath: String) throws -> String {
        try file(relativePath)
    }

    private var repositoryRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }
}
