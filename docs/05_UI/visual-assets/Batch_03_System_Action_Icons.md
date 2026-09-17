# Visual Asset System — Batch 03：macOS 标准行为图标语义

> Task：`MAC-VISUAL-ASSET-03-R3`  
> 总体设计：[`../Visual_Asset_System_v1.0.md`](../Visual_Asset_System_v1.0.md)  
> 执行总方案：[`README.md`](README.md)

## 1. 目的

为 Add / Remove / Edit / Search 四个标准 macOS 行为建立稳定类型化语义，并固定平台资产与世界观自有资产的边界。

## 2. 实际交付

新增：

```text
macos-app/WorldOfMysteries/DesignSystem/WOMSystemIcon.swift
```

语义映射：

| WOM semantic | SF Symbol | 说明 |
|---|---|---|
| `add` | `plus` | 添加 |
| `remove` | `minus` | 从集合移除，不等同于 destructive delete |
| `edit` | `pencil` | 编辑 |
| `search` | `magnifyingglass` | 搜索 / 查找 |

## 3. 资产边界

- 世界观概念：原创 SVG + `WOMIconAsset` / `WOMNavigationIconAsset`。
- macOS 标准行为：SF Symbols + `WOMSystemIcon`。
- 状态颜色、选中态和动效：由后续 `WOMIcon` / ButtonStyle + Design Token 负责。

不复制系统 glyph 到 `Assets.xcassets`，也不在业务页面散落裸 `Image(systemName:)` 字符串作为长期方案。

## 4. 本批不做

- 不实现 `WOMIcon` SwiftUI View。
- 不迁移 Toolbar / Sidebar / 页面。
- 不实现 Close / Back / Favorite / More。
- 不修改 Design Token 数值。
- 不触碰 Engine / DB / IPC / contracts。

## 5. 提交与验证策略

本批作为原子 commit 合入视觉资产集成分支，不单独等待一轮完整 CI。权威验证在本阶段所有既有视觉资产 PR 汇总后，对最终集成结果统一执行。

## 6. 下一步

继续扩展：

```text
close     -> xmark
back      -> chevron.left
favorite  -> star
more      -> ellipsis
```

这些可以作为后续原子 commit 持续推送到同一持久化 PR，不要求额外拆成最小 PR。
