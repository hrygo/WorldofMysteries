# Visual Asset System — Batch 08：Button Style Primitives

> Task：`MAC-VISUAL-SYSTEM-WAVE-B`  
> 执行总计划：[`README.md`](README.md)  
> 状态：IMPLEMENTED IN PR #26

## 1. 目标

建立统一按钮 chrome，复用现有 Design Token，不另起一套颜色、圆角或 motion 常量。

## 2. 语义 Variant

`WOMButtonVariant`：

- `primary`：黄铜主操作；
- `secondary`：深色次操作；
- `tertiary`：低干扰透明/工具操作；
- `danger`：破坏性操作；
- `ritual`：深空 + 灵性蓝边缘，用于仪式型强语义动作。

## 3. 三种 ButtonStyle

- `WOMButtonStyle`：普通文本/Label 按钮；
- `WOMIconButtonStyle`：icon-only 紧凑按钮；
- `WOMToolbarButtonStyle`：macOS toolbar / inspector header 密度。

三者共享同一个内部 chrome，防止 hover / pressed / disabled 行为漂移。

## 4. 状态策略

当前 primitive 覆盖：

- normal
- hover
- pressed
- disabled
- reduced motion

Focus 不创建私有焦点状态机，保留 SwiftUI/macOS 原生 focus 行为；Loading 不塞入 `ButtonStyle`，后续由具体 `WOMButton` 容器控制 action 禁用与 ProgressView，避免样式层无法完整阻止键盘触发的问题。

## 5. Token 复用

复用：

- `DesignTokens.Interaction`
- `DesignTokens.Spacing`
- `DesignTokens.Radii`
- `DesignTokens.Borders`
- `Color.Mystic.*`

不修改 token 数值，不产生第二事实源。

## 6. 后续

下一原子 commit 进入 Batch 09：Panel / Card / Texture Layer / Section Chrome。
