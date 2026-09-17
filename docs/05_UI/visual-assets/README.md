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
- **Visual QA Contract 追溯适用于所有历史视觉代码；已合并不是豁免理由。**

## 2. 技术边界

- 世界观图形：原创 vector asset + typed registry，命名 `wom.icon.* / wom.ornament.* / wom.texture.*`。
- 平台行为与通用状态：SF Symbols + `WOMSystemIcon` / `WOMStatusIcon`。
- Hover / Pressed / Selected / Focused / Disabled / Loading：SwiftUI style + Design Token 驱动，不复制状态位图。
- Surface：程序化 fill/stroke/shadow + 少量纹理；Reduced Transparency / Increase Contrast 有稳定退化。
- Sheet / Popover / Inspector 的**呈现机制使用系统 API**；WOM 只提供内容 chrome，不模拟系统窗口层级。
- macOS Focus / contrast / active appearance 读取 SwiftUI environment，不自建第二套平台状态机。

## 3. Visual QA 硬性基线

当前权威 QA 规则：[`Visual_QA_Contract_v1.0.md`](Visual_QA_Contract_v1.0.md)。

- 常规正文 / Button / Form text 最终合成对比度 >= **4.5:1**。
- 关键非文本 affordance >= **3:1**。
- 长正文与关键说明优先向 **7:1** 靠拢。
- 正文默认 >= **13pt**；说明/元数据默认 >= **11pt**。
- 10pt 仅允许短数字 / 快捷键 / 极短标签；9pt 以下不承载关键语义。
- 最小窗口 **960×640** 必须无结构性重叠。
- 长中文 / 英文 / Badge / Loading / Error / Empty 必须有自然增长或 responsive fallback。
- 布局优先 Grid / adaptive / `ViewThatFits`，不得用缩小字体、负 offset 或魔法宽度掩盖空间问题。
- 同组卡片、按钮、标题基线、padding、视觉重量保持工整一致。
- Reduce Motion 必须在组件内部生效，不能只依赖父视图不触发动画。

## 4. 已合入 main

| 阶段 | PR | 内容 | 状态 |
|---|---|---|---|
| Foundation | #21–#25 | 核心/导航图标、Ornament、Texture、系统行为语义、持久化基础 | DONE |
| Wave B | #26 | Icon / Button / Surface primitives、Gallery、Sidebar、Ritual、Codex/Archive、Artifact/Fate、Content Shell | DONE |
| Wave C | #27 | Focus / Contrast / Accessibility states、semantic regression tests | DONE |
| Wave D | #28 | Asset Catalog contract、typed icon 边界、导航/Commands/⌘K Focus、placeholder readiness | DONE |
| Wave E | #29 | Overlay / Feedback chrome、Loading、Status、typed Empty State、Gallery regression | DONE |

当前主线基线：`main@475949e8d07c99683776faa63c88543e96e8d250`（包含 #29）。

## 5. 生产入口事实

- **Sidebar / Fate / Content Shell**：真实生产入口。
- **Ritual**：已有真实组件，但没有独立一级路由。
- **Character / Story Book / Cards / Worldline / Notes**：已有部分高质量 View primitive，但仍缺真实生产数据绑定，继续保持 placeholder。
- **Artifact**：继续作为 Fate 中命运干预工具；不额外制造背包一级导航。
- **Component Gallery**：设计系统 Showcase / Visual Regression / Visual QA Stress 观察入口，不等于业务页面完成。

## 6. 当前持久化工作流：Visual QA Backfill / PR #31

目标：将四项质量要求追溯应用到 Wave A–E：
1. 对比度符合最佳实践；
2. 字体清晰可辨；
3. 组件布局无重叠覆盖；
4. 布局工整、基线统一、对仗稳定。

Batch：[`Batch_22_Visual_QA_Backfill.md`](Batch_22_Visual_QA_Backfill.md)

### 已完成实现

- Button / Ritual / Sidebar / Codex / Dossier / Narrative / Worldline 的 contrast、microcopy、responsive backfill；
- ContentView 960pt minimum-window Fate / Settings / Engine header；
- Wave E Overlay / Status / Loading / Empty 在窄 Inspector/Popover 下的 responsive fallback；
- Spirituality Gauge / Listening Ring / Backlund / Crimson Beacon / Spirit Pendulum 的可读性与 Reduce Motion；
- shared `MysticTone.readableForeground` / 11pt Badge / KeyValueRow fallback；
- Artifact Showcase / Fate shortcut / shared Artifact Shell adaptive；
- **15/15 Artifact 个体 View 全量审计与必要返修**：Probability Die、Arrodes、Alzuhod Quill、Brass Book、Wishing Lamp、Creeping Hunger、Leymano、Groselle、Azik、Cards of Blasphemy、Sea God Scepter、Staff of Stars、Old Ones Box、Death Knell、Unshadowed Crucifix；
- Gallery Visual QA Stress specimens；
- `VisualQAContractTests.swift` 覆盖共享层、生产入口、历史组件与 15/15 Artifact 个体层。

### 已审计无需修改

- AdviceInputField；
- DatabaseStatusHUDCard；
- TarotCardView；
- CluePinboardNodeView。

当前下一动作：**锁最终 head → 最终 diff / Capsule 回读 → `MACOS_APP_P0` → CI 全绿后标记 READY TO MERGE。**

## 7. Wave E 关键决策（继续有效）

1. `.sheet` / `.popover` / `.inspector` 仍由 SwiftUI 系统 API 控制生命周期、焦点、键盘和辅助功能。
2. `WOMOverlayPanel` 只定义内容视觉层级、padding、surface、stroke 与 texture。
3. Loading 使用系统 `ProgressView`，不增加自制无限 spinner。
4. Status Banner 使用 typed status icon + 文本 + 左侧几何 rail；Differentiate Without Color 时增加 dash pattern。
5. Empty State 使用 `WOMEmptyState(source:)` 作为 typed canonical 入口；旧 `MysticEmptyState` 继续兼容。
6. 不修改 Engine / DB / IPC / schema，不用静态 demo 数据把 placeholder 冒充为生产页面。

## 8. 后续候选

Visual QA Backfill 完成后再进入：
- Production workspace binding（仅真实领域数据源就绪后）；
- Segmented / Tab-like control style；
- Relation / Achievement / Cooldown 等世界观特殊 chrome；
- 页面级 Inspector / multi-window 策略。

任何后续 Wave 必须先满足 Visual QA Contract，不允许新增“风格正确但不可读/会覆盖”的组件。

## 9. 恢复入口

稳定设计基线 → 本文件 → `Visual_QA_Contract_v1.0.md` → `Batch_22_Visual_QA_Backfill.md` → `MAC-VISUAL-QA-BACKFILL` Task Capsule → PR #31 base/head/diff → `VisualQAContractTests.swift` → Component Gallery Visual QA Stress → 最终 CI/readback。
