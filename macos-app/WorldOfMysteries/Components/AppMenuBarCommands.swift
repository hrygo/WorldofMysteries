import SwiftUI

/// macOS 顶层系统菜单栏组件（集成神秘学专属指令、导航快速跳转与快捷键系统）
public struct AppMenuBarCommands: Commands {
    @Binding public var currentNavigation: NavigationItem
    @Binding public var isSidebarCollapsed: Bool
    public var onAdviceRequested: () -> Void
    public var onReconnectEngine: () -> Void
    
    public init(
        currentNavigation: Binding<NavigationItem>,
        isSidebarCollapsed: Binding<Bool>,
        onAdviceRequested: @escaping () -> Void = {},
        onReconnectEngine: @escaping () -> Void = {}
    ) {
        self._currentNavigation = currentNavigation
        self._isSidebarCollapsed = isSidebarCollapsed
        self.onAdviceRequested = onAdviceRequested
        self.onReconnectEngine = onReconnectEngine
    }
    
    public var body: some Commands {
        // 1. 视图与侧边栏折叠控制
        SidebarCommands()
        
        // 2. 导航快速跳转菜单 (⌘1 ~ ⌘9)
        CommandMenu("导航 (Navigation)") {
            ForEach(NavigationItem.allCases) { item in
                Button {
                    currentNavigation = item
                } label: {
                    Label {
                        Text(item.localizedTitle)
                    } icon: {
                        WOMIcon(source: item.iconSource, size: .compact)
                    }
                }
                .keyboardShortcut(KeyEquivalent(Character(item.shortcutNumber)), modifiers: .command)
            }
            
            Divider()
            
            Button(isSidebarCollapsed ? "展开侧边栏" : "折叠侧边栏") {
                withAnimation(DesignTokens.Motion.smoothSpring) {
                    isSidebarCollapsed.toggle()
                }
            }
            .keyboardShortcut("s", modifiers: [.option, .command])
        }
        
        // 3. 诡秘世界专属神秘学操作菜单
        CommandMenu("神秘学 (Mysticism)") {
            Button("传达干预建议 (Advice)...") {
                currentNavigation = .fate
                onAdviceRequested()
            }
            .keyboardShortcut("k", modifiers: .command)
            
            Button("翻阅调查笔记与灵摆占卜") {
                currentNavigation = .notes
            }
            .keyboardShortcut("p", modifiers: .command)
            
            Button("进入组件全景画廊") {
                currentNavigation = .gallery
            }
            .keyboardShortcut("g", modifiers: .command)
            
            Divider()
            
            Button("重连本地引擎 Local Engine (IPC)") {
                onReconnectEngine()
            }
            .keyboardShortcut("r", modifiers: [.option, .command])
        }
    }
}
