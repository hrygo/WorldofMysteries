import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Visual QA Source Guards")
struct VisualQASourceGuardTests {
    @Test("production visual source does not use direct system fonts below 10pt")
    func noSubTenPointDirectSystemFonts() throws {
        let regex = try NSRegularExpression(
            pattern: #"\.font\s*\(\s*\.system\s*\(\s*size:\s*([0-9]+(?:\.[0-9]+)?)"#
        )

        var violations: [String] = []
        for fileURL in try productionVisualSwiftFiles() {
            let source = try String(contentsOf: fileURL, encoding: .utf8)
            for (lineNumber, line) in source.components(separatedBy: .newlines).enumerated() {
                guard isProductionCodeLine(line) else { continue }
                let range = NSRange(line.startIndex..<line.endIndex, in: line)
                guard let match = regex.firstMatch(in: line, range: range),
                      let valueRange = Range(match.range(at: 1), in: line),
                      let size = Double(line[valueRange]),
                      size < 10
                else {
                    continue
                }

                violations.append(
                    violation(
                        fileURL: fileURL,
                        lineNumber: lineNumber + 1,
                        detail: "direct system font \(size)pt is below the 10pt floor",
                        line: line
                    )
                )
            }
        }

        expectNoViolations(violations)
    }

    @Test("production visual source does not shrink text to fit")
    func noMinimumScaleFactor() throws {
        let violations = try productionVisualSwiftFiles().flatMap { fileURL in
            try literalViolations(
                in: fileURL,
                literal: ".minimumScaleFactor(",
                detail: "minimumScaleFactor hides layout pressure by shrinking text"
            )
        }

        expectNoViolations(violations)
    }

    @Test("content layout does not use negative padding as a collision fix")
    func noNegativePaddingInContentLayout() throws {
        let regex = try NSRegularExpression(
            pattern: #"\.padding\s*\((?:[^\n\)]*,\s*)?-\s*[^\n\)]+\)"#
        )
        var violations: [String] = []

        for fileURL in try contentLayoutSwiftFiles() {
            let source = try String(contentsOf: fileURL, encoding: .utf8)
            for (lineNumber, line) in source.components(separatedBy: .newlines).enumerated() {
                guard isProductionCodeLine(line) else { continue }
                let range = NSRange(line.startIndex..<line.endIndex, in: line)
                guard regex.firstMatch(in: line, range: range) != nil else { continue }

                violations.append(
                    violation(
                        fileURL: fileURL,
                        lineNumber: lineNumber + 1,
                        detail: "negative padding is not allowed in page/content layout",
                        line: line
                    )
                )
            }
        }

        expectNoViolations(violations)
    }

    @Test("visual layer keeps native SwiftUI window and inspector infrastructure")
    func noCustomAppKitWindowInfrastructure() throws {
        let forbidden = ["NSPanel", "NSWindow", "NSViewRepresentable"]
        var violations: [String] = []

        for fileURL in try productionVisualSwiftFiles() {
            for literal in forbidden {
                violations += try literalViolations(
                    in: fileURL,
                    literal: literal,
                    detail: "custom AppKit window/view bridge requires a separate high-risk architecture review"
                )
            }
        }

        expectNoViolations(violations)
    }

    @Test("source guard scope remains semantic rather than blanket visual bans")
    func guardPolicyAvoidsOverBroadRules() throws {
        let policy = try file(
            "docs/05_UI/visual-assets/Visual_QA_Source_Guards_v1.0.md"
        )

        #expect(policy.contains("不做全局禁止"))
        #expect(policy.contains("`.offset(...)`"))
        #expect(policy.contains("`.lineLimit(1)`"))
        #expect(policy.contains("`.opacity(...)`"))
        #expect(policy.contains("10pt"))
        #expect(policy.contains("focus ring"))
    }

    // MARK: - Scanner

    private func productionVisualSwiftFiles() throws -> [URL] {
        let directoryRoots = [
            repositoryRoot.appendingPathComponent("macos-app/WorldOfMysteries/DesignSystem"),
            repositoryRoot.appendingPathComponent("macos-app/WorldOfMysteries/Components"),
            repositoryRoot.appendingPathComponent("macos-app/WorldOfMysteries/Artifacts"),
        ]
        let explicitFiles = [
            repositoryRoot.appendingPathComponent("macos-app/WorldOfMysteries/ContentView.swift"),
            repositoryRoot.appendingPathComponent("macos-app/WorldOfMysteries/MyApp.swift"),
        ]

        var files: [URL] = []
        for root in directoryRoots {
            files += try recursiveSwiftFiles(at: root)
        }
        files += explicitFiles.filter { FileManager.default.fileExists(atPath: $0.path) }

        return files
            .filter { !$0.path.contains("/WorldOfMysteriesTests/") }
            .sorted { relativePath(for: $0) < relativePath(for: $1) }
    }

    private func contentLayoutSwiftFiles() throws -> [URL] {
        let directoryRoots = [
            repositoryRoot.appendingPathComponent("macos-app/WorldOfMysteries/Components"),
            repositoryRoot.appendingPathComponent("macos-app/WorldOfMysteries/Artifacts"),
        ]
        var files: [URL] = []
        for root in directoryRoots {
            files += try recursiveSwiftFiles(at: root)
        }

        let contentView = repositoryRoot.appendingPathComponent(
            "macos-app/WorldOfMysteries/ContentView.swift"
        )
        if FileManager.default.fileExists(atPath: contentView.path) {
            files.append(contentView)
        }

        return files.sorted { relativePath(for: $0) < relativePath(for: $1) }
    }

    private func recursiveSwiftFiles(at root: URL) throws -> [URL] {
        guard FileManager.default.fileExists(atPath: root.path) else { return [] }
        guard let enumerator = FileManager.default.enumerator(
            at: root,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) else {
            return []
        }

        var files: [URL] = []
        for case let url as URL in enumerator {
            guard url.pathExtension == "swift" else { continue }
            let values = try url.resourceValues(forKeys: [.isRegularFileKey])
            guard values.isRegularFile == true else { continue }
            files.append(url)
        }
        return files
    }

    private func literalViolations(
        in fileURL: URL,
        literal: String,
        detail: String
    ) throws -> [String] {
        let source = try String(contentsOf: fileURL, encoding: .utf8)
        return source.components(separatedBy: .newlines).enumerated().compactMap {
            lineNumber, line in
            guard isProductionCodeLine(line), line.contains(literal) else { return nil }
            return violation(
                fileURL: fileURL,
                lineNumber: lineNumber + 1,
                detail: detail,
                line: line
            )
        }
    }

    private func isProductionCodeLine(_ line: String) -> Bool {
        let trimmed = line.trimmingCharacters(in: .whitespaces)
        return !trimmed.isEmpty
            && !trimmed.hasPrefix("//")
            && !trimmed.hasPrefix("///")
            && !trimmed.hasPrefix("*")
    }

    private func violation(
        fileURL: URL,
        lineNumber: Int,
        detail: String,
        line: String
    ) -> String {
        let snippet = line.trimmingCharacters(in: .whitespacesAndNewlines)
        return "\(relativePath(for: fileURL)):\(lineNumber): \(detail) :: \(snippet)"
    }

    private func expectNoViolations(_ violations: [String]) {
        for violation in violations {
            print("VISUAL_QA_SOURCE_GUARD: \(violation)")
        }
        #expect(violations.isEmpty)
    }

    private func file(_ relativePath: String) throws -> String {
        try String(
            contentsOf: repositoryRoot.appendingPathComponent(relativePath),
            encoding: .utf8
        )
    }

    private func relativePath(for fileURL: URL) -> String {
        let rootPath = repositoryRoot.path.hasSuffix("/")
            ? repositoryRoot.path
            : repositoryRoot.path + "/"
        return fileURL.path.replacingOccurrences(of: rootPath, with: "")
    }

    private var repositoryRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }
}
