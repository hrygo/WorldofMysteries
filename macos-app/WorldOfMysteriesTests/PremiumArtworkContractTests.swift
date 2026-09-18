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
        let world = try source("Components/BacklundMetropolisCard.swift")
        let fate = try source("Artifacts/ArtifactFateInterventionView.swift")
        let ritual = try source("Components/BronzeAltarPrayerCard.swift")
        let chronicle = try source("Components/NarrativeChronicleView.swift")
        let worldline = try source("Components/WorldlineNodeView.swift")
        let artifactShowcase = try source("Artifacts/ArtifactShowcaseView.swift")

        #expect(world.contains("WOMWorldArtworkAsset.worldHero.wideHeaderAssetName"))
        #expect(fate.contains("WOMWorldArtworkAsset.grayFog.wideHeaderAssetName"))
        #expect(ritual.contains("WOMWorldArtworkAsset.ritualAltar.runtimeAssetName"))
        #expect(chronicle.contains("WOMWorldArtworkAsset.codexArchive.runtimeAssetName"))
        #expect(worldline.contains("WOMWorldArtworkAsset.fateWorldline.runtimeAssetName"))
        #expect(artifactShowcase.contains("WOMWorldArtworkAsset.artifactVault.wideHeaderAssetName"))
    }

    @Test("Artifact selectors consume thumbnail variants with semantic fallback")
    func artifactSelectorsUseThumbnailVariants() throws {
        let gallery = try source("Artifacts/ArtifactShowcaseView.swift")
        let fate = try source("Artifacts/ArtifactFateInterventionView.swift")

        #expect(gallery.contains("artworkAsset.thumbnailAssetName"))
        #expect(fate.contains("artworkAsset.thumbnailAssetName"))
        #expect(gallery.contains("fallback: .systemImage(descriptor.systemIcon)"))
        #expect(fate.contains("fallback: .systemImage(descriptor.systemIcon)"))
    }

    @Test("W1 selected-source contract stays aligned with typed runtime registry")
    func w1ExecutableImageContractAlignment() throws {
        let data = try Data(contentsOf: w1ContractURL)
        let json = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])

        #expect(json["contract_version"] as? Int == 3)
        #expect(json["artwork_id"] as? String == "W1_WORLD_HERO")
        #expect(json["status"] as? String == "LOCKED_SELECTED_SOURCE_FINISHING_PENDING")

        let generation = try #require(json["generation"] as? [String: Any])
        #expect(generation["selected_source_locked"] as? Bool == true)
        #expect(nonEmptyString(generation["generation_id"]))
        #expect(generation["no_more_composition_regeneration_required"] as? Bool == true)
        #expect(
            generation["historical_v2_context_gate"] as? String
                == "superseded_by_art_direction_v3"
        )

        let master = try #require(json["production_master"] as? [String: Any])
        #expect(master["target_width"] as? Int == 4096)
        #expect(master["target_height"] as? Int == 2560)
        #expect(master["runtime_loadable"] as? Bool == false)

        let derivatives = try #require(json["runtime_derivatives"] as? [[String: Any]])
        let byName = Dictionary(
            uniqueKeysWithValues: derivatives.compactMap { entry -> (String, [String: Any])? in
                guard let name = entry["asset_name"] as? String else { return nil }
                return (name, entry)
            }
        )

        let runtimeName = WOMWorldArtworkAsset.worldHero.runtimeAssetName
        let wideName = WOMWorldArtworkAsset.worldHero.wideHeaderAssetName

        let runtime = try #require(byName[runtimeName])
        #expect(runtime["width"] as? Int == 2560)
        #expect(runtime["height"] as? Int == 1600)
        #expect(runtime["derivation"] as? String == "full_frame_downsample_from_master")

        let wide = try #require(byName[wideName])
        #expect(wide["width"] as? Int == 2400)
        #expect(wide["height"] as? Int == 900)
        #expect(
            wide["derivation"] as? String
                == "top_aligned_4096x1536_crop_from_master_then_downsample"
        )
        #expect(wide["crop_anchor"] as? String == "top")

        let composition = try #require(json["composition"] as? [String: Any])
        let wideCrop = try #require(composition["wide_crop"] as? [String: Any])
        #expect(wideCrop["vertical_anchor"] as? String == "top")
        #expect(wideCrop["master_crop_pixels"] as? [Int] == [0, 0, 4096, 1536])

        let crimsonMoon = try #require(json["crimson_moon"] as? [String: Any])
        #expect(crimsonMoon["required"] as? Bool == true)
        #expect(crimsonMoon["must_survive_runtime_wide_crop"] as? Bool == true)
    }

    @Test("shipping W1 assets require complete QA and provenance evidence")
    func shippingW1AssetsRequireEvidence() throws {
        let catalog = try catalogArtworkNames()
        let required = Set([
            WOMWorldArtworkAsset.worldHero.runtimeAssetName,
            WOMWorldArtworkAsset.worldHero.wideHeaderAssetName,
        ])
        let present = catalog.intersection(required)

        guard !present.isEmpty else { return }

        #expect(
            present == required,
            "W1 must ship runtime and wide derivatives atomically from the same approved master"
        )

        let qaData = try Data(contentsOf: w1QAURL)
        let qa = try #require(JSONSerialization.jsonObject(with: qaData) as? [String: Any])
        #expect(qa["final_verdict"] as? String == "PASSED")

        let gates = try #require(qa["gates"] as? [String: Any])
        for gateName in [
            "G0_semantic",
            "G1_canon_atmosphere",
            "G2_composition",
            "G3_structure",
            "G4_production",
            "G5_runtime",
        ] {
            let gate = try #require(gates[gateName] as? [String: Any])
            #expect(gate["status"] as? String == "PASSED", "\(gateName) must pass before W1 ships")
        }

        let provenanceData = try Data(contentsOf: w1ProvenanceURL)
        let provenance = try #require(
            JSONSerialization.jsonObject(with: provenanceData) as? [String: Any]
        )
        #expect(provenance["status"] as? String == "APPROVED")

        let master = try #require(provenance["master"] as? [String: Any])
        #expect(nonEmptyString(master["sha256"]))

        let derivatives = try #require(provenance["derivatives"] as? [[String: Any]])
        let derivativeByName = Dictionary(
            uniqueKeysWithValues: derivatives.compactMap { entry -> (String, [String: Any])? in
                guard let name = entry["asset_name"] as? String else { return nil }
                return (name, entry)
            }
        )

        for assetName in required {
            let derivative = try #require(derivativeByName[assetName])
            #expect(nonEmptyString(derivative["sha256"]), "\(assetName) requires a recorded SHA256")
        }
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

    private var repositoryRootURL: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    private var w1ContractURL: URL {
        repositoryRootURL
            .appendingPathComponent("docs/05_UI/artwork/contracts", isDirectory: true)
            .appendingPathComponent("W1_WORLD_HERO.contract.json")
    }

    private var w1QAURL: URL {
        repositoryRootURL
            .appendingPathComponent("docs/05_UI/artwork/qa", isDirectory: true)
            .appendingPathComponent("W1_WORLD_HERO.qa.json")
    }

    private var w1ProvenanceURL: URL {
        repositoryRootURL
            .appendingPathComponent("docs/05_UI/artwork/provenance", isDirectory: true)
            .appendingPathComponent("W1_WORLD_HERO.provenance.json")
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

    private func nonEmptyString(_ value: Any?) -> Bool {
        guard let string = value as? String else { return false }
        return !string.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
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
