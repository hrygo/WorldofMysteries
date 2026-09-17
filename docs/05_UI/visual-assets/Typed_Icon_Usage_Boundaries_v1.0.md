# WorldofMysteries Typed Icon 使用边界 v1.0

> 目的：明确什么时候必须进入 WOM typed icon 层，什么时候应该继续直接使用 SF Symbols，避免两种相反的漂移：世界观语义重新散落成字符串，或为了“统一”而把所有局部平台 glyph 都包装成无意义枚举。

## 1. 必须使用 Typed Registry 的场景

以下语义属于跨组件、跨页面的稳定设计系统 API，不允许业务视图继续散落字符串：

### A. 世界观语义

使用 `WOMIconAsset` / `WOMNavigationIconAsset`：

- World / Ritual / Codex / Artifact
- Character / Fate / Worldline / Notes
- Clue / Inventory / Divination / Spirituality / Gray Fog / Seal / Card

这些图形由项目原创 SVG 提供，Asset Catalog 是物理资源层，Swift enum 是语义层。

### B. 全局平台动作

使用 `WOMSystemIcon`：

- add / remove / edit / search
- close / back / favorite / more
- gallery / settings
- sidebar collapse / expand
- voice advice / audio replay

理由：这些行为跨多个控件重复出现，需要稳定语义与统一替换能力，但图形本身继续来自 SF Symbols。

### C. 通用状态

使用 `WOMStatusIcon`：

- warning
- success
- locked
- active
- cooldown

状态颜色与图标是两个独立语义维度；在 Differentiate Without Color 模式下不能只靠颜色传递状态。

## 2. 可以直接使用 `Image(systemName:)` 的场景

局部、内容型、一次性 pictogram 可以继续直接使用 SF Symbols，不要求为包装而包装，例如：

- 地点类型：house / university / moon 等；
- 某件 Artifact 自身由 `ArtifactDescriptor.systemIcon` 数据驱动的局部展示；
- 只在单个组件内部出现、没有跨组件稳定语义的说明图标；
- Apple 平台约定俗成、且无需项目级替换策略的临时辅助 glyph。

如果同一个 raw symbol 开始跨 2 个以上生产组件表达同一动作/状态，应升级进入 typed registry。

## 3. 禁止的做法

### 不复制平台 glyph 到 Asset Catalog

不得新增：

```text
wom.icon.add
wom.icon.remove
wom.icon.edit
wom.icon.search
wom.icon.close
wom.icon.back
wom.icon.favorite
wom.icon.more
```

这些语义必须继续映射 SF Symbols。

### 不用 SF Symbols 冒充世界观标识

已经存在自有 SVG 的稳定世界观语义，在生产导航、通用组件、主标题等位置不得重新退回通用 glyph，例如用 globe 冒充 World、person 冒充 Character、book 冒充 Codex。

### 不把状态位图化

Hover / Pressed / Selected / Focused / Disabled / Loading / High Contrast 等状态不得通过复制一组 `*.active.svg` / `*.hover.png` 实现；由 SwiftUI + Design Token 驱动。

## 4. 选择算法

新增图标需求时按顺序判断：

1. 是否是 WorldofMysteries 世界观稳定概念？是 → 原创 SVG + typed asset registry。
2. 是否是跨组件稳定的平台动作/通用状态？是 → typed SF Symbol registry。
3. 是否只是当前内容对象的局部 pictogram？是 → 可直接 SF Symbol。
4. 是否已在多个生产组件重复？是 → 升级 typed registry。

## 5. Accessibility 规则

- 图标旁已有可见文本且图标不增加信息：`accessibilityHidden(true)` 或让 `WOMIcon` 保持装饰性。
- icon-only button：必须在 Button 层提供 `accessibilityLabel` / help。
- 状态图标：不得只靠颜色；需要图形差异、文字或 accessibility value。
- 世界观图标不得把内部资产名如 `wom.icon.grayfog` 直接朗读给用户。

## 6. 审计策略

不采用“全仓库禁止 `Image(systemName:)`”这种机械规则。

审计重点是：

- typed registry 已声明的语义，在关键生产入口是否又退回 raw string；
- 平台动作是否被错误复制进 Asset Catalog；
- 新增世界观 SVG 是否有 registry 与 Asset Catalog contract；
- 重复 raw glyph 是否已经形成跨组件稳定语义。

## 7. 与 Wave D 的关系

Batch 18 的 Asset Catalog Contract Tests 负责守护物理资源与 typed registry 的一致性；本文负责守护“什么应该 typed、什么不应该 typed”的工程边界。两者合起来形成：

```text
视觉语义边界
    ↓
typed registry
    ↓
Asset Catalog / SF Symbols
    ↓
WOMIcon / component styles
    ↓
production views
```
