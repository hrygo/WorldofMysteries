# Visual Asset System — 执行总体方案与持久化规则

> 稳定设计基线：[`../Visual_Asset_System_v1.0.md`](../Visual_Asset_System_v1.0.md)  
> 本文件：视觉资产系统的 **Living Plan / 执行总体方案**。

## 1. 权威性

- 长期视觉语言、Token 原则、技术边界：以 `Visual_Asset_System_v1.0.md` 为准。
- 当前实施顺序、资产落盘进度、依赖和恢复入口：以本文件为准。
- 单批设计与实现细节：以对应 `Batch_xx_*.md`、Task Capsule、原子 commit 为准。

任何关键设计判断不得只存在于聊天、临时工作区或 PR 描述中。

## 2. 持久化与提交模型

1. **尽早远端持久化**：任务开始后尽快建立远端分支/PR，不等待整批实现完成。
2. **PR 不要求最小化**：一个 PR 可以持续承载同一工作流的多个增量阶段。
3. **原子 commit 才是最小单元**：每个 commit 必须语义单一、可审查、可回滚、可独立定位。
4. **总 / 分资料同步落盘**：涉及方案时，必须同时维护本 Living Plan 与对应 Batch 文档；实现只完成方案的一部分，也必须把总体方案一起提交。
5. **资产尽快落盘**：SVG、纹理、注册表、组件实现一旦形成稳定增量即提交，避免只保留在执行环境。
6. **最终集成验证优先**：低风险同类 UI/资产增量持续推送到同一持久化 PR；准备合并时对最终 head 跑完整权威门禁。

## 3. 资产技术边界

### 自有世界观图形

使用 `Assets.xcassets` 中原创矢量资产 + 类型化注册表：

```text
wom.icon.*
wom.ornament.*
wom.texture.*
```

### 平台标准行为

优先使用 SF Symbols，通过 `WOMSystemIcon` / `WOMStatusIcon` 做稳定语义映射，不复制系统 glyph 到 Asset Catalog。

### 视觉状态

颜色、hover、pressed、selected、focused、disabled、loading 等状态由 SwiftUI 样式与 Design Token 控制，不通过重复导出大量状态位图实现。

## 4. 已落盘基线

| 阶段 | 内容 | 状态 |
|---|---|---|
| Foundation / PR #22 | World / Ritual / Codex / Artifact；`WOMIconAsset` 基础；总体设计基线 | 已合入 main |
| Navigation / PR #21 | Character / Fate / Worldline / Notes；`WOMNavigationIconAsset` | 已合入 main |
| Batch 02 / PR #23 + #25 | Clue / Inventory / Settings；扩展 `WOMIconAsset`；Living Plan | 已合入 main |
| Batch 03 / PR #24 + #25 | Add / Remove / Edit / Search 的 SF Symbols 类型化语义 | 已合入 main |

## 5. 当前持久化工作流：Wave B

长期 PR：`feat/wom-visual-system-wave-b` / PR #26。

1. **Batch 04**：Close / Back / Favorite / More。**已实现。**
2. **Batch 05**：状态语义 + Divination / Spirituality / Gray Fog / Seal / Card。**已实现。**
3. **Batch 06**：`WOMTextureAsset`。**已实现。**
4. **Batch 07**：统一 `WOMIcon`。**已实现。**
5. **Batch 08**：Button Style primitives。**已实现。**
6. **Batch 09**：Panel / Card / Texture / Section Chrome。**已实现。**
7. **Batch 10**：Component Gallery 视觉系统展示。**已实现。**
8. **Batch 11**：Sidebar 生产迁移。**已实现。**
9. **Batch 12**：现有 Ritual 组件（祭坛祈祷 + 黄水晶灵摆）迁移。**已实现。**
10. **Batch 13+**：Codex/Story Book、Artifact/Fate 等真实组件与页面继续迁移。

## 6. 原子 commit 规则

```text
docs(macos): persist visual system wave B plan
feat(macos): complete system action icon semantics
feat(macos): add occult state and interaction icon assets
feat(macos): register texture assets
feat(macos): add unified WOMIcon component
feat(macos): add button style primitives
feat(macos): add panel and card surface primitives
feat(macos): expose visual system in component gallery
feat(macos): migrate sidebar to visual system
feat(macos): migrate ritual components to visual system
```

不得为了减少 commit 数把不相关资产、组件和页面迁移揉成一个提交。

## 7. 生产页面迁移事实

- Sidebar：存在真实生产组件，已迁移。
- Ritual：当前**没有独立一级导航路由**；已优先迁移真实存在的 `BronzeAltarPrayerCard` 与 `CitrinePendulumScryingCard`，不制造空路由。
- Story Book / Cards：当前 `ContentView` 仍进入 generic placeholder；后续先盘点真实 Codex / Card 组件，再决定生产入口。
- Artifact：当前明确作为 Fate 中的命运干预工具嵌入，不新增一级“道具背包”导航。

## 8. 下一阶段

1. Codex / Archive 真实组件盘点与迁移；
2. Artifact / Fate 真实组件迁移；
3. ContentView shell 的状态栏 / 底部常驻交互 chrome 收口；
4. accessibility / keyboard / reduced motion / transparency / high contrast 收口。

## 9. 恢复入口

1. `docs/05_UI/Visual_Asset_System_v1.0.md`
2. 本文件
3. 最新 `Batch_xx_*.md`
4. 当前 Task Capsule
5. `WOMIconAsset.swift` / `WOMNavigationIconAsset.swift` / `WOMSystemIcon.swift` / `WOMStatusIcon.swift`
6. `WOMIcon.swift` / `WOMButtonStyles.swift` / `WOMSurfaceStyles.swift`
7. `Assets.xcassets/wom.*`
8. PR #26 与其原子 commit 历史

目标：任何执行环境丢失后，仅依赖仓库和开放 PR 即可继续推进。
