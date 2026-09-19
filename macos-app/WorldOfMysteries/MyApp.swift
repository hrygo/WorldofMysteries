import AppKit
import SwiftUI

@main
struct WorldOfMysteriesApp: App {
    @NSApplicationDelegateAdaptor(EngineAppDelegate.self) private var engineDelegate
    @State private var appState = AppState()
    @State private var currentNavigation: NavigationItem = .fate
    @State private var isSidebarCollapsed: Bool = false
    @State private var adviceFocusRequestID: Int = 0

    private var galleryRuntimeVerificationEnabled: Bool {
        UserDefaults.standard.bool(
            forKey: ComponentGalleryRuntimeVerificationView.enabledPreferenceKey
        )
    }

    private var primaryWindowWidth: CGFloat {
        guard galleryRuntimeVerificationEnabled else { return WOMWindowMetrics.defaultWidth }
        let requested = UserDefaults.standard.double(
            forKey: ComponentGalleryRuntimeVerificationView.widthPreferenceKey
        )
        return requested > 0 ? CGFloat(requested) : WOMWindowMetrics.defaultWidth
    }

    private var primaryWindowHeight: CGFloat {
        guard galleryRuntimeVerificationEnabled else { return WOMWindowMetrics.defaultHeight }
        let requested = UserDefaults.standard.double(
            forKey: ComponentGalleryRuntimeVerificationView.heightPreferenceKey
        )
        return requested > 0 ? CGFloat(requested) : WOMWindowMetrics.defaultHeight
    }

    init() {
        // 视觉系统为暗色单一样式：把窗口背板、标题栏与系统控件一并声明为暗色，
        // 避免系统浅色外观给暗色画布配上浅色窗口装饰与浅色系统控件。
        NSApp?.appearance = NSAppearance(named: .darkAqua)
    }

    var body: some Scene {
        WindowGroup {
            if galleryRuntimeVerificationEnabled {
                ComponentGalleryRuntimeVerificationView()
            } else {
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
        }
        .defaultSize(
            width: primaryWindowWidth,
            height: primaryWindowHeight
        )
        // G5 运行时取证窗口：把出厂的派生图按未裁切方式呈现，供采集脚本复算。
        Window(
            ArtifactArtworkRuntimeVerificationView.windowTitle,
            id: ArtifactArtworkRuntimeVerificationView.windowID
        ) {
            ArtifactArtworkRuntimeVerificationView()
        }
        // 采集窗口的初始尺寸来自偏好键：抓取脚本按档位写入并重启 App，窗口就以该档位创建。
        // 窗口本身仍是原生可缩放窗口；这里只是让「抓取像素 = 档位 × 背屏倍率」可复算，
        // 而不必依赖 Accessibility 的窗口几何（本机该路径不可用）。
        .defaultSize(
            width: ArtifactArtworkRuntimeVerificationView.preferredWindowSize.width,
            height: ArtifactArtworkRuntimeVerificationView.preferredWindowSize.height
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

        // 场景美术运行时证据采集面（G5）：产品表面用 `.fill` 裁切并叠加 scrim 与透明度，
        // 无法证明「出厂的派生图确实被渲染出来」。该窗口只做未裁切渲染与发布态叠加探针，
        // 供 `docs/05_UI/artwork/tools/` 下的抓取脚本采集可复算的运行时证据。
        Window("场景美术运行时校验", id: SceneArtworkRuntimeVerificationView.windowID) {
            SceneArtworkRuntimeVerificationView()
        }
        .defaultSize(
            width: WOMWindowMetrics.defaultWidth,
            height: WOMWindowMetrics.defaultHeight
        )
    }
}
