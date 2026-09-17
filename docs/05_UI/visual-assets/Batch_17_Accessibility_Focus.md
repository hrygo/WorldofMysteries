# Visual Asset System — Wave C / Batch 17：macOS Focus 与 Accessibility State

> Task：`MAC-VISUAL-SYSTEM-WAVE-C`  
> Base：`main@d0de662e4d2af8d607c9014084ee54ebe7b4a9f3`  
> 状态：PLAN PERSISTED / IMPLEMENTATION STARTED

## 1. 目标

Wave B 已完成资产、图标、按钮、Surface 与关键生产组件迁移。Wave C 不再以增加资产数量为主，而是收紧真正的 macOS 控件行为与无障碍视觉状态：

1. 键盘 Focus 必须有明确但克制的视觉反馈；
2. Increase Contrast 时边框/Surface 区分度增强；
3. Differentiate Without Color 开启时，selected / danger / ritual 等状态不能只靠颜色；
4. inactive window 应适度降低强调，不让自定义 chrome 与 macOS active appearance 冲突；
5. reduced motion / reduced transparency 继续保持 Wave B 的退化策略；
6. 为 typed registry、尺寸 scale 与语义映射补 Swift Testing 回归断言。

## 2. macOS 技术依据

SwiftUI 环境提供：

- `isFocused`：最近 focusable ancestor 是否获得焦点；
- `colorSchemeContrast`：当前颜色方案的对比度偏好；
- `accessibilityDifferentiateWithoutColor`：是否要求不用颜色作为唯一信息载体；
- `appearsActive`：macOS 当前窗口/上下文是否应呈 active appearance。

`ButtonStyle` 保留平台标准 Button 交互，仅自定义外观，不另造键盘触发机制。

## 3. 第一阶段实现

### Button chrome

计划增加：

- focus ring；
- increased contrast 下更明确的 border；
- differentiate-without-color 下 hover/selected 之外的几何/描边反馈；
- inactive appearance 下降低 glow/accent；
- icon-only / toolbar 保持同一 shared chrome。

### Surface chrome

计划增加：

- high-contrast stroke；
- selected card 在 differentiate-without-color 下使用双层/更宽描边，而非只有金色；
- inactive window 降低不必要 glow。

### Gallery

增加 Accessibility State specimen，集中预览 Focus / Disabled / High Contrast 设计约定。

## 4. 测试

`DesignSystemTests` 增加纯语义回归测试：

- `WOMIconSize` 16 / 20 / 24 / 32；
- `WOMSystemIcon` 关键 SF Symbol 映射；
- `WOMStatusIcon` 映射；
- `WOMTextureAsset` 兼容 aliases 与 `semanticKey`；
- `WOMIconAsset` 新增世界观资产 registry 完整性；
- `NavigationItem.iconSource` 覆盖 9 个入口。

## 5. 提交策略

继续使用长期 PR + 原子 commit：

```text
docs(macos): persist visual system wave C plan
feat(macos): add focus and contrast aware button chrome
feat(macos): harden accessible surface states
feat(macos): add accessibility specimens to gallery
test(macos): cover visual system semantic registries
```

准备合并时只对最终 head 运行一次完整 `MACOS_APP_P0`。
