# Visual Asset System — Wave C / Batch 17：macOS Focus 与 Accessibility State

> Task：`MAC-VISUAL-SYSTEM-WAVE-C`  
> Base：`main@d0de662e4d2af8d607c9014084ee54ebe7b4a9f3`  
> 状态：IMPLEMENTED / FINAL CI PENDING

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

新增专门的辅助功能展示区：

- Tab / Shift-Tab 可实测 Focus ring；
- “聚焦主按钮”可程序化移动焦点；
- 同屏展示 Disabled / Danger / Ritual；
- Selected / Unselected 卡片并排验证非颜色选中态；
- 提示用户切换 macOS 增强对比度、不使用颜色进行区分、减少动态效果和降低透明度观察实时结果。

## 5. 语义回归测试

新增 `VisualSystemSemanticTests.swift`，采用 Swift Testing，覆盖：

- `WOMIconSize` = 16 / 20 / 24 / 32；
- `WOMSystemIcon` 核心系统行为映射；
- `WOMStatusIcon` 状态映射；
- `WOMTextureAsset` Wave B compatibility aliases 与 `semanticKey`；
- `WOMIconAsset` 世界观 registry 必需项；
- 9 个 `NavigationItem.iconSource` 类型化来源。

不采用像素截图 golden，避免 macOS 字体、渲染器、系统版本变化导致脆弱测试；视觉状态由 Component Gallery 做人工/自动截图入口，语义契约由 Swift Testing 守护。

## 6. 技术原则

SwiftUI environment 是系统状态事实源；不维护平行的 focus/contrast/accessibility 状态机。自定义 `ButtonStyle` 只改视觉，不重写 Button 的平台触发与键盘行为。

## 7. 下一步

Wave C 当前实现完成。下一步只对 PR #27 最终 head 统一执行 `MACOS_APP_P0`；若失败，仅用原子 fix commit 修复最终结果。
