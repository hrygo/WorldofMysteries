# Visual Asset System — Batch 09：Surface / Texture / Section Chrome

> Task：`MAC-VISUAL-SYSTEM-WAVE-B`  
> 执行总计划：[`README.md`](README.md)  
> 状态：IMPLEMENTED IN PR #26

## 1. 目标

将面板、卡牌、纹理与章节装饰从页面内零散 modifier 收口为可组合 DesignSystem primitive。

## 2. 新增 Primitive

### `WOMSurfaceTone`

第一版 tone：

- panel
- card
- floating
- ritual
- parchment

### `WOMTextureLayer`

统一纹理 overlay：

- Asset 由 `WOMTextureAsset` 提供；
- 默认低 opacity；
- 支持 blend mode；
- `accessibilityReduceTransparency` 开启时自动把纹理降低到极弱级别；
- 不参与 hit testing / accessibility tree。

### `WOMPanelBackground`

程序化背景：

- semantic fill
- hairline stroke
- 可选 texture
- 仅 floating / ritual 使用克制 shadow/glow
- floating 在 reduced transparency 下退化为实色 elevated surface

### `WOMCardChrome`

在 base surface 上统一 selected / hovered border 与 glow，不复制页面级逻辑。

### `WOMSectionHeaderStyle` + `WOMDividerOrnament`

章节标题使用现有排版 token；divider 采用程序化细线 + 菱形，不新增图片资产。

## 3. 约束

- 不把整块 UI 烘焙成 PNG；
- 不引入新的 Design Token 常量；
- 不使用大面积实时 blur；
- 纹理只是质感层，不决定信息层级；
- reduced transparency 必须有稳定退化路径。

## 4. 后续

下一阶段进入 Component Gallery，把本轮新资产和 primitive 真实挂进设计系统展示页；随后再迁移生产页面。
