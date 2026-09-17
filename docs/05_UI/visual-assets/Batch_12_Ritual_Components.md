# Visual Asset System — Batch 12：Ritual 现有组件迁移

> Task：`MAC-VISUAL-RITUAL-COMPONENTS`  
> 执行总计划：[`README.md`](README.md)  
> 状态：IMPLEMENTED IN PR #26

## 1. 仓库现状与范围决定

当前产品导航不存在独立的 Ritual 一级路由，因此本批不凭空创建新页面。现有仪式体验主要落在：

- `BronzeAltarPrayerCard`
- `CitrinePendulumScryingCard`

本批直接迁移这两个真实组件，并保持产品导航结构不变。

## 2. Bronze Altar Prayer

迁移内容：

- 根容器 → `WOMPanelBackground(.ritual)` + 极弱 Fool Veil 纹理；
- 标题语义 → `wom.icon.ritual`；
- 灵性消耗 → `wom.icon.spirituality`；
- 祈求目的 → Card surface + Seal 图标；
- 行为按钮 → `WOMButtonStyle(.ritual)`；
- 共鸣中状态 → `WOMStatusIcon.active`；
- 蜡烛闪烁尊重 `accessibilityReduceMotion`。

三段式尊名、pathwayColor、ritualIntent、spiritualityCost 和回调语义不变。

## 3. Citrine Pendulum Scrying

迁移内容：

- 根容器 → Ritual surface + Fool Veil；
- 标题 → `wom.icon.divination`；
- 灵性消耗 → `wom.icon.spirituality`；
- TextField → Card + Sacred Slate；
- 执链按钮 → `WOMButtonStyle(.ritual)`；
- 推演状态 → 类型化 `WOMStatusIcon`；
- Divider → `WOMDividerOrnament`；
- reduced motion 下停止灵摆往复与定格偏摆。

## 4. 明确未改变

- `resolveOutcome(for:)` 规则不变；
- 高位存在关键词判定不变；
- 1.6 秒原型推演时序不变；
- `onScryingTriggered` 回调不变；
- 不将表达层推演写入领域事实；
- 不新增 Ritual 一级导航。

## 5. 后续

下一步处理 Codex/Story Book 现状：先定位真实生产视图；若仍为 placeholder，则优先迁移已有 Codex/Archive 组件而不是制造空页面。
