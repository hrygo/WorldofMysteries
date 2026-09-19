import Foundation
import Testing
@testable import WorldOfMysteriesCore

/// 场景美术内建契约。
///
/// 这些断言的主题只有一条：已批准的 W1–W6 与 15 件神器美术必须出现在**真实游戏场景**里，
/// 而不是只存在于运行时校验窗口或组件画廊。
@Suite("Scene Artwork Integration")
struct SceneArtworkIntegrationTests {
    @Test("every approved world and scene artwork family is bound to a production scene")
    func sceneRegistryCoversAllSixWorldArtworks() {
        let declared = WOMSceneArtworkRegistry.coveredAssets
        let approved = Set(WOMWorldArtworkAsset.allCases)

        #expect(declared == approved)
    }

    @Test("scene declarations only reference runtime-loadable derivatives")
    func sceneDeclarationsStayOnRuntimeDerivatives() {
        for declaration in WOMSceneArtworkRegistry.all {
            #expect(declaration.asset.assetName(for: declaration.variant) != nil)
            // 页头场景带一律用 wide 派生图：未裁切的 16:10 原图在页头里会被压掉主体。
            #expect(declaration.variant == .wideHeader)
            #expect(declaration.assetName.hasSuffix(".wide"))
            #expect(!declaration.assetName.contains("master"))
            #expect(declaration.assetName == declaration.asset.assetName(for: declaration.variant))
        }
    }

    @Test("navigation only claims scene art where an approved scene asset exists")
    func navigationSceneBindingsStayHonest() {
        let bound = NavigationItem.allCases.compactMap(WOMSceneArtworkRegistry.scene(for:))

        #expect(Set(bound.map(\.rawValue)).count == bound.count)
        #expect(WOMSceneArtworkRegistry.scene(for: .world) == .worldObservation)
        #expect(WOMSceneArtworkRegistry.scene(for: .character) == .characterCodex)
        #expect(WOMSceneArtworkRegistry.scene(for: .storyBook) == .narrativeArchive)
        #expect(WOMSceneArtworkRegistry.scene(for: .worldline) == .worldlineAtlas)
        #expect(WOMSceneArtworkRegistry.scene(for: .notes) == .investigationNotes)
        // `.cards` / `.settings` 没有语义相符的已批准场景资产：宁可留白，也不套错图。
        #expect(WOMSceneArtworkRegistry.scene(for: .cards) == nil)
        #expect(WOMSceneArtworkRegistry.scene(for: .settings) == nil)
    }

    @Test("production navigation mounts the scene hero header for every scene it declares")
    func contentViewMountsSceneHeroHeaders() throws {
        let content = try source("macos-app/WorldOfMysteries/ContentView.swift")

        #expect(content.contains("sceneHeroHeader"))
        #expect(content.contains("WOMSceneHeroHeader("))
        #expect(content.contains("WOMSceneArtworkRegistry.scene(for: currentNavigation)"))
    }

    @Test("fate scene surfaces the whole fifteen-item artifact library")
    func fateSceneSurfacesTheArtifactLibrary() throws {
        let fate = try source("macos-app/WorldOfMysteries/Artifacts/ArtifactFateInterventionView.swift")

        #expect(fate.contains("WOMSceneHeroHeader("))
        #expect(fate.contains("scene: .artifactLibrary"))
        #expect(fate.contains("ForEach(ArtifactRegistry.all)"))
        #expect(fate.contains("descriptor.id.artworkAsset.thumbnailAssetName"))
    }

    @Test("all fifteen artifact identities carry consumable runtime artwork")
    func artifactArtworkReachability() throws {
        let shell = try source("macos-app/WorldOfMysteries/Artifacts/ArtifactUIPrimitivesCore.swift")
        let showcase = try source("macos-app/WorldOfMysteries/Artifacts/ArtifactShowcaseView.swift")

        #expect(Set(ArtifactID.allCases.map(\.artworkAsset.rawValue)).count == 15)
        // 详情图与缩略图各自至少有一个生产消费点，且都不是校验窗口。
        #expect(shell.contains("artifactID.artworkAsset.detailAssetName"))
        #expect(showcase.contains("descriptor.id.artworkAsset.thumbnailAssetName"))
    }

    @Test("scene hero header keeps artwork decorative and identity textual")
    func sceneHeroHeaderStaysTextFirst() throws {
        let header = try source("macos-app/WorldOfMysteries/Components/WOMSceneHeroHeader.swift")

        #expect(header.contains("@Environment(\\.accessibilityReduceTransparency)"))
        #expect(header.contains("WOMArtworkScrim(edge: .leading"))
        #expect(header.contains("ViewThatFits(in: .horizontal)"))
        #expect(header.contains("fallback: .icon(declaration.fallbackIcon)"))
        #expect(!header.contains(".accessibilityLabel("))
    }

    private func source(_ relativePath: String) throws -> String {
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
