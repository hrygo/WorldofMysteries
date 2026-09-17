# Visual Asset System — 执行总体方案与持久化规则

> 稳定设计基线：[`../Visual_Asset_System_v1.0.md`](../Visual_Asset_System_v1.0.md)  
> 当前执行事实源：本文件。  
> Visual QA：[`Visual_QA_Contract_v1.0.md`](Visual_QA_Contract_v1.0.md)

## 1. 持久化与交付规则

- 关键设计判断必须落仓库，不依赖聊天或临时环境。
- 同一阶段采用 **长期持久化 PR + 原子 commit**；PR 不要求最小化。
- 涉及方案时同步提交：总体/Living Plan + Batch + Capsule + 实际代码/测试。
- 稳定增量尽早推远端；最终 head 统一执行 `MACOS_APP_P0`。
- 不绕过主分支保护；写入成功不等于交付完成。
- Visual QA Contract 对历史和未来视觉代码都生效，已合并不是豁免理由。

## 2. 技术边界

- 世界观图形：原创 vector asset + typed registry。
- 平台行为/状态：SF Symbols + typed semantic registry。
- Hover / Pressed / Selected / Focused / Disabled / Loading：SwiftUI style + Design Token 驱动。
- Sheet / Popover / Inspector / Tab / segmented selection 优先系统 SwiftUI/macOS 语义；WOM 只补视觉和语义封装，不伪造系统控件。
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
- Reduce Motion 必须在组件内部生效；状态不得仅靠颜色表达。

## 4. 已合入 main

| 阶段 | PR | 内容 | 状态 |
|---|---|---|---|
| Foundation | #21–#25 | Core/navigation icons、ornament、texture、platform semantics | DONE |
| Wave B | #26 | Icon/Button/Surface、Gallery、Sidebar、Ritual、Codex、Artifact/Fate、Shell | DONE |
| Wave C | #27 | Focus / Contrast / Accessibility states | DONE |
| Wave D | #28 | Asset contracts、typed icon、navigation/commands/focus | DONE |
| Wave E | #29 | Overlay / Feedback / Loading / Status / typed Empty State | DONE |

`main` 当前仍为 `475949e8d07c99683776faa63c88543e96e8d250`（包含 #29）。

## 5. 已验证待合并：Visual QA Backfill / PR #31

Branch: `feat/wom-visual-qa-backfill-v2`  
Final head: `8b9ab58428d05762184884c9e60b03f6e8075d71`

状态：**READY TO MERGE / ALL QUALITY GATES PASSED**。

已完成：
- Wave A–E retroactive contrast / typography / collision / alignment audit；
- 960×640 minimum-window responsive hardening；
- shared Mystic primitives / Overlay / Gallery stress；
- 15/15 Artifact shared + individual visual QA；
- Reduce Motion / long-content / dynamic tone text remediation；
- `VisualQAContractTests.swift` regression contract。

#31 尚未由本执行流合并；后续 Wave F 以其已验证 head 作为 stacked base。

## 6. 当前持久化工作流：Wave F — Advanced Interaction & World-State Chrome

Branch: `feat/wom-visual-system-wave-f`  
Stacked base: `feat/wom-visual-qa-backfill-v2@8b9ab58428d05762184884c9e60b03f6e8075d71`  
Batch: [`Batch_23_Wave_F_Advanced_Interaction_Chrome.md`](Batch_23_Wave_F_Advanced_Interaction_Chrome.md)

### F23.1 — Adaptive segmented mode selection

- 使用原生 `Picker`；
- 宽度充足时 `.segmented`；
- 空间不足时通过 `ViewThatFits` 降级为 `.menu`；
- 不用 Buttons 模拟 `NSSegmentedControl`；
- keyboard / focus / accessibility 保持系统语义。

### F23.2 — Relationship chrome

新增 presentation-only `WOMRelationBadge`：trusted / aligned / neutral / wary / hostile。

- icon + text + border/shape 同时表达；
- 不做 color-only state；
- 不引入关系持久化或领域分数。

### F23.3 — Achievement seal

新增 `WOMAchievementSeal`：locked / discovered / completed。

- locked 仍保持可读；
- completed 用 icon/geometry + text，而非只靠颜色；
- 长名称允许换行。

### F23.4 — Cooldown / availability indicator

新增 `WOMCooldownIndicator`：ready / cooling / locked。

- UI 仅呈现外部提供的 progress / remaining label；
- 不在视觉组件内部实现游戏计时器或 wall-clock truth；
- 不增加无限动画。

### F23.5 — Gallery / Tests

- Advanced interaction specimens；
- narrow width / long Chinese / long English / differentiate-without-color stress；
- `VisualAdvancedInteractionContractTests.swift`。

## 7. 生产入口事实

- Sidebar / Fate / Content Shell：真实生产入口。
- Ritual：已有真实组件，无独立一级路由。
- Character / Story Book / Cards / Worldline / Notes：部分 View primitive 已存在，但真实领域数据链未就绪时继续保持 placeholder。
- Artifact：作为 Fate 命运干预工具，不额外制造背包一级导航。
- Component Gallery：Showcase / Visual Regression / Visual QA Stress，不代表业务页面完成。

## 8. Wave F 合并策略

1. Wave F 先作为 stacked Draft PR 持久化。
2. #31 合并后，Wave F retarget 到 `main`。
3. 重新核对/reissue Capsule base，确保 base SHA 与主线一致。
4. 只对最终 Wave F head 跑完整 `MACOS_APP_P0`。
5. 未经明确指令不执行 merge。

## 9. 恢复入口

`Visual_Asset_System_v1.0.md` → 本文件 → `Visual_QA_Contract_v1.0.md` → Batch 23 → `MAC-VISUAL-SYSTEM-WAVE-F` Capsule → Wave F PR → Advanced Interaction primitives → Gallery → contract tests → final CI/readback。
