# Visual Asset System — 执行总体方案与持久化规则

> 稳定设计基线：[`../Visual_Asset_System_v1.0.md`](../Visual_Asset_System_v1.0.md)  
> 本文件：视觉资产系统的 **Living Plan / 执行总体方案**。

## 1. 权威性

- 长期视觉语言、Token 原则、技术边界：以 `Visual_Asset_System_v1.0.md` 为准。
- 当前实施顺序、资产落盘进度、依赖和恢复入口：以本文件为准。
- 单批设计与实现细节：以对应 `Batch_xx_*.md`、Task Capsule、原子 commit 为准。

任何关键设计判断不得只存在于聊天、临时工作区或 PR 描述中。

## 2. 持久化与提交模型

从本阶段起采用以下固定规则：

1. **尽早远端持久化**：任务开始后尽快建立远端分支/PR，不等待整批实现完成。
2. **PR 不要求最小化**：一个 PR 可以持续承载同一工作流的多个增量阶段。
3. **原子 commit 才是最小单元**：每个 commit 必须语义单一、可审查、可回滚、可独立定位。
4. **总 / 分资料同步落盘**：涉及方案时，必须同时维护本 Living Plan 与对应 Batch 文档；实现只完成方案的一部分，也必须把总体方案一起提交。
5. **资产尽快落盘**：SVG、纹理、注册表、组件实现一旦形成稳定增量即提交，避免只保留在执行环境。
6. **最终集成验证优先**：低风险同类 UI/资产批次可先合并到集成分支，最后对整体集成结果跑一次权威门禁；高风险架构/契约改动仍可独立加严。

## 3. 资产技术边界

### 自有世界观图形

使用 `Assets.xcassets` 中原创矢量资产 + 类型化注册表，命名空间统一为：

```text
wom.icon.*
wom.ornament.*
wom.texture.*
```

### 平台标准行为

优先使用 SF Symbols，通过 `WOMSystemIcon` 做稳定语义映射，不复制系统 glyph 到 Asset Catalog。

### 视觉状态

颜色、hover、pressed、selected、focused、disabled、loading 等状态由 SwiftUI 样式与 Design Token 控制，不通过重复导出大量状态位图实现。

## 4. 当前已落盘链路

| 阶段 | 内容 | 持久化状态 |
|---|---|---|
| Foundation / PR #22 | Visual Asset System 基线；World / Ritual / Codex / Artifact；`WOMIconAsset` 基础 | 已合入 main |
| Navigation / PR #21 | Character / Fate / Worldline / Notes；`WOMNavigationIconAsset` | 已合入 main |
| Batch 02 / PR #23 | Clue / Inventory / Settings；扩展 `WOMIconAsset`；Living Plan | 已进入集成分支 |
| Batch 03 / PR #24 | Add / Remove / Edit / Search 的 SF Symbols 类型化语义 | 本次进入集成分支 |

## 5. 后续路线

后续不再强制“一批 = 一个 PR”；可以在同一持久化 PR 内用多个原子 commit 连续推进。

优先顺序：

1. 补齐系统行为语义：Close / Back / Favorite / More。
2. 状态与世界交互语义：Warning / Success / Locked / Active / Cooldown / Divination / Spirituality / Fate / Gray Fog / Seal / Card。
3. 纹理注册与质量盘点：Parchment / Gold / Veil / Slate / Velvet。
4. `WOMIcon`：统一 custom asset 与 SF Symbols source。
5. `WOMButtonStyle` / Icon Button / Toolbar Button。
6. `WOMPanelBackground` / `WOMCardChrome` / `WOMTextureLayer` / Section Chrome。
7. 真实页面逐步迁移：Sidebar、Ritual、Codex、Artifact、Component Gallery。
8. 最终补齐 accessibility、keyboard navigation、reduced motion/transparency/high contrast。

## 6. 恢复入口

新执行环境恢复时，按以下顺序读取：

1. `docs/05_UI/Visual_Asset_System_v1.0.md`
2. 本文件
3. 最新 Batch 文档
4. `WOMIconAsset.swift` / `WOMNavigationIconAsset.swift` / `WOMSystemIcon.swift`
5. `Assets.xcassets/wom.*`
6. 当前远端 PR 与最近原子 commit

目标是保证任何环境丢失后，仅依赖仓库即可恢复当前视觉系统状态和下一步工作。
