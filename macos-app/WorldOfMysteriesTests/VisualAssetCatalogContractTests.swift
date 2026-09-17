import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Visual Asset Catalog Contracts")
struct VisualAssetCatalogContractTests {
    @Test("typed custom icon registries exactly match wom.icon imagesets")
    func customIconRegistryMatchesCatalog() throws {
        let registered = Set(WOMIconAsset.allCases.map(\.rawValue))
            .union(WOMNavigationIconAsset.allCases.map(\.rawValue))
        let catalog = try catalogIconNames()

        #expect(catalog == registered)
    }

    @Test("every custom icon remains a template-preserved SVG")
    func customIconsRemainTemplateVectors() throws {
        let registered = Set(WOMIconAsset.allCases.map(\.rawValue))
            .union(WOMNavigationIconAsset.allCases.map(\.rawValue))

        for assetName in registered.sorted() {
            let imagesetURL = assetsCatalogURL
                .appendingPathComponent("\(assetName).imageset", isDirectory: true)
            #expect(FileManager.default.fileExists(atPath: imagesetURL.path), "Missing imageset for \(assetName)")

            let contents = try decodeContents(at: imagesetURL.appendingPathComponent("Contents.json"))
            #expect(contents.properties?.templateRenderingIntent == "template", "\(assetName) must render as template")
            #expect(contents.properties?.preservesVectorRepresentation == true, "\(assetName) must preserve vector representation")

            let svgNames = contents.images.compactMap(\.filename).filter { $0.lowercased().hasSuffix(".svg") }
            #expect(!svgNames.isEmpty, "\(assetName) must reference an SVG")

            for svgName in svgNames {
                #expect(
                    FileManager.default.fileExists(
                        atPath: imagesetURL.appendingPathComponent(svgName).path
                    ),
                    "Missing SVG \(svgName) for \(assetName)"
                )
            }
        }
    }

    @Test("texture registry points to real catalog resources without duplicate aliases")
    func textureRegistryMatchesCatalog() throws {
        for texture in WOMTextureAsset.allCases {
            let imagesetURL = assetsCatalogURL
                .appendingPathComponent("\(texture.rawValue).imageset", isDirectory: true)
            #expect(FileManager.default.fileExists(atPath: imagesetURL.path), "Missing texture imageset \(texture.rawValue)")

            let contents = try decodeContents(at: imagesetURL.appendingPathComponent("Contents.json"))
            let filenames = contents.images.compactMap(\.filename)
            #expect(!filenames.isEmpty, "Texture \(texture.rawValue) must contain a physical resource")

            for filename in filenames {
                #expect(
                    FileManager.default.fileExists(
                        atPath: imagesetURL.appendingPathComponent(filename).path
                    ),
                    "Missing texture payload \(filename) for \(texture.rawValue)"
                )
            }
        }

        #expect(WOMTextureAsset.foolVeil.rawValue == WOMTextureAsset.grayFogSoft.rawValue)
        #expect(WOMTextureAsset.gold.rawValue == WOMTextureAsset.agedGold.rawValue)
    }

    @Test("standard platform action glyphs are not duplicated as custom imagesets")
    func platformActionsStayInSFSymbols() throws {
        let forbiddenCustomCopies: Set<String> = [
            "wom.icon.add",
            "wom.icon.remove",
            "wom.icon.edit",
            "wom.icon.search",
            "wom.icon.close",
            "wom.icon.back",
            "wom.icon.favorite",
            "wom.icon.more",
        ]
        let catalog = try catalogIconNames()

        #expect(catalog.isDisjoint(with: forbiddenCustomCopies))
    }

    private var assetsCatalogURL: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("WorldOfMysteries", isDirectory: true)
            .appendingPathComponent("Assets.xcassets", isDirectory: true)
    }

    private func catalogIconNames() throws -> Set<String> {
        let entries = try FileManager.default.contentsOfDirectory(
            at: assetsCatalogURL,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        )

        return Set(entries.compactMap { url in
            let name = url.lastPathComponent
            guard name.hasPrefix("wom.icon."), name.hasSuffix(".imageset") else {
                return nil
            }
            return String(name.dropLast(".imageset".count))
        })
    }

    private func decodeContents(at url: URL) throws -> AssetContents {
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(AssetContents.self, from: data)
    }
}

private struct AssetContents: Decodable {
    struct ImageEntry: Decodable {
        let filename: String?
    }

    struct Properties: Decodable {
        let preservesVectorRepresentation: Bool?
        let templateRenderingIntent: String?

        enum CodingKeys: String, CodingKey {
            case preservesVectorRepresentation = "preserves-vector-representation"
            case templateRenderingIntent = "template-rendering-intent"
        }
    }

    let images: [ImageEntry]
    let properties: Properties?
}
