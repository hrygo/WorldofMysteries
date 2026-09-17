# Visual Asset System — Wave C / Batch 17：macOS Focus 与 Accessibility State

> Task：`MAC-VISUAL-SYSTEM-WAVE-C`  
> Base：`main@d0de662e4d2af8d607c9014084ee54ebe7b4a9f3`  
> 状态：BUTTON + SURFACE + GALLERY IMPLEMENTED / TESTS IN PROGRESS

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

`VisualSystemGallerySection` 新增专门的辅助功能展示区：

- 可用 Tab / Shift-Tab 实测 Focus ring；
- 提供“聚焦主按钮”动作，可直接把键盘焦点移动到目标按钮；
- 同屏展示 Disabled / Danger / Ritual；
- Selected / Unselected 卡片并排，用于验证 Differentiate Without Color 的双层描边；
- 文案明确提示可在 macOS 系统辅助功能中切换增强对比度、不使用颜色区分、减少动态效果和降低透明度观察实时结果。

## 5. 技术原则

SwiftUI environment 是系统状态事实源；不维护平行的 focus/contrast/accessibility 状态机。自定义 `ButtonStyle` 只改视觉，不重写 Button 的平台触发与键盘行为。

## 6. 下一步

1. `DesignSystemTests` 补 typed registry / icon size / texture compatibility / Navigation icon-source 回归；
2. 静态回读 Wave C diff；
3. 最终 head 统一执行 `MACOS_APP_P0`。
