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

    @Test("sidebar gallery uses live bindings instead of frozen constant snapshots")
    func sidebarGalleryUsesLiveBindings() throws {
        let source = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryWorldGroup.swift"
        )

        #expect(source.contains("selection: $selection"))
        #expect(source.contains("isCollapsed: $isCollapsed"))
        #expect(source.contains("当前选择：\\(selection.localizedTitle)"))
        #expect(!source.contains("selection: .constant(.fate)"))
        #expect(!source.contains("isCollapsed: .constant(isCollapsed)"))
    }

    @Test("control specimens expose observable local feedback instead of no-op examples")
    func controlSpecimensExposeFeedback() throws {
        let primitives = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryPrimitivesSection.swift"
        )
        let interactions = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryInteractionSpecimenSection.swift"
        )

        #expect(primitives.contains("@State private var actionCount"))
        #expect(primitives.contains("recordAction("))
        #expect(primitives.contains("控件已响应"))
        #expect(interactions.contains("@State private var controlActionCount"))
        #expect(interactions.contains("recordControlAction("))
        #expect(interactions.contains("最近交互"))
    }

    @Test("gallery specimens prefer adaptive composition under width pressure")
    func gallerySpecimensUseAdaptiveComposition() throws {
        let primitives = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryPrimitivesSection.swift"
        )
        let interactions = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryInteractionSpecimenSection.swift"
        )

        #expect(primitives.contains("LazyVGrid("))
        #expect(primitives.contains("WOMAdaptivePair("))
        #expect(interactions.contains("LazyVGrid("))
        #expect(interactions.contains("ViewThatFits(in: .horizontal)"))
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
