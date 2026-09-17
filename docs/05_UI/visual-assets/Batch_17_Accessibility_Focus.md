# Visual Asset System — Wave C / Batch 17：macOS Focus 与 Accessibility State

> Task：`MAC-VISUAL-SYSTEM-WAVE-C`  
> Base：`main@d0de662e4d2af8d607c9014084ee54ebe7b4a9f3`  
> 状态：IMPLEMENTED / FINAL CI RETRY 3

## 1. 目标

Wave C 聚焦 macOS 原生 Focus、高对比度、Differentiate Without Color、inactive appearance 与设计系统回归保障，不扩展领域功能。

## 2. Button Chrome

`WOMButtonStyle`、`WOMIconButtonStyle`、`WOMToolbarButtonStyle` 共享 `WOMButtonChrome`，读取系统 environment：

- `isFocused`
- `appearsActive`
- `colorSchemeContrast`
- `accessibilityDifferentiateWithoutColor`
- `accessibilityReduceMotion`

实现 Focus 外环、Increase Contrast heavy border、Danger/Ritual 非颜色 dash pattern、inactive-window 降低 accent/glow、Reduced Motion 关闭反馈动画。

## 3. Surface / Card Chrome

- `WOMTextureLayer` 在 Reduced Transparency / Increased Contrast 下限制纹理强度；
- `WOMPanelBackground` 在 Increased Contrast 下使用更清晰 semantic stroke，并在后台窗口/高对比度关闭 decorative glow；
- `WOMCardChrome` 的 selected 在 Differentiate Without Color 下增加第二层 inset border，不仅依赖颜色；
- Card hover/selection 动画尊重 Reduced Motion；
- Section Header 与 Divider 在 Increased Contrast 下加强清晰度。

## 4. Component Gallery Accessibility Specimen

新增专门的辅助功能展示区：Tab / Shift-Tab Focus、程序化聚焦、Disabled / Danger / Ritual，以及 Selected / Unselected 非颜色状态对照；并提示切换 macOS 增强对比度、不使用颜色区分、减少动态效果和降低透明度实时观察。

## 5. 语义回归测试

`VisualSystemSemanticTests.swift` 使用 Swift Testing，覆盖：

- `WOMIconSize` = 16 / 20 / 24 / 32；
- `WOMSystemIcon` / `WOMStatusIcon` 映射；
- `WOMTextureAsset` compatibility aliases 与 `semanticKey`；
- `WOMIconAsset` 世界观 registry；
- 9 个 `NavigationItem.iconSource`。

不采用像素截图 golden；视觉状态由 Component Gallery 作为观察入口，语义契约由 Swift Testing 守护。

## 6. 最终 CI 发现与修复记录

### Retry 1

Architecture/Contracts 与 Python 全绿；Swift 6 Test Suite 失败。确认新测试错误导入 `WorldOfMysteries`，而 Swift Package 实际模块为 `WorldOfMysteriesCore`。已修复：

```swift
@testable import WorldOfMysteriesCore
```

### Retry 2

Architecture/Contracts 与 Python 继续全绿；Swift 6 编译已越过模块导入，随后在 `WOMSurfaceStyles.swift` 报告确定性语法错误：`shadowRadius` getter 在 `guard` 之后使用无 `return` 的 `switch`，导致 `missing return in getter expected to return CGFloat`。

修复为显式 switch expression：

```swift
private var shadowRadius: CGFloat {
    guard appearsActive, !isIncreasedContrast else { return 0 }
    return switch tone {
    case .floating: 14
    case .ritual: 7
    case .panel, .card, .parchment: 0
    }
}
```

该修复只纠正 Swift 6 返回语义，不改变视觉设计或产品逻辑。

## 7. 技术原则

SwiftUI environment 是系统状态事实源；不维护平行的 focus/contrast/accessibility 状态机。自定义 `ButtonStyle` 只改视觉，不重写 Button 的平台触发与键盘行为。
