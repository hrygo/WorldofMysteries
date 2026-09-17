# Visual Asset System — Living Plan / 当前执行事实源

> 稳定设计基线：[`../Visual_Asset_System_v1.0.md`](../Visual_Asset_System_v1.0.md)  
> Visual QA：[`Visual_QA_Contract_v1.0.md`](Visual_QA_Contract_v1.0.md)  
> Source Guards：[`Visual_QA_Source_Guards_v1.0.md`](Visual_QA_Source_Guards_v1.0.md)

## 1. 持久化与交付规则

- 关键设计判断必须落仓库，不依赖聊天或临时环境。
- 同一阶段采用 **长期持久化 PR + 原子 commit**；PR 不要求最小化。
- 涉及方案时同步提交：Living Plan + Batch + Capsule + 实际代码/测试。
- 稳定增量尽早推远端；最终 head 统一执行 `MACOS_APP_P0`。
- 不绕过主分支保护；写入成功不等于交付完成。
- Visual QA Contract 对历史和未来视觉代码都生效，已合并不是豁免理由。

## 2. 技术与 QA 边界

- 世界观图形：原创 vector asset + typed registry。
- 平台行为/状态：SF Symbols + typed semantic registry。
- Sheet / Popover / Inspector / segmented selection / WindowGroup 优先系统 SwiftUI/macOS 语义；WOM 不伪造系统控件/窗口。
- 常规正文 / Button / Form text 最终对比度 >= **4.5:1**；关键非文本 affordance >= **3:1**。
- body 默认 >= **13pt**；metadata 默认 >= **11pt**；10pt 仅短数字/快捷键/极短标签；9pt 以下不承载关键语义。
- 最小窗口 **960×640** 无结构性重叠；长中英文必须自然增长或 responsive fallback。
- 优先 adaptive Grid / `ViewThatFits`；不得通过缩小字体、负 padding、魔法宽度或抬高最小窗口掩盖空间问题。
- Reduce Motion / Increased Contrast / Differentiate Without Color / Reduce Transparency / Keyboard Focus 必须稳定退化。

## 3. 已合入 main

| 阶段 | PR | 内容 | 状态 |
|---|---|---|---|
| Foundation | #21–#25 | Core/navigation icons、ornament、texture、platform semantics | DONE |
| Wave B | #26 | Icon/Button/Surface、Gallery、Sidebar、Ritual、Codex、Artifact/Fate、Shell | DONE |
| Wave C | #27 | Focus / Contrast / Accessibility states | DONE |
| Wave D | #28 | Asset contracts、typed icon、navigation/commands/focus | DONE |
| Wave E | #29 | Overlay / Feedback / Loading / Status / typed Empty State | DONE |

## 4. 已验证待合并：Visual QA Backfill / PR #31

Branch: `feat/wom-visual-qa-backfill-v2`  
Final head: `8b9ab58428d05762184884c9e60b03f6e8075d71`  
状态：**READY TO MERGE / ALL QUALITY GATES PASSED**。

已完成 Wave A–E 的 retroactive contrast / typography / collision / alignment audit、960×640 responsive hardening、shared primitives、15/15 Artifact individual QA、Reduce Motion 和 `VisualQAContractTests.swift`。

## 5. 已实现待 retarget：Wave F / PR #32

Branch: `feat/wom-visual-system-wave-f`  
Stacked base: `#31@8b9ab58428d05762184884c9e60b03f6e8075d71`  
Head: `a4ae319d48f25b9eadffdf6f8e64845ecc55cada`  
状态：**IMPLEMENTATION COMPLETE / RETARGET + FINAL CI PENDING**。

已实现：
- `WOMAdaptiveSegmentedPicker`：native Picker segmented → menu fallback；
- `WOMRelationBadge`；
- `WOMAchievementSeal`；
- `WOMCooldownIndicator`；
- Gallery narrow/long-label stress；
- `VisualAdvancedInteractionContractTests.swift`。

## 6. 已实现待 retarget：Wave G / PR #33

Branch: `feat/wom-visual-system-wave-g`  
Stacked base: `#32@a4ae319d48f25b9eadffdf6f8e64845ecc55cada`  
Head: `12b3f9a100193b4ad3dba8de3bd43263ba4e6baf`  
状态：**IMPLEMENTATION COMPLETE / RETARGET + FINAL CI PENDING**。

已实现：
- `WOMWindowMetrics`：minimum 960×640 / default 1180×760；
- `WOMInspectorMetrics`：280 / 320 / 420；
- `WOMAdaptivePair`：双栏 → 纵向 fallback；
- `WOMInspectorContent`；
- MyApp `.defaultSize` 与 ContentView shared metrics；
- Native `.inspector` Visual QA Preview；
- `VisualWindowLayoutContractTests.swift`。

## 7. 当前持久化工作流：Wave H — Visual QA Source Guards

Branch: `feat/wom-visual-system-wave-h`  
Stacked base: `#33@12b3f9a100193b4ad3dba8de3bd43263ba4e6baf`  
Batch: [`Batch_25_Wave_H_Visual_QA_Source_Guards.md`](Batch_25_Wave_H_Visual_QA_Source_Guards.md)  
Task: `MAC-VISUAL-QA-SOURCE-GUARDS`  
状态：**IN PROGRESS**。

目标：把已经完成的人工/点名式 QA 回归进一步升级为面向整个生产视觉源码的自动 Guard。

### H25.1 — Small Type Guard

- 扫描直接 `.font(.system(size: ...))`；
- `< 10pt` 失败；
- 不禁止 10pt 短数字/快捷键/短标签。

### H25.2 — No Shrink-to-Fit

- 禁止 `.minimumScaleFactor`；
- 空间不足必须通过换行 / adaptive Grid / `ViewThatFits` 解决。

### H25.3 — Negative Padding Layout Guard

- Components / Artifacts / ContentView 禁止负 padding；
- DesignSystem focus-ring 外扩不做 blanket ban。

### H25.4 — Native Window Guard

- 普通视觉源码禁止 `NSPanel / NSWindow / NSViewRepresentable`；
- 若未来需要 AppKit bridge，必须独立高风险任务评审。

### H25.5 — Source Guard Test Infrastructure

- 递归扫描 production `.swift`；
- 排除 Tests；
- 违规结果包含相对路径、行号与片段；
- 不全局禁止 offset / lineLimit / opacity 等存在合法场景的 API。

## 8. 生产入口事实

- Sidebar / Fate / Content Shell：真实生产入口。
- Ritual：已有真实组件，无独立一级路由。
- Character / Story Book / Cards / Worldline / Notes：真实领域数据链未就绪时继续保持 placeholder。
- Artifact：作为 Fate 命运干预工具，不额外制造背包一级导航。
- Component Gallery / Native Inspector Preview：Showcase / Visual Regression / QA surface，不代表业务页面完成。

## 9. Stacked 合并策略

1. #31 合并 → #32 retarget `main`、重签 Capsule、最终 CI；
2. #32 合并 → #33 retarget `main`、重签 Capsule、最终 CI；
3. #33 合并 → Wave H retarget `main`、重签 Capsule、回读纯增量；
4. Wave H 最终 head 只跑一次 `MACOS_APP_P0`；
5. 未经明确授权不执行 merge。

## 10. 恢复入口

`Visual_Asset_System_v1.0.md` → 本文件 → `Visual_QA_Contract_v1.0.md` → `Visual_QA_Source_Guards_v1.0.md` → Batch 25 → `MAC-VISUAL-QA-SOURCE-GUARDS` Capsule → Wave H PR → `VisualQASourceGuardTests.swift` → retarget → final CI/readback。
