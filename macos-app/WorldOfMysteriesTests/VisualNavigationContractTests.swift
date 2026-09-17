import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Visual Navigation Contracts")
struct VisualNavigationContractTests {
    @Test("primary navigation keeps exactly nine stable entries")
    func primaryNavigationCount() {
        #expect(NavigationItem.allCases.count == 9)
    }

    @Test("command shortcuts remain unique and cover command-1 through command-9")
    func shortcutNumbersRemainUnique() {
        let shortcuts = NavigationItem.allCases.map(\.shortcutNumber)
        #expect(Set(shortcuts).count == shortcuts.count)
        #expect(Set(shortcuts) == Set((1...9).map(String.init)))
    }

    @Test("navigation sections cover every primary destination exactly once")
    func sectionsCoverNavigationExactlyOnce() {
        let flattened = NavigationSection.allCases.flatMap(\.items)
        #expect(flattened.count == NavigationItem.allCases.count)
        #expect(Set(flattened.map(\.rawValue)) == Set(NavigationItem.allCases.map(\.rawValue)))
    }

    @Test("critical production navigation surfaces use typed icon sources")
    func criticalProductionViewsUseTypedNavigationIcons() throws {
        let sidebar = try source("macos-app/WorldOfMysteries/Components/AppSidebarView.swift")
        let content = try source("macos-app/WorldOfMysteries/ContentView.swift")
        let commands = try source("macos-app/WorldOfMysteries/Components/AppMenuBarCommands.swift")

        #expect(!sidebar.contains("Image(systemName: item.systemIcon)"))
        #expect(!content.contains("Image(systemName: currentNavigation.systemIcon)"))
        #expect(!commands.contains("item.systemIcon"))
        #expect(sidebar.contains("item.iconSource"))
        #expect(content.contains("currentNavigation.iconSource"))
        #expect(commands.contains("item.iconSource"))
    }

    @Test("command-K advice action stays wired to the scene focus request")
    func adviceFocusCommandIsWired() throws {
        let app = try source("macos-app/WorldOfMysteries/MyApp.swift")
        let commands = try source("macos-app/WorldOfMysteries/Components/AppMenuBarCommands.swift")
        let advice = try source("macos-app/WorldOfMysteries/Components/AdviceInputField.swift")

        #expect(commands.contains("onAdviceRequested()"))
        #expect(app.contains("adviceFocusRequestID &+= 1"))
        #expect(app.contains(".environment(\\.adviceFocusRequestID, adviceFocusRequestID)"))
        #expect(advice.contains("@Environment(\\.adviceFocusRequestID)"))
        #expect(advice.contains(".focused($isTextFieldFocused)"))
        #expect(advice.contains(".onChange(of: adviceFocusRequestID)"))
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
