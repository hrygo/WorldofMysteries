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

    @Test("critical production navigation surfaces no longer fall back to legacy icon strings")
    func criticalProductionViewsUseTypedNavigationIcons() throws {
        let root = repositoryRoot
        let sidebar = try String(
            contentsOf: root
                .appendingPathComponent("macos-app/WorldOfMysteries/Components/AppSidebarView.swift"),
            encoding: .utf8
        )
        let content = try String(
            contentsOf: root
                .appendingPathComponent("macos-app/WorldOfMysteries/ContentView.swift"),
            encoding: .utf8
        )

        #expect(!sidebar.contains("Image(systemName: item.systemIcon)"))
        #expect(!content.contains("Image(systemName: currentNavigation.systemIcon)"))
        #expect(sidebar.contains("item.iconSource"))
        #expect(content.contains("currentNavigation.iconSource"))
    }

    private var repositoryRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }
}
