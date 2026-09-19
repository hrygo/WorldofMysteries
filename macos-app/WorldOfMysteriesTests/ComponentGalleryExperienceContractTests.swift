import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Component Gallery Experience Contracts")
struct ComponentGalleryExperienceContractTests {
    @Test("primary pendulum gallery uses the real high-fidelity citrine interaction")
    func primaryPendulumUsesRealComponent() throws {
        let source = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryInteractionGroup.swift"
        )

        #expect(source.contains("CitrinePendulumScryingCard("))
        #expect(source.contains("onScryingTriggered:"))
        #expect(source.contains("WOMAdaptivePair("))
        #expect(!source.contains("SpiritPendulumView("))
    }

    @Test("canonical geography no longer duplicates the pendulum showcase")
    func geographyDoesNotDuplicatePendulum() throws {
        let source = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryWorldGroup.swift"
        )

        #expect(source.contains("原著正典地域档案"))
        #expect(!source.contains("CitrinePendulumScryingCard("))
    }

    @Test("citrine production component remains bound to the real asset and motion path")
    func citrineAssetAndMotionPathRemainConnected() throws {
        let artwork = try file(
            "macos-app/WorldOfMysteries/Components/CitrinePendulumArtwork.swift"
        )
        let card = try file(
            "macos-app/WorldOfMysteries/Components/CitrinePendulumScryingCard.swift"
        )
        let assetContents = try file(
            "macos-app/WorldOfMysteries/Assets.xcassets/PendulumCitrine.imageset/Contents.json"
        )
        let imageURL = repositoryRoot.appendingPathComponent(
            "macos-app/WorldOfMysteries/Assets.xcassets/PendulumCitrine.imageset/pendulum_citrine.jpg"
        )

        #expect(artwork.contains(#"NSImage(named: "PendulumCitrine")"#))
        #expect(card.contains("CitrinePendulumArtwork("))
        #expect(card.contains(".repeatForever(autoreverses: true)"))
        #expect(assetContents.contains("pendulum_citrine.jpg"))
        #expect(FileManager.default.fileExists(atPath: imageURL.path))
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
