import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Visual Typography Contracts")
struct VisualTypographyContractTests {
    @Test("Mystic typography roles keep their readability floors")
    func typographyRoleFloors() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/DesignTokens.swift")

        let minimums: [(name: String, minimum: Double)] = [
            ("gothicDisplay", 32),
            ("displayLarge", 28),
            ("titleLarge", 22),
            ("titleMedium", 18),
            ("titleSmall", 15),
            ("narrativeSubtitle", 16),
            ("bodyLarge", 14),
            ("bodyMedium", 13),
            ("caption", 11),
            ("monoBadge", 11),
        ]

        var failures: [String] = []
        for item in minimums {
            let actual = try systemFontSize(named: item.name, in: source)
            if actual < item.minimum {
                failures.append("Font.Mystic.\(item.name): \(actual)pt < \(item.minimum)pt")
            }
        }

        let cursive = try customFontSize(named: "parchmentCursive", in: source)
        if cursive < 14 {
            failures.append("Font.Mystic.parchmentCursive: \(cursive)pt < 14pt")
        }

        for failure in failures {
            print("VISUAL_QA_TYPOGRAPHY: \(failure)")
        }
        #expect(failures.isEmpty)
    }

    @Test("text rhythm metrics keep readable line spacing")
    func lineSpacingFloors() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/DesignTokens.swift")

        #expect(try scalar(named: "narrativeLineSpacing", in: source) >= 6.0)
        #expect(try scalar(named: "parchmentLineSpacing", in: source) >= 5.0)
        #expect(try scalar(named: "bodyLineSpacing", in: source) >= 4.0)
        #expect(try scalar(named: "titleLineSpacing", in: source) >= 3.0)
        #expect(try scalar(named: "compactLineSpacing", in: source) >= 2.0)
    }

    @Test("body and metadata token floors match the Visual QA contract")
    func contractSpecificFloors() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/DesignTokens.swift")

        #expect(try systemFontSize(named: "bodyMedium", in: source) >= 13)
        #expect(try systemFontSize(named: "caption", in: source) >= 11)
        #expect(try systemFontSize(named: "monoBadge", in: source) >= 11)
    }

    private func systemFontSize(named name: String, in source: String) throws -> Double {
        let escapedName = NSRegularExpression.escapedPattern(for: name)
        let pattern = "public\\s+static\\s+let\\s+\(escapedName)\\s*=\\s*Font\\.system\\(\\s*size:\\s*([0-9.]+)"
        return try firstCapture(pattern: pattern, in: source, description: "system font \(name)")
    }

    private func customFontSize(named name: String, in source: String) throws -> Double {
        let escapedName = NSRegularExpression.escapedPattern(for: name)
        let pattern = "public\\s+static\\s+let\\s+\(escapedName)\\s*=\\s*Font\\.custom\\([^\\n]*?size:\\s*([0-9.]+)"
        return try firstCapture(pattern: pattern, in: source, description: "custom font \(name)")
    }

    private func scalar(named name: String, in source: String) throws -> Double {
        let escapedName = NSRegularExpression.escapedPattern(for: name)
        let pattern = "public\\s+static\\s+let\\s+\(escapedName)\\s*:\\s*CGFloat\\s*=\\s*([0-9.]+)"
        return try firstCapture(pattern: pattern, in: source, description: "scalar \(name)")
    }

    private func firstCapture(
        pattern: String,
        in source: String,
        description: String
    ) throws -> Double {
        let regex = try NSRegularExpression(pattern: pattern)
        let range = NSRange(source.startIndex..<source.endIndex, in: source)
        guard let match = regex.firstMatch(in: source, range: range),
              let captureRange = Range(match.range(at: 1), in: source),
              let value = Double(source[captureRange])
        else {
            throw NSError(
                domain: "VisualTypographyContractTests",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "Missing or invalid \(description)"]
            )
        }
        return value
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
