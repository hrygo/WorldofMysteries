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
- readable text contrast >= **4.5:1**；关键 non-text affordance >= **3:1**；长正文优先 >= **7:1**。
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

已实现：native segmented → menu fallback、Relation Badge、Achievement Seal、Cooldown Indicator、Gallery stress、`VisualAdvancedInteractionContractTests.swift`。

## 6. 已实现待 retarget：Wave G / PR #33

Branch: `feat/wom-visual-system-wave-g`  
Stacked base: `#32@a4ae319d48f25b9eadffdf6f8e64845ecc55cada`  
Head: `12b3f9a100193b4ad3dba8de3bd43263ba4e6baf`  
状态：**IMPLEMENTATION COMPLETE / RETARGET + FINAL CI PENDING**。

已实现：

- `WOMWindowMetrics`：minimum 960×640 / default 1180×760；
- `WOMInspectorMetrics`：280 / 320 / 420；
- `WOMAdaptivePair`；
- `WOMInspectorContent`；
- MyApp `.defaultSize` / ContentView shared metrics；
- Native `.inspector` Visual QA Preview；
- `VisualWindowLayoutContractTests.swift`。

## 7. 已实现待 retarget：Wave H / PR #34 — Visual QA Source Guards

Branch: `feat/wom-visual-system-wave-h`  
Stacked base: `#33@12b3f9a100193b4ad3dba8de3bd43263ba4e6baf`  
Batch: [`Batch_25_Wave_H_Visual_QA_Source_Guards.md`](Batch_25_Wave_H_Visual_QA_Source_Guards.md)  
Task: `MAC-VISUAL-QA-SOURCE-GUARDS`  
状态：**IMPLEMENTATION COMPLETE / UPSTREAM RECONCILE + FINAL CI PENDING**。

### Source Guards

- 生产视觉直接 system font `<10pt` 自动失败；
- `.minimumScaleFactor` 自动失败；
- Components / Artifacts / ContentView 负 padding 自动失败；
- 视觉层 `NSPanel / NSWindow / NSViewRepresentable` 自动失败；
- 违规日志包含相对路径、行号和源码片段；
- 不 blanket-ban offset / lineLimit / opacity / 10pt short metadata。

### Contrast Guards

`VisualContrastContractTests.swift` 直接解析 `DesignTokens.swift` RGB Token 并计算 WCAG ratio：

- AAA/长文本批准组合 >= 7:1；
- 常规 readable text 批准组合 >= 4.5:1；
- Danger 锁定 `textPrimary / crimsonThread`；
- Parchment primary/secondary/tertiary hierarchy 数学验证；
- 动态 Pathway/accent/status 色如要承担正文，必须先进入 Approved Contrast Matrix。

## 8. 生产入口事实

- Sidebar / Fate / Content Shell：真实生产入口。
- Ritual：已有真实组件，无独立一级路由。
- Character / Story Book / Cards / Worldline / Notes：真实领域数据链未就绪时继续保持 placeholder。
- Artifact：作为 Fate 命运干预工具，不额外制造背包一级导航。
- Component Gallery / Native Inspector Preview：Showcase / Visual Regression / QA surface，不代表业务页面完成。

## 9. Stacked 合并策略

1. #31 合并 → #32 retarget `main`、重签 Capsule、最终 CI；
2. #32 合并 → #33 retarget `main`、重签 Capsule、最终 CI；
3. #33 合并 → #34 retarget `main`、重签 Capsule、回读 Source Guard/Contrast Guard 纯增量；
4. #34 最终 head 运行完整 `MACOS_APP_P0`，首次执行若发现历史残留则修实现，不放宽规则掩盖问题；
5. 未经明确授权不执行 merge。

## 10. 后续候选

在 Source Guard 经最终 CI 验证后，再推进新的业务视觉能力；优先顺序：

- production Inspector binding（仅真实领域数据就绪后）；
- placeholder workspace 数据接入后的 NavigationSplitView / Inspector contract；
- 独立 Codex/Story Book window 仅在具备独立工作流与 state restoration 语义后评估；
- window restore / zoom / multi-window policy。

## 11. 恢复入口

`Visual_Asset_System_v1.0.md` → 本文件 → `Visual_QA_Contract_v1.0.md` → `Visual_QA_Source_Guards_v1.0.md` → Batch 25 → `MAC-VISUAL-QA-SOURCE-GUARDS` Capsule → PR #34 → `VisualQASourceGuardTests.swift` + `VisualContrastContractTests.swift` → retarget → final CI/readback。
