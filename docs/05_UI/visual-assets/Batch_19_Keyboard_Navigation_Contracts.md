# Visual Asset System — Wave D / Batch 19：Keyboard / Navigation Contract

> 分支：`feat/wom-visual-system-wave-d`  
> 状态：IMPLEMENTED / FINAL CI PENDING

## 1. 目标

锁定 macOS 菜单命令、Sidebar、一级导航与 Advice 输入焦点之间的结构事实，避免视觉系统重构后出现重复快捷键、图标语义漂移或“快捷键触发但没有真实焦点”的伪完成。

## 2. 已固化的结构契约

`VisualNavigationContractTests.swift` 当前覆盖：

1. 一级导航固定为 9 个入口；
2. `shortcutNumber` 必须唯一覆盖 `1...9`；
3. `NavigationSection` 展开后必须恰好覆盖全部一级入口，不能重复或遗漏；
4. `AppSidebarView` 不得退回 `Image(systemName: item.systemIcon)`；
5. `ContentView` 的导航 placeholder 不得退回 `currentNavigation.systemIcon`；
6. `AppMenuBarCommands` 不得再读取 `item.systemIcon`，必须使用 `item.iconSource`；
7. ⌘K 的 Advice 操作必须继续连通 scene-scoped focus request 与 `AdviceInputField` 的原生 `@FocusState`。

## 3. 真实 Commands 审计结果

### ⌘1–⌘9

`AppMenuBarCommands` 已经通过：

```swift
ForEach(NavigationItem.allCases) { item in
    ...
    .keyboardShortcut(KeyEquivalent(Character(item.shortcutNumber)), modifiers: .command)
}
```

生成一级导航快捷键，因此**不存在第二套数字快捷键表**。`NavigationItem.allCases + shortcutNumber` 继续是单一事实源，本轮不重写该结构。

### Sidebar 折叠

Sidebar help 文案为 `⌥⌘S`，Commands 同样使用 `Option + Command + S`，当前一致，无需新增平行快捷键。

### Commands 图标

审计发现 Commands 仍读取兼容层 `item.systemIcon`，与 Sidebar 的 typed `item.iconSource` 形成漂移。现已改为：

```swift
Label {
    Text(item.localizedTitle)
} icon: {
    WOMIcon(source: item.iconSource, size: .compact)
}
```

一级导航 Sidebar / placeholder / menu commands 现共享同一 typed visual semantic source。

## 4. ⌘K Advice Focus 修复

原实现中 `AppMenuBarCommands` 会先切换到 `.fate`，但 `MyApp.onAdviceRequested` 只是空注释，因此 ⌘K **不会真正聚焦输入框**。

现采用 scene-scoped request token：

1. `MyApp` 维护 `adviceFocusRequestID`；
2. ⌘K 触发时递增 request ID；
3. WindowGroup 通过 SwiftUI Environment 下发 request ID；
4. `AdviceInputField` 监听环境值变化；
5. TextField 使用原生 `@FocusState` 获得键盘焦点。

不使用 NotificationCenter，不维护第二套焦点状态机，也不改变 Advice ≠ Command 的领域语义。

## 5. 验证原则

- 菜单只负责导航和请求焦点，不直接提交 Advice；
- `NavigationItem` 继续承担一级导航名称、快捷键与 typed icon source；
- TextField 焦点仍由 SwiftUI `@FocusState` 管理；
- 最终编译与行为契约由 `MACOS_APP_P0` 验证。
