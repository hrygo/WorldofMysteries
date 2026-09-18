import AppKit
import SwiftUI

@main
struct WorldOfMysteriesApp: App {
    @NSApplicationDelegateAdaptor(EngineAppDelegate.self) private var engineDelegate
    @State private var appState = AppState()
    @State private var currentNavigation: NavigationItem = .fate
    @State private var isSidebarCollapsed: Bool = false
    @State private var adviceFocusRequestID: Int = 0

    init() {
        // 视觉系统为暗色单一样式：把窗口背板、标题栏与系统控件一并声明为暗色，
        // 避免系统浅色外观给暗色画布配上浅色窗口装饰与浅色系统控件。
        NSApp?.appearance = NSAppearance(named: .darkAqua)
    }

    var body: some Scene {
        WindowGroup {
            ContentView(
                currentNavigation: $currentNavigation,
                isSidebarCollapsed: $isSidebarCollapsed
            )
            .environment(appState)
            .onAppear { engineDelegate.appState = appState }
            .environment(\.adviceFocusRequestID, adviceFocusRequestID)
            // 视觉系统为暗色单一样式（obsidian 画布 + 黄铜金层级）。
            // 在场景根声明暗色外观，避免系统浅色外观把窗口背板、滚动容器与系统控件
            // 换成浅色表面，从而出现「浅底浅字」一类不可读事故。
            .preferredColorScheme(.dark)
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
