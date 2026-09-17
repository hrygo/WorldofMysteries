import Foundation
import ImageIO
import Testing
@testable import WorldOfMysteriesCore

@Suite("Premium Artwork Contracts")
struct PremiumArtworkContractTests {
    @Test("world artwork registry covers the six approved semantic scene families")
    func worldArtworkRegistryCoverage() {
        #expect(WOMWorldArtworkAsset.allCases.count == 6)
        #expect(Set(WOMWorldArtworkAsset.allCases.map(\.rawValue)).count == 6)

        for asset in WOMWorldArtworkAsset.allCases {
            #expect(asset.runtimeAssetName.hasPrefix("wom.art."))
            #expect(asset.assetName(for: .sceneRuntime) == asset.runtimeAssetName)
            #expect(asset.assetName(for: .wideHeader) == asset.wideHeaderAssetName)
            #expect(asset.assetName(for: .artifactThumbnail) == nil)
            #expect(asset.assetName(for: .artifactDetail) == nil)
        }
    }

    @Test("all 15 Artifact IDs map one-to-one to premium artwork identities")
    func artifactArtworkRegistryCoverage() {
        #expect(ArtifactID.allCases.count == 15)
        #expect(WOMArtifactArtworkAsset.allCases.count == 15)

        let mapped = ArtifactID.allCases.map(\.artworkAsset)
        #expect(Set(mapped.map(\.rawValue)).count == 15)
        #expect(Set(mapped.map(\.rawValue)) == Set(WOMArtifactArtworkAsset.allCases.map(\.rawValue)))
    }

    @Test("Artifact runtime variants can never resolve to a production master")
    func artifactRuntimeVariantsExcludeMasters() {
        for asset in WOMArtifactArtworkAsset.allCases {
            #expect(asset.thumbnailAssetName.hasSuffix(".thumbnail"))
            #expect(asset.detailAssetName.hasSuffix(".detail"))
            #expect(asset.assetName(for: .artifactThumbnail) == asset.thumbnailAssetName)
            #expect(asset.assetName(for: .artifactDetail) == asset.detailAssetName)
            #expect(asset.assetName(for: .sceneRuntime) == nil)
            #expect(asset.assetName(for: .wideHeader) == nil)
            #expect(!asset.thumbnailAssetName.contains(".master"))
            #expect(!asset.detailAssetName.contains(".master"))
        }
    }

    @Test("runtime surfaces consume all six typed scene artwork identities")
    func runtimeSurfacesUseTypedSceneArtwork() throws {
        let contentView = try source("ContentView.swift")
        let ritual = try source("Components/BronzeAltarPrayerCard.swift")
        let chronicle = try source("Components/NarrativeChronicleView.swift")
        let worldline = try source("Components/WorldlineNodeView.swift")
        let artifactShowcase = try source("Artifacts/ArtifactShowcaseView.swift")

        #expect(contentView.contains("WOMWorldArtworkAsset.worldHero.runtimeAssetName"))
        #expect(contentView.contains("WOMWorldArtworkAsset.grayFog.wideHeaderAssetName"))
        #expect(ritual.contains("WOMWorldArtworkAsset.ritualAltar.runtimeAssetName"))
        #expect(chronicle.contains("WOMWorldArtworkAsset.codexArchive.runtimeAssetName"))
        #expect(worldline.contains("WOMWorldArtworkAsset.fateWorldline.runtimeAssetName"))
        #expect(artifactShowcase.contains("WOMWorldArtworkAsset.artifactVault.wideHeaderAssetName"))
    }

    @Test("catalog contains no unregistered runtime premium artwork")
    func catalogHasNoOrphanPremiumArtwork() throws {
        let catalog = try catalogArtworkNames()
        let declared = declaredRuntimeArtworkNames
        #expect(catalog.isSubset(of: declared))
    }

    @Test("present premium artwork derivatives match approved runtime pixel contracts")
    func presentArtworkDerivativesMatchRuntimePixelContracts() throws {
        for directory in try catalogArtworkDirectories() {
            let assetName = String(directory.lastPathComponent.dropLast(".imageset".count))
            let expected = try #require(expectedPixelSize(for: assetName))
            let payloads = try imagesetPayloadURLs(in: directory)

            #expect(!payloads.isEmpty, "\(assetName) must reference a runtime image payload")

            for payload in payloads {
                let actual = try pixelSize(of: payload)
                #expect(
                    actual.width == expected.width && actual.height == expected.height,
                    "\(assetName) expected \(expected.width)×\(expected.height), got \(actual.width)×\(actual.height)"
                )
            }
        }
    }

    private func source(_ relativePath: String) throws -> String {
        try String(
            contentsOf: appSourceURL.appendingPathComponent(relativePath),
            encoding: .utf8
        )
    }

    private var appSourceURL: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("WorldOfMysteries", isDirectory: true)
    }

    private var assetsCatalogURL: URL {
        appSourceURL.appendingPathComponent("Assets.xcassets", isDirectory: true)
    }

    private var declaredRuntimeArtworkNames: Set<String> {
        let world = WOMWorldArtworkAsset.allCases.flatMap {
            [$0.runtimeAssetName, $0.wideHeaderAssetName]
        }
        let artifacts = WOMArtifactArtworkAsset.allCases.flatMap {
            [$0.thumbnailAssetName, $0.detailAssetName]
        }
        return Set(world + artifacts)
    }

    private func catalogArtworkNames() throws -> Set<String> {
        Set(try catalogArtworkDirectories().map {
            String($0.lastPathComponent.dropLast(".imageset".count))
        })
    }

    private func catalogArtworkDirectories() throws -> [URL] {
        try FileManager.default.contentsOfDirectory(
            at: assetsCatalogURL,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        )
        .filter { url in
            let name = url.lastPathComponent
            return name.hasPrefix("wom.art.") && name.hasSuffix(".imageset")
        }
    }

    private func imagesetPayloadURLs(in directory: URL) throws -> [URL] {
        struct Contents: Decodable {
            struct ImageEntry: Decodable {
                let filename: String?
            }
            let images: [ImageEntry]
        }

        let manifestURL = directory.appendingPathComponent("Contents.json")
        let contents = try JSONDecoder().decode(Contents.self, from: Data(contentsOf: manifestURL))
        return contents.images.compactMap(\.filename).map(directory.appendingPathComponent)
    }

    private func pixelSize(of url: URL) throws -> (width: Int, height: Int) {
        let source = try #require(CGImageSourceCreateWithURL(url as CFURL, nil))
        let properties = try #require(
            CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
        )
        let width = try #require(properties[kCGImagePropertyPixelWidth] as? Int)
        let height = try #require(properties[kCGImagePropertyPixelHeight] as? Int)
        return (width, height)
    }

    private func expectedPixelSize(for assetName: String) -> (width: Int, height: Int)? {
        if assetName.hasPrefix("wom.art.artifact.") {
            if assetName.hasSuffix(".thumbnail") { return (512, 512) }
            if assetName.hasSuffix(".detail") { return (1024, 1024) }
            return nil
        }

        if assetName.hasPrefix("wom.art.world.") || assetName.hasPrefix("wom.art.scene.") {
            if assetName.hasSuffix(".wide") { return (2400, 900) }
            return (2560, 1600)
        }

        return nil
    }
}
