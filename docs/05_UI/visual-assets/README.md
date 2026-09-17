# Visual Asset System — Living Plan / 当前执行事实源

> 稳定设计基线：[`../Visual_Asset_System_v1.0.md`](../Visual_Asset_System_v1.0.md)  
> Visual QA：[`Visual_QA_Contract_v1.0.md`](Visual_QA_Contract_v1.0.md)

## 1. 持久化与交付规则

- 关键设计判断必须落仓库，不依赖聊天或临时环境。
- 同一阶段采用 **长期持久化 PR + 原子 commit**；PR 不要求最小化。
- 涉及方案时同步提交：Living Plan + Batch + Capsule + 实际代码/测试。
- 稳定增量尽早推远端；最终 head 统一执行 `MACOS_APP_P0`。
- 不绕过主分支保护；写入成功不等于交付完成。
- Visual QA Contract 对历史和未来视觉代码都生效，已合并不是豁免理由。

## 2. 技术边界

- 世界观图形：原创 vector asset + typed registry。
- 平台行为/状态：SF Symbols + typed semantic registry。
- Hover / Pressed / Selected / Focused / Disabled / Loading：SwiftUI style + Design Token 驱动。
- Sheet / Popover / Inspector / segmented selection / WindowGroup 优先系统 SwiftUI/macOS 语义；WOM 只补视觉、语义与布局契约，不伪造系统控件/窗口。
- Surface 使用程序化 fill/stroke/shadow + 少量纹理。
- 不允许新增 Engine / DB / IPC / schema 耦合来服务纯视觉组件。

## 3. Visual QA 硬性基线

- 常规正文 / Button / Form text 最终对比度 >= **4.5:1**。
- 关键非文本 affordance >= **3:1**。
- 长正文与关键说明优先向 **7:1** 靠拢。
- 正文默认 >= **13pt**；说明/元数据默认 >= **11pt**。
- 10pt 仅短数字 / 快捷键 / 极短标签；9pt 以下不承载关键语义。
- 最小窗口 **960×640** 无结构性重叠。
- 长中英文、Badge、Loading、Error、Empty 必须自然增长或 responsive fallback。
- 优先 adaptive Grid / `ViewThatFits`；不得通过缩小字体、负 offset、魔法宽度或抬高最小窗口掩盖布局问题。
- 同组卡片、按钮、标题基线、padding、视觉重量保持工整一致。
- Reduce Motion / Increased Contrast / Differentiate Without Color / Reduce Transparency / Keyboard Focus 必须稳定退化。

## 4. 已合入 main

| 阶段 | PR | 内容 | 状态 |
|---|---|---|---|
| Foundation | #21–#25 | Core/navigation icons、ornament、texture、platform semantics | DONE |
| Wave B | #26 | Icon/Button/Surface、Gallery、Sidebar、Ritual、Codex、Artifact/Fate、Shell | DONE |
| Wave C | #27 | Focus / Contrast / Accessibility states | DONE |
| Wave D | #28 | Asset contracts、typed icon、navigation/commands/focus | DONE |
| Wave E | #29 | Overlay / Feedback / Loading / Status / typed Empty State | DONE |

## 5. 已验证待合并：Visual QA Backfill / PR #31

Branch: `feat/wom-visual-qa-backfill-v2`  
Final head: `8b9ab58428d05762184884c9e60b03f6e8075d71`  
状态：**READY TO MERGE / ALL QUALITY GATES PASSED**。

已完成 Wave A–E 的 retroactive contrast / typography / collision / alignment audit、960×640 responsive hardening、shared primitives、15/15 Artifact shared + individual QA、Reduce Motion 和 `VisualQAContractTests.swift`。

## 6. 已实现待 retarget：Wave F / PR #32

Branch: `feat/wom-visual-system-wave-f`  
Stacked base: `#31@8b9ab58428d05762184884c9e60b03f6e8075d71`  
Head: `a4ae319d48f25b9eadffdf6f8e64845ecc55cada`  
状态：**IMPLEMENTATION COMPLETE / RETARGET + FINAL CI PENDING**。

已实现：

- `WOMAdaptiveSegmentedPicker`：原生 Picker segmented → menu fallback；
- `WOMRelationBadge`：5 种关系语义，非 color-only；
- `WOMAchievementSeal`：locked/discovered/completed；
- `WOMCooldownIndicator`：外部状态驱动 determinate `ProgressView`；
- Gallery long-label / narrow-width stress；
- `VisualAdvancedInteractionContractTests.swift`。

Wave F 不伪造关系分数、成就持久化、冷却计时器或业务真相。

## 7. 当前持久化工作流：Wave G — Window / Inspector / Responsive Workspace Layout

Branch: `feat/wom-visual-system-wave-g`  
Stacked base: `feat/wom-visual-system-wave-f@a4ae319d48f25b9eadffdf6f8e64845ecc55cada`  
Batch: [`Batch_24_Wave_G_Window_Inspector_Layout.md`](Batch_24_Wave_G_Window_Inspector_Layout.md)  
Task: `MAC-VISUAL-SYSTEM-WAVE-G`  
状态：**IN PROGRESS**。

### G24.1 — Window metrics

- minimum usable size：960×640；
- default initial size：1180×760；
- 默认尺寸仅用于首次窗口，不锁定用户 resize。

### G24.2 — Inspector metrics

- min 280 / ideal 320 / max 420；
- 使用系统 `.inspectorColumnWidth(min:ideal:max:)`；
- 不创建 NSPanel / NSWindow coordinator。

### G24.3 — Responsive workspace primitive

- `WOMAdaptivePair` 统一宽屏双栏 → 窄屏纵向；
- 保留 13pt body / 11pt metadata；
- 不用负 offset / magic width 解决挤压。

### G24.4 — Production integration

- `ContentView` min size 改为 metrics 单一事实源；
- Fate 局势双栏复用 responsive primitive；
- `WorldOfMysteriesApp` 使用舒适 default size；
- 不改变 IPC / Domain / navigation state。

### G24.5 — Gallery / Contract

- 使用真实 `.inspector` 展示长文本与状态；
- Inspector 280pt 压力场景；
- `VisualWindowLayoutContractTests.swift` 锁定 metrics、native Inspector、no custom window coordinator。

## 8. 生产入口事实

- Sidebar / Fate / Content Shell：真实生产入口。
- Ritual：已有真实组件，无独立一级路由。
- Character / Story Book / Cards / Worldline / Notes：真实领域数据链未就绪时继续保持 placeholder。
- Artifact：作为 Fate 命运干预工具，不额外制造背包一级导航。
- Component Gallery：Showcase / Visual Regression / Visual QA Stress，不代表业务页面完成。
- 多窗口：在没有独立领域工作流前，不新增无意义 standalone WindowGroup。

## 9. Stacked 合并策略

1. #31 先合并后，#32 retarget `main`、重签 Capsule、最终 CI；
2. #32 合并后，Wave G retarget `main`、重签 Capsule、回读纯增量；
3. Wave G 最终 head 只跑一次 `MACOS_APP_P0`；
4. 未经明确授权不执行 merge。

## 10. 恢复入口

`Visual_Asset_System_v1.0.md` → 本文件 → `Visual_QA_Contract_v1.0.md` → Batch 24 → `MAC-VISUAL-SYSTEM-WAVE-G` Capsule → Wave G PR → `WOMWorkspaceLayout` → `MyApp` / `ContentView` → Gallery native Inspector specimen → `VisualWindowLayoutContractTests`。
