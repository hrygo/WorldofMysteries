# Visual Asset System — 执行总体方案与持久化规则

> 稳定设计基线：[`../Visual_Asset_System_v1.0.md`](../Visual_Asset_System_v1.0.md)  
> 本文件：视觉资产系统的 **Living Plan / 当前执行事实源**。

## 1. 当前执行规则

- 长期视觉原则、Token 边界与技术方向以 `Visual_Asset_System_v1.0.md` 为准；当前实施顺序、PR 与状态以本文件为准。
- 关键设计判断必须落仓库，不依赖聊天或临时环境。
- 同一阶段采用 **长期持久化 PR + 原子 commit**；PR 不要求最小化。
- 涉及方案时必须同步提交：总体方案 / Living Plan / Batch 记录 / 实际代码或资产。
- 稳定增量尽早推远端；最终 head 统一运行完整 `MACOS_APP_P0`。
- 不绕过主分支保护，不把“写入成功”当作“交付完成”。

## 2. 技术边界

- 世界观图形：原创 vector asset + typed registry，命名 `wom.icon.* / wom.ornament.* / wom.texture.*`。
- 平台行为与通用状态：SF Symbols + `WOMSystemIcon` / `WOMStatusIcon`。
- Hover / Pressed / Selected / Focused / Disabled / Loading：SwiftUI style + Design Token 驱动，不复制状态位图。
- Surface：程序化 fill/stroke/shadow + 少量纹理；Reduced Transparency / Increase Contrast 有稳定退化。
- Sheet / Popover / Inspector 的**呈现机制使用系统 API**；WOM 只提供内容 chrome，不模拟系统窗口层级。
- macOS Focus / contrast / active appearance 读取 SwiftUI environment，不自建第二套平台状态机。

## 3. 已合入 main

| 阶段 | PR | 内容 | 状态 |
|---|---|---|---|
| Foundation | #21–#25 | 核心/导航图标、Ornament、Texture、系统行为语义、持久化基础 | DONE |
| Wave B | #26 | Icon / Button / Surface primitives、Gallery、Sidebar、Ritual、Codex/Archive、Artifact/Fate、Content Shell | DONE |
| Wave C | #27 | Focus / Contrast / Accessibility states、semantic regression tests | DONE |
| Wave D | #28 | Asset Catalog contract、typed icon 边界、导航/Commands/⌘K Focus、placeholder readiness | DONE |

当前 `main` 基线：`51a9b2679420edbf1fb9b12189033a2a6cdc8567`（PR #28 merge commit）。

## 4. 生产入口事实

- **Sidebar / Fate / Content Shell**：真实生产入口。
- **Ritual**：已有真实组件，但没有独立一级路由。
- **Character / Story Book / Cards / Worldline / Notes**：已有部分高质量 View primitive，但仍缺真实生产数据绑定，继续保持 placeholder。
- **Artifact**：继续作为 Fate 中命运干预工具；不额外制造背包一级导航。
- **Component Gallery**：设计系统 Showcase / Visual Regression 观察入口，不等于业务页面完成。

## 5. 当前持久化工作流：Wave E

目标：补齐应用级 Overlay / Feedback visual chrome，使 Inspector / Popover / Sheet 内容、Loading、Status、Empty State 在不破坏 macOS 原生呈现机制的前提下统一视觉语义。

### Batch 21 — Overlay & Feedback Chrome

| 子阶段 | 内容 | 状态 |
|---|---|---|
| E21.1 | 总体方案 / Living Plan / Task Capsule / Batch 21 持久化 | IN PROGRESS |
| E21.2 | `WOMOverlayPanel`：Inspector / Popover / Sheet content chrome | PLANNED |
| E21.3 | `WOMLoadingState` + `WOMStatusBanner` | PLANNED |
| E21.4 | `MysticEmptyState` typed icon 兼容升级 | PLANNED |
| E21.5 | Component Gallery Overlay/Feedback specimen | PLANNED |
| E21.6 | Overlay semantic contract tests | PLANNED |

## 6. Wave E 技术原则

1. `.sheet` / `.popover` / `.inspector` 仍由 SwiftUI 系统 API 控制生命周期、焦点、键盘和辅助功能。
2. `WOMOverlayPanel` 只定义内容视觉层级、padding、surface、stroke、texture 和 active appearance。
3. Loading 优先使用系统 `ProgressView`，避免自制无限动画；Reduced Motion 下不添加额外旋转/呼吸效果。
4. Status Banner 使用 typed status icon / semantic tone，不仅依赖颜色区分。
5. Empty State 保留现有 raw SF Symbol 初始化器兼容性，同时新增 typed `WOMIconSource` 入口。
6. 不修改 Engine / DB / IPC / schema，不用静态 demo 数据把 placeholder 冒充为生产页面。

## 7. 后续候选

- Production workspace binding（仅在真实领域数据源就绪后）；
- Segmented / Tab-like control style；
- Relation / Achievement / Cooldown 等世界观特殊 chrome；
- 更完整的高对比度 / Reduced Transparency / Reduced Motion 回归矩阵；
- 页面级窗口尺寸、Inspector 宽度与多窗口策略。

## 8. 恢复入口

稳定设计基线 → 本文件 → `Batch_21_Overlay_Feedback_Chrome.md` → `MAC-VISUAL-SYSTEM-WAVE-E` Task Capsule → `DesignSystem/WOM*` → Component Gallery → 当前 Wave E PR 原子 commit 历史 → 最终 CI/readback。
