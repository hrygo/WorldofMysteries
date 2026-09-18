import Foundation
import Testing
@testable import WorldOfMysteriesCore

/// Guards the surface-compositing and workspace-column contracts that keep the dark canvas readable.
///
/// Background regression this suite exists for: `WOMPanelBackground` used to compose its fill inside
/// a `ZStack`. A flexible `ZStack` root makes SwiftUI lay the background out at the *container* size,
/// so translucent panels (obsidian glass at 80% + texture) painted across the whole workspace column
/// and buried the main content: text looked nearly invisible and components appeared to cover each
/// other. The panel must therefore stay a fill root with bounded overlays.
@Suite("Workspace Surface Compositing Contracts")
struct VisualSurfaceCompositingContractTests {
    @Test("panel background composes from a fill root with bounded overlays")
    func panelBackgroundStaysWellFormed() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/WOMSurfaceStyles.swift")
        let body = strippingComments(
            try declarationBody(of: "public struct WOMPanelBackground: View", in: source)
        )

        #expect(!body.contains("ZStack"))
        #expect(body.contains("fillColor"))
        #expect(body.contains(".overlay"))
        #expect(body.contains(".clipShape(shape)"))
    }

    @Test("texture layers are bounded by their container instead of escaping it")
    func textureLayerStaysBounded() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/WOMSurfaceStyles.swift")
        let body = try declarationBody(of: "public struct WOMTextureLayer: View", in: source)

        #expect(body.contains(".scaledToFill()"))
        #expect(body.contains(".frame(maxWidth: .infinity, maxHeight: .infinity"))
        #expect(body.contains(".clipped()"))
    }

    @Test("workspace column keeps explicit band constraints")
    func workspaceColumnKeepsBandConstraints() throws {
        let source = try file("macos-app/WorldOfMysteries/DesignSystem/WOMWorkspaceLayout.swift")
        let body = try declarationBody(of: "public struct WOMWorkspaceColumn", in: source)

        // 上/下两栏各声明一次固定宽度，中栏独占剩余高度。
        #expect(body.components(separatedBy: ".frame(maxWidth: .infinity)").count - 1 >= 2)
        #expect(body.contains(".frame(maxWidth: .infinity, maxHeight: .infinity)"))
    }

    @Test("production window uses the constrained column and the opaque canvas")
    func productionWindowUsesConstrainedComposition() throws {
        let source = try file("macos-app/WorldOfMysteries/ContentView.swift")

        #expect(source.contains("WOMWorkspaceColumn {"))
        #expect(source.contains(".background(WOMWindowCanvas())"))
        #expect(source.contains(".frame(maxWidth: .infinity, maxHeight: .infinity)"))
        #expect(source.contains(".frame(maxWidth: .infinity, alignment: .leading)"))
    }

    @Test("app declares its dark-only appearance at the scene root")
    func appDeclaresDarkAppearance() throws {
        let source = try file("macos-app/WorldOfMysteries/MyApp.swift")

        #expect(source.contains("NSAppearance(named: .darkAqua)"))
        #expect(source.contains(".preferredColorScheme(.dark)"))
    }

    // MARK: - Source helpers

    /// Drops comment text so documentation may name an anti-pattern without tripping its own guard.
    private func strippingComments(_ source: String) -> String {
        source
            .components(separatedBy: .newlines)
            .map { line in
                guard let commentRange = line.range(of: "//") else { return line }
                return String(line[line.startIndex..<commentRange.lowerBound])
            }
            .joined(separator: "\n")
    }

    /// Extracts a declaration body by scanning from the declaration until braces balance out.
    private func declarationBody(of declaration: String, in source: String) throws -> String {
        guard let start = source.range(of: declaration) else {
            throw NSError(
                domain: "VisualSurfaceCompositingContractTests",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "Missing declaration: \(declaration)"]
            )
        }

        var depth = 0
        var hasOpened = false
        var index = start.lowerBound

        while index < source.endIndex {
            let character = source[index]
            if character == "{" {
                depth += 1
                hasOpened = true
            } else if character == "}" {
                depth -= 1
                if hasOpened && depth == 0 {
                    return String(source[start.lowerBound...index])
                }
            }
            index = source.index(after: index)
        }

        throw NSError(
            domain: "VisualSurfaceCompositingContractTests",
            code: 2,
            userInfo: [NSLocalizedDescriptionKey: "Unbalanced declaration: \(declaration)"]
        )
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
