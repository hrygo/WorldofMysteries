import SwiftUI

@main
struct WorldOfMysteriesApp: App {
    @State private var appState = AppState()
    @State private var currentNavigation: NavigationItem = .fate
    @State private var isSidebarCollapsed: Bool = false

    var body: some Scene {
        WindowGroup {
            ContentView(
                currentNavigation: $currentNavigation,
                isSidebarCollapsed: $isSidebarCollapsed
            )
            .environment(appState)
        }
        .commands {
            AppMenuBarCommands(
                currentNavigation: $currentNavigation,
                isSidebarCollapsed: $isSidebarCollapsed,
                onAdviceRequested: {
                    // 激活命运干预焦点
                },
                onReconnectEngine: {
                    Task {
                        await appState.startAndConnect()
                    }
                }
            )
        }
    }
}
