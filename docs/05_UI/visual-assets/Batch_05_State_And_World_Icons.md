# Visual Asset System — Batch 05：状态与世界交互语义

> Task：`MAC-VISUAL-SYSTEM-WAVE-B`  
> 执行总计划：[`README.md`](README.md)  
> 状态：IMPLEMENTED IN PR #26

## 1. 设计判断

本批把“状态语义”和“世界观交互语义”明确分开，避免将 macOS 已有的通用状态 glyph 重绘成近似系统图标。

### 平台状态：SF Symbols

新增 `WOMStatusIcon`：

| Semantic | SF Symbol |
|---|---|
| warning | `exclamationmark.triangle` |
| success | `checkmark.circle` |
| locked | `lock` |
| active | `sparkles` |
| cooldown | `timer` |

### 世界观交互：原创 SVG

新增 5 个 24×24 template vector asset：

| Asset | 视觉母题 |
|---|---|
| `wom.icon.divination` | 占卜环 + 摆锤 |
| `wom.icon.spirituality` | 灵性焰滴 + 内在之眼 |
| `wom.icon.grayfog` | 三层灰雾流线 + 微光星芒 |
| `wom.icon.seal` | 双环封印 + 中心秘纹 |
| `wom.icon.card` | 古典卡牌框 + 星芒 |

## 2. 注册策略

- 通用状态通过 `WOMStatusIcon` 暴露，不写入 `Assets.xcassets`；
- 世界观交互扩展 `WOMIconAsset`；
- Fate 已由 `WOMNavigationIconAsset` 提供，不重复创建同义资产；
- 颜色、selected、hover、disabled 等状态由未来 `WOMIcon` 和 ButtonStyle 控制。

## 3. 资产规格

```text
canvas: 24 × 24
format: SVG
rendering intent: template
preserves vector representation: true
color: semantic token controlled
```

## 4. 后续

下一原子 commit 进入 Batch 06：盘点已有纹理并建立 `WOMTextureAsset`。
