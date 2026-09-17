# Visual Asset System — Wave C / Batch 17：macOS Focus 与 Accessibility State

> Task：`MAC-VISUAL-SYSTEM-WAVE-C`  
> Base：`main@d0de662e4d2af8d607c9014084ee54ebe7b4a9f3`  
> 状态：BUTTON CHROME IMPLEMENTED / SURFACE & TESTS IN PROGRESS

## 1. 目标

Wave C 聚焦 macOS 原生 Focus、高对比度、Differentiate Without Color、inactive appearance 与设计系统回归保障，不扩展领域功能。

## 2. Button Chrome 已实现

`WOMButtonStyle`、`WOMIconButtonStyle`、`WOMToolbarButtonStyle` 继续共享同一个 `WOMButtonChrome`，新增读取：

- `isFocused`
- `appearsActive`
- `colorSchemeContrast`
- `accessibilityDifferentiateWithoutColor`
- 原有 `accessibilityReduceMotion`

### Focus

获得键盘焦点时，在既有 border 外增加由 `DesignTokens.Accessibility.focusRingWidth / focusRingOffset` 驱动的外环；不替换 Button 的平台触发机制。

### Increase Contrast

- border 提升到 heavy；
- Primary / Secondary / Tertiary 使用更清晰的 `textGoldAccent` 边界；
- Danger / Ritual 使用各自高辨识语义色；
- 关闭模糊 glow，改靠清晰描边建立层级。

### Differentiate Without Color

当用户要求“不仅靠颜色区分”时：

- Danger 使用 `[4, 2]` dash pattern；
- Ritual 使用 `[1, 2]` dot-like pattern；
- 其他通用按钮保持连续线。

因此危险/仪式语义即使在无法依赖颜色时仍有几何差异。

### Inactive Window

`appearsActive == false` 时降低自定义 accent/background 强度，并关闭 hover glow，避免后台窗口保持过强视觉权重。

## 3. 技术依据

采用 SwiftUI 环境状态，不创建第二套 focus/contrast 状态机。自定义 `ButtonStyle` 继续保留平台标准 Button interaction。

## 4. 下一步

1. Surface / Card chrome 同步支持 Increased Contrast、Differentiate Without Color、inactive appearance；
2. Component Gallery 增加 accessibility specimen；
3. DesignSystemTests 补 typed registry / size / compatibility 回归；
4. 最终 head 统一运行 `MACOS_APP_P0`。
