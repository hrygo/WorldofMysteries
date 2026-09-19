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

    @Test("visual-system controls report activation instead of swallowing clicks")
    func visualSystemControlsReportActivation() throws {
        let source = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryVisualSystemSection.swift"
        )

        #expect(source.contains("@State private var visualActionCount"))
        #expect(source.contains("recordVisualAction("))
        #expect(source.contains("最近操作"))
        #expect(!source.contains("Button(\"主操作\") {}"))
        #expect(!source.contains("Button(\"危险操作\") {}"))
        #expect(!source.contains("actionTitle: \"查看原因\"\n                ) {}"))
    }

    @Test("gallery shell lazily hosts heavy sections and keeps section order unambiguous")
    func galleryShellIsLazyAndNumbered() throws {
        let gallery = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryView.swift"
        )
        let recovery = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryControlRecoverySection.swift"
        )
        let artifact = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryArtifactGroup.swift"
        )
        let visual = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryVisualSystemSection.swift"
        )

        #expect(gallery.contains("LazyVStack(alignment: .leading"))
        #expect(gallery.contains("真实组件优先 · 可交互 specimen"))
        #expect(recovery.contains("12 · 控件恢复与反馈边界"))
        #expect(artifact.contains("13 · 特殊物品玩法组件"))
        #expect(visual.contains("recordVisualAction(\"查看完整诊断\")"))
        #expect(visual.contains("recordVisualAction(\"压力样例操作\")"))
    }

    @Test("production component callbacks are wired in gallery instead of left disabled")
    func productionCallbacksAreWired() throws {
        let interactions = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryInteractionGroup.swift"
        )
        let world = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryWorldGroup.swift"
        )

        #expect(interactions.contains("onVoiceTapped:"))
        #expect(interactions.contains("onSubmitAdvice:"))
        #expect(interactions.contains("onNodeTapped:"))
        #expect(interactions.contains("onSelect:"))
        #expect(interactions.contains("ListeningRingView(state: .idle) {"))
        #expect(world.contains("onTapStar:"))
        #expect(world.contains("onChantPrayer:"))
        #expect(world.contains("onVoiceAdviceTapped:"))
        #expect(world.contains("TingenCityDossierCard { location in"))
        #expect(world.contains("BacklundMetropolisCard { district in"))
    }

    @Test("standalone production views missing from the old gallery now have contextual showcases")
    func missingProductionViewsAreShowcased() throws {
        let interactions = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryInteractionGroup.swift"
        )
        let world = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryWorldGroup.swift"
        )

        #expect(interactions.contains("TarotCardView(stage: .unknown)"))
        #expect(interactions.contains("TarotCardView(stage: .established)"))
        #expect(interactions.contains("NarrativeChronicleView("))
        #expect(interactions.contains("onReplayAudio:"))
        #expect(world.contains("WOMSceneHeroHeader("))
        #expect(world.contains("scene: .worldObservation"))
    }

    @Test("specimen stage provides context chrome without taking over component state")
    func specimenStageContract() throws {
        let source = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGallerySpecimenStage.swift"
        )

        #expect(source.contains("enum ComponentGallerySpecimenMode"))
        #expect(source.contains("case live"))
        #expect(source.contains("case stateMatrix"))
        #expect(source.contains("ViewThatFits(in: .horizontal)"))
        #expect(source.contains("private let controls: Controls"))
    }

    @Test("high-value interactive specimens expose replayable reset paths")
    func interactiveSpecimensAreReplayable() throws {
        let source = try file(
            "macos-app/WorldOfMysteries/Components/ComponentGalleryInteractionGroup.swift"
        )

        #expect(source.contains("Button(\"重置仪轨\")"))
        #expect(source.contains(".id(scrySessionID)"))
        #expect(source.contains("scrySessionID = UUID()"))
        #expect(source.contains("Button(\"重置选择\")"))
        #expect(source.contains("ComponentGallerySpecimenStage("))
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
