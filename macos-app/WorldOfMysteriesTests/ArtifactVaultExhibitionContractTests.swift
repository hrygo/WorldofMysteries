import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Artifact Vault Exhibition Contracts")
struct ArtifactVaultExhibitionContractTests {
    @Test("vault is an exhibition hierarchy rather than a flat component selector")
    func exhibitionHierarchy() throws {
        let source = try file(
            "macos-app/WorldOfMysteries/Artifacts/ArtifactShowcaseView.swift"
        )

        #expect(source.contains("神器展览 · Artifact Vault"))
        #expect(source.contains("collectionShelf"))
        #expect(source.contains("exhibitionDossier"))
        #expect(source.contains("liveExhibitStage"))
        #expect(source.contains("CURRENT EXHIBIT"))
        #expect(source.contains("LIVE ARTIFACT WORKBENCH"))
        #expect(!source.contains("Canon Artifact Component Library"))
    }

    @Test("vault preserves all production artifact gameplay components")
    func productionComponentsRemainCanonical() throws {
        let source = try file(
            "macos-app/WorldOfMysteries/Artifacts/ArtifactShowcaseView.swift"
        )

        #expect(source.contains("ProbabilityDieArtifactView("))
        #expect(source.contains("ArrodesMirrorArtifactView("))
        #expect(source.contains("AlzuhodQuillArtifactView("))
        #expect(source.contains("TrunsoestBrassBookArtifactView("))
        #expect(source.contains("MagicWishingLampArtifactView("))
        #expect(source.contains("CreepingHungerArtifactView("))
        #expect(source.contains("LeymanoTravelsArtifactView("))
        #expect(source.contains("GroselleTravelsArtifactView("))
        #expect(source.contains("AzikCopperWhistleArtifactView("))
        #expect(source.contains("CardsOfBlasphemyArtifactView("))
        #expect(source.contains("SeaGodScepterArtifactView("))
        #expect(source.contains("StaffOfStarsArtifactView("))
        #expect(source.contains("BoxOfGreatOldOnesArtifactView("))
        #expect(source.contains("DeathKnellArtifactView("))
        #expect(source.contains("UnshadowedCrucifixArtifactView("))
    }

    @Test("vault browsing keeps filtering search adjacency and preview reset local")
    func browsingContract() throws {
        let source = try file(
            "macos-app/WorldOfMysteries/Artifacts/ArtifactShowcaseView.swift"
        )

        #expect(source.contains("Picker(\"物品分组\""))
        #expect(source.contains("TextField(\"搜索神器\""))
        #expect(source.contains("selectAdjacent(offset: -1)"))
        #expect(source.contains("selectAdjacent(offset: 1)"))
        #expect(source.contains("resetShowcase()"))
        #expect(source.contains("genericModel.resetPresentation(keepHistory: false)"))
        #expect(source.contains(".id(showcaseRevision)"))
    }

    @Test("vault preserves responsive and single-scroll ownership")
    func responsiveContract() throws {
        let source = try file(
            "macos-app/WorldOfMysteries/Artifacts/ArtifactShowcaseView.swift"
        )

        #expect(source.contains("ViewThatFits(in: .horizontal)"))
        #expect(source.contains("ScrollView(.horizontal, showsIndicators: false)"))
        #expect(!source.contains("ScrollView {"))
        #expect(source.contains("LazyHStack("))
    }

    @Test("gallery labels the area as an artifact exhibition")
    func galleryLabel() throws {
        let source = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryArtifactGroup.swift"
        )

        #expect(source.contains("13 · 神器展览 (Artifact Vault)"))
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
