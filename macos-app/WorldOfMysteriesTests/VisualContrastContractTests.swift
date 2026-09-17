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
            ("textTertiary", "obsidianCard", 4.5),
            ("textGoldAccent", "obsidianCard", 7.0),
            ("textGoldAccent", "deepVoid", 7.0),
            ("brassGoldPrimary", "obsidianCard", 7.0),
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

    private var repositoryRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }
}
