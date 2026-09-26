import Foundation
import Testing
@testable import WorldOfMysteriesCore

/// 诚实表达与用户旅程契约。
///
/// 这些断言的共同主题：界面可以说得少，但不能说得不真。
/// 任何一条被打破，都意味着产品重新开始向用户宣称它并不知道的状态。
@Suite("Honest State and Journey Contracts")
struct VisualHonestyContractTests {

    // MARK: - 旅程与上下文

    @Test("advice console exists only in the fate intervention context")
    func adviceConsoleIsContextBound() {
        for item in NavigationItem.allCases {
            #expect(item.showsAdviceConsole == (item == .fate))
        }
    }

    @Test("workspace shell gates the advice console and reserves bottom inset")
    func shellGatesAdviceConsole() throws {
        let content = try source("macos-app/WorldOfMysteries/ContentView.swift")

        #expect(content.contains("if currentNavigation.showsAdviceConsole {"))
        #expect(content.contains("workspaceBottomInset"))
    }

    @Test("planned modules are labelled instead of pretending to work")
    func plannedModulesAreLabelled() throws {
        let content = try source("macos-app/WorldOfMysteries/ContentView.swift")
        let sidebar = try source("macos-app/WorldOfMysteries/Components/AppSidebarView.swift")
        let commands = try source("macos-app/WorldOfMysteries/Components/AppMenuBarCommands.swift")

        #expect(!content.contains("功能占位"))
        #expect(!sidebar.contains("功能占位"))
        #expect(sidebar.contains("规划中"))
        #expect(commands.contains("（规划中）"))
        #expect(content.contains("plannedModuleBlueprint"))
    }

    @Test("navigation badges are data driven rather than fabricated")
    func badgesAreNotFabricated() throws {
        let sidebar = try source("macos-app/WorldOfMysteries/Components/AppSidebarView.swift")
        let content = try source("macos-app/WorldOfMysteries/ContentView.swift")

        #expect(sidebar.contains("badgeCounts: [NavigationItem: Int] = [:]"))
        #expect(!sidebar.contains("[.fate: 2, .worldline: 1]"))
        #expect(!content.contains("badgeCounts"))
    }

    // MARK: - 单一事实源

    @Test("one demo snapshot feeds sidebar status bar and workspace")
    func singleDemoSnapshotSource() throws {
        let sidebar = try source("macos-app/WorldOfMysteries/Components/AppSidebarView.swift")
        let content = try source("macos-app/WorldOfMysteries/ContentView.swift")

        for file in [sidebar, content] {
            #expect(!file.contains("Text(\"85%\")"))
            #expect(!file.contains("Text(\"Seq 9\")"))
            #expect(!file.contains("克莱恩 · 占卜家"))
            #expect(!file.contains("第五纪 · 1349 年"))
        }

        #expect(sidebar.contains("snapshot.spiritualityPercentText"))
        #expect(content.contains("snapshot.sequenceDescription"))
        #expect(content.contains("snapshot.worldTimeLabel"))
    }

    // MARK: - 引擎与四库状态

    @Test("engine readiness is never asserted unconditionally")
    func engineReadinessIsHonest() throws {
        let content = try source("macos-app/WorldOfMysteries/ContentView.swift")
        let state = try source("macos-app/WorldOfMysteries/AppState.swift")
        let client = try source("macos-app/WorldOfMysteries/EngineIPCClient.swift")

        #expect(content.contains("case .scaffoldPreview: \"本地引擎未接入 · 界面为示例数据\""))
        #expect(content.contains("demoDataChip"))
        #expect(client.contains("isScaffoldOnly: Bool { false }"))
        #expect(state.contains("health.worldReady"))
        #expect(state.contains("welcome.capabilities.contains(\"world.home\")"))
        #expect(state.contains(".transportReady"))
        #expect(content.contains("onSubmitAdvice: nil"))
        #expect(!client.contains("Echo mock response"))
        #expect(!content.contains("worldListeningState ="))
        #expect(!content.contains("这些入口承载真实交互"))
        #expect(content.contains("世界询问与语音功能尚未开放"))
    }

    @Test("four-kernel HUD defaults to an unprobed state")
    func databaseHUDDoesNotInventMeasurements() throws {
        let card = try source("macos-app/WorldOfMysteries/Components/DatabaseStatusHUDCard.swift")
        let content = try source("macos-app/WorldOfMysteries/ContentView.swift")

        #expect(card.contains("case notProbed"))
        #expect(card.contains("尚未接入 Local Engine 探针"))
        #expect(content.contains("DatabaseStatusHUDCard(role: role)"))
        #expect(!content.contains("38.2 MB"))
        #expect(!content.contains("isHealthy: true"))
    }

    @Test("unprobed database cards never render an actionable rebuild control")
    func rebuildControlRequiresProbe() throws {
        let card = try source("macos-app/WorldOfMysteries/Components/DatabaseStatusHUDCard.swift")

        #expect(card.contains("if role.isRebuildable, status.isProbed, let onRebuildTapped {"))
    }

    // MARK: - 视觉符号与滚动所有权

    @Test("listening ring keeps the non-technical world symbol")
    func listeningRingAvoidsMicrophonePrimaryVisual() throws {
        let ring = try source("macos-app/WorldOfMysteries/Components/ListeningRingView.swift")

        #expect(!ring.contains("mic"))
        #expect(!ring.contains("Image(systemName:"))
        #expect(ring.contains("glyphCore"))
    }

    @Test("gallery does not own a nested scroll container")
    func galleryHasSingleScrollOwner() throws {
        let gallery = try source("macos-app/WorldOfMysteries/Components/ComponentGalleryView.swift")

        #expect(!gallery.contains("Scroll"))
    }

    // MARK: - 基线字段覆盖

    @Test("fate page surfaces uncertainty pressure cast and consequences")
    func fatePageCoversBaselineFields() throws {
        let content = try source("macos-app/WorldOfMysteries/ContentView.swift")
        let required = [
            "不确定性 (Uncertainty)",
            "压力 (Pressure)",
            "涉及人物 (Involved Characters)",
            "潜在后果 (Potential Consequences)",
        ]

        for field in required {
            #expect(content.contains(field), "Fate page must surface \(field)")
        }
    }

    @Test("world home observes the world instead of showing a single paragraph")
    func worldHomeIsAnObservationSurface() throws {
        let content = try source("macos-app/WorldOfMysteries/ContentView.swift")

        #expect(content.contains("可观察事件"))
        #expect(content.contains("TingenCityDossierCard()"))
        #expect(content.contains("观察者询问"))
    }

    @Test("live first-turn panel stays separate from the demo surfaces")
    func liveFirstTurnPanelIsSeparateFromDemoData() throws {
        let content = try source("macos-app/WorldOfMysteries/ContentView.swift")
        let appState = try source("macos-app/WorldOfMysteries/AppState.swift")
        let panel = try source("macos-app/WorldOfMysteries/StorySessionPanel.swift")

        // The live panel exists, and the demo surfaces keep their honest label.
        #expect(content.contains("StorySessionPanel(model: appState.storyModel)"))
        #expect(content.contains("isShowingDemoData"))
        #expect(appState.contains("public var isShowingDemoData: Bool { true }"))
        // Story entry is gated on the advertised capability and a real world service.
        #expect(appState.contains("handshake.capabilities.contains(\"story.entry.get\")"))
        #expect(appState.contains("guard health.worldReady"))
        // The panel states the verification scope instead of claiming generated narrative.
        #expect(panel.contains("工程验证 · 固定首轮"))
        #expect(panel.contains("不是生成叙事"))
        #expect(panel.contains("语音仍禁用"))
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
