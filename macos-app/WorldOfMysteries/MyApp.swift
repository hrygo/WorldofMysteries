import SwiftUI

@main
struct WorldOfMysteriesApp: App {
    @State private var appState = AppState()
    @State private var currentNavigation: NavigationItem = .fate
    @State private var isSidebarCollapsed: Bool = false
    @State private var adviceFocusRequestID: Int = 0

    var body: some Scene {
        WindowGroup {
            ContentView(
                currentNavigation: $currentNavigation,
                isSidebarCollapsed: $isSidebarCollapsed
            )
            .environment(appState)
            .environment(\.adviceFocusRequestID, adviceFocusRequestID)
        }
        .defaultSize(
            width: WOMWindowMetrics.defaultWidth,
            height: WOMWindowMetrics.defaultHeight
        )
        .commands {
            AppMenuBarCommands(
                currentNavigation: $currentNavigation,
                isSidebarCollapsed: $isSidebarCollapsed,
                onAdviceRequested: {
                    adviceFocusRequestID &+= 1
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
