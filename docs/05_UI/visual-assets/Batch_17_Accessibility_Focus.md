# Visual Asset System — Wave C / Batch 17：macOS Focus 与 Accessibility State

> Task：`MAC-VISUAL-SYSTEM-WAVE-C`  
> Base：`main@d0de662e4d2af8d607c9014084ee54ebe7b4a9f3`  
> 状态：BUTTON + SURFACE IMPLEMENTED / GALLERY & TESTS IN PROGRESS

## 1. 目标

Wave C 聚焦 macOS 原生 Focus、高对比度、Differentiate Without Color、inactive appearance 与设计系统回归保障，不扩展领域功能。

## 2. Button Chrome

`WOMButtonStyle`、`WOMIconButtonStyle`、`WOMToolbarButtonStyle` 共享 `WOMButtonChrome`，读取：

- `isFocused`
- `appearsActive`
- `colorSchemeContrast`
- `accessibilityDifferentiateWithoutColor`
- `accessibilityReduceMotion`

实现：Focus 外环、Increase Contrast heavy border、Danger/Ritual 非颜色 dash pattern、inactive-window 降低 accent/glow、reduced motion 关闭反馈动画。

## 3. Surface / Card Chrome

### `WOMTextureLayer`

- Reduced Transparency：纹理 opacity 上限 0.025；
- Increased Contrast：纹理 opacity 上限 0.05，减少视觉噪声。

### `WOMPanelBackground`

- Increase Contrast 使用更清晰 semantic stroke；
- stroke 从 hairline 提升到 standard；
- high contrast / inactive window 关闭 decorative glow/shadow；
- parchment / ritual / dark surfaces 保持各自语义边界。

### `WOMCardChrome`

- selected + Increase Contrast → heavy border；
- `accessibilityDifferentiateWithoutColor` + selected → 增加第二层 inset border，因此 selected 不只靠金色表达；
- hover/selected 动画尊重 Reduced Motion；
- inactive window 关闭 glow。

### Section / Divider

- Section Header 在 Increase Contrast 下使用完整 `textGoldAccent`；
- Divider 在 Increase Contrast 下升级到 standard width 和更高对比色。

## 4. macOS 技术原则

SwiftUI environment 是系统状态事实源；不维护平行的 focus/contrast/accessibility 状态机。自定义 `ButtonStyle` 只改视觉，不重写 Button 的平台触发与键盘行为。

## 5. 下一步

1. Component Gallery 增加 Accessibility State specimen；
2. DesignSystemTests 补 typed registry / size / compatibility 回归；
3. 静态回读 Wave C diff；
4. 最终 head 统一执行 `MACOS_APP_P0`。
