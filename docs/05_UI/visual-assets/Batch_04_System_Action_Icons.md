# Visual Asset System — Batch 04：系统行为语义补齐

> Task：`MAC-VISUAL-SYSTEM-WAVE-B`  
> 总体设计：[`../Visual_Asset_System_v1.0.md`](../Visual_Asset_System_v1.0.md)  
> 执行总计划：[`README.md`](README.md)  
> 状态：PLANNED / PERSISTED BEFORE IMPLEMENTATION

## 1. 目标

在已有 Add / Remove / Edit / Search 基础上补齐第二组 macOS 标准行为语义：

| WOM semantic | SF Symbol | 用途 |
|---|---|---|
| `close` | `xmark` | 关闭、取消局部浮层 |
| `back` | `chevron.left` | 返回上一层 |
| `favorite` | `star` | 收藏 / 标记 |
| `more` | `ellipsis` | 更多操作 |

## 2. 技术边界

这些都是平台标准行为，不创建自有 SVG；通过 `WOMSystemIcon` 类型化映射使用 SF Symbols。

Selected / filled 状态不在 registry 中复制，例如 Favorite 的选中态应由未来 `WOMIcon` / ButtonStyle 通过 symbol variant 或状态策略处理。

## 3. 本批验收

- `WOMSystemIcon` 不再散落第二组行为字符串；
- 与现有 Add / Remove / Edit / Search 保持同一 API；
- 不修改 Design Token；
- 不迁移真实页面；
- 实现与本文档在同一长期 PR 中持久化。

## 4. 后续

完成本批后不关闭 PR，继续以新的原子 commit 推进 Batch 05 状态与世界交互语义资产。
