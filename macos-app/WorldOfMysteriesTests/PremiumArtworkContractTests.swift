import Foundation
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

    @Test("catalog contains no unregistered runtime premium artwork")
    func catalogHasNoOrphanPremiumArtwork() throws {
        let catalog = try catalogArtworkNames()
        let declared = declaredRuntimeArtworkNames
        #expect(catalog.isSubset(of: declared))
    }

    private var assetsCatalogURL: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("WorldOfMysteries", isDirectory: true)
            .appendingPathComponent("Assets.xcassets", isDirectory: true)
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
        let entries = try FileManager.default.contentsOfDirectory(
            at: assetsCatalogURL,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        )

        return Set(entries.compactMap { url in
            let name = url.lastPathComponent
            guard name.hasPrefix("wom.art."), name.hasSuffix(".imageset") else {
                return nil
            }
            return String(name.dropLast(".imageset".count))
        })
    }
}
