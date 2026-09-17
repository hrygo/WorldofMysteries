# Visual Asset System — Wave D / Batch 19：Keyboard / Navigation Contract

> 分支：`feat/wom-visual-system-wave-d`  
> 状态：STRUCTURAL CONTRACTS IMPLEMENTED

## 1. 目标

在继续调整 macOS 菜单/Focus 行为之前，先锁定当前产品导航的结构事实，避免视觉重构意外改变信息架构。

## 2. 已固化的契约

新增 `VisualNavigationContractTests.swift`：

1. 一级导航固定为 9 个入口；
2. `shortcutNumber` 必须唯一覆盖 `1...9`；
3. `NavigationSection` 展开后必须恰好覆盖全部一级入口，不能重复或遗漏；
4. `AppSidebarView` 不得退回 `Image(systemName: item.systemIcon)`；
5. `ContentView` 的导航 placeholder 不得退回 `currentNavigation.systemIcon`；
6. 两个关键生产入口必须继续使用 `iconSource` typed semantics。

## 3. 为什么先做结构测试

键盘命令、菜单命令与 Sidebar shortcut 提示必须共享同一信息架构事实。先锁定 `NavigationItem` / `NavigationSection` / `shortcutNumber`，后续即使调整 `Commands` 或 Focus 路由，也能避免：

- ⌘数字重复；
- 菜单与 Sidebar 显示不一致；
- 某入口被 Section 漏掉；
- typed icon 迁移后又退回 legacy raw string。

## 4. 下一步

下一步审计 `AppMenuBarCommands` 与 App scene 的真实键盘命令绑定：

- 确认 ⌘1–⌘9 是否全部由同一 `NavigationItem` 事实源驱动；
- 确认 Sidebar collapse/expand 的快捷键与 help 文案一致；
- 如发现重复硬编码，再做最小重构；
- 不自行创造新的快捷键体系。
