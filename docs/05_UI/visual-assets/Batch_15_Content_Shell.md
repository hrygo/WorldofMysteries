# Visual Asset System — Batch 15：ContentView Shell 收口

> Task：`MAC-VISUAL-CONTENT-SHELL`  
> 执行总计划：[`README.md`](README.md)  
> 状态：IMPLEMENTED IN PR #26

## 1. 范围

本批只迁移 App 公共视觉壳：

- 顶部 Engine 状态栏；
- 主工作区背景；
- 底部 Advice / Listening Ring 常驻区域；
- World / Settings 标题图标；
- generic placeholder 的 typed icon 与状态表达。

## 2. 视觉系统接入

- Engine ready / warning → `WOMStatusIcon`；
- 世界纪元标识 → `wom.icon.world`；
- 顶栏 / 底栏 → `WOMPanelBackground(.floating)` + 极弱 Sacred Slate；
- App 主背景 → Obsidian Base + 极弱 Sacred Slate texture；
- World 首页基础卡面 → `WOMCardChrome`；
- Fate 状态区域 divider → `WOMDividerOrnament`；
- Settings 标题 → `WOMSystemIcon.settings`；
- generic placeholder → `NavigationItem.iconSource` + `WOMIcon`。

## 3. reduced motion

以下现有状态切换现在尊重 `accessibilityReduceMotion`：

- Voice tapped → Listening Ring；
- Advice submit → deciding；
- Listening Ring toggling。

逻辑状态仍完全一致，只在 reduced motion 下取消动画插值。

## 4. 功能完成度表达

Story Book / Cards / Character 等尚未接入真实 ContentView 分发的入口仍进入 generic placeholder。

placeholder 文案明确说明：

> 视觉系统已就绪，但不会将未实现功能标记为生产完成。

这使视觉完成度与功能完成度分离，避免设计系统升级造成“看起来像已完成”的误导。

## 5. 明确未改变

- `AppState.startAndConnect()`；
- `currentNavigation` 分发；
- Fate / World / Gallery / Settings 路由；
- AdviceInputField 回调；
- ListeningRing 状态机；
- Engine / IPC / DB / contracts。

## 6. 后续

进入 Wave B 最后收口：检查 typed icon 覆盖、keyboard/accessibility/reduced transparency/high contrast，并在最终 head 上统一执行权威 CI。
