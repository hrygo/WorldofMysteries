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

已完成 Wave A–E 的 retroactive contrast / typography / collision / alignment audit、960×640 responsive hardening、shared primitives、15/15 Artifact shared + individual QA、Reduce Motion 和 `VisualQAContractTests.swift`。

#31 尚未由本执行流合并；Wave F 以该已验证 head 作为 stacked base。

## 6. 当前持久化工作流：Wave F — Advanced Interaction & World-State Chrome / PR #32

Branch: `feat/wom-visual-system-wave-f`  
Stacked base: `feat/wom-visual-qa-backfill-v2@8b9ab58428d05762184884c9e60b03f6e8075d71`  
Batch: [`Batch_23_Wave_F_Advanced_Interaction_Chrome.md`](Batch_23_Wave_F_Advanced_Interaction_Chrome.md)  
状态：**IMPLEMENTATION COMPLETE / RETARGET + FINAL CI PENDING**。

### F23.1 — `WOMAdaptiveSegmentedPicker` — DONE

- 原生 SwiftUI `Picker`；
- 宽空间 `.segmented`；
- segmented 保持 intrinsic readable width；
- 窄空间 `ViewThatFits` 自动降级 `.menu`；
- 不使用 Buttons 模拟系统 segmented control；
- 不引入 AppKit bridge。

### F23.2 — `WOMRelationBadge` — DONE

- trusted / aligned / neutral / wary / hostile；
- icon + text + border/shape；
- Differentiate Without Color 使用不同 dash；
- Increased Contrast 增强边界；
- 长标题/详情自然换行；
- 不包含关系分数或持久化。

### F23.3 — `WOMAchievementSeal` — DONE

- locked / discovered / completed；
- 11pt metadata；
- locked 状态仍保持可读；
- icon + text + geometry，非 color-only；
- 长成就名/说明允许多行。

### F23.4 — `WOMCooldownIndicator` — DONE

- ready / cooling / locked；
- determinate `ProgressView`；
- progress 由外部 Runtime/Domain 提供；
- 无 Timer / Task.sleep / repeatForever；
- 不在视觉组件内部制造 availability truth。

### F23.5 — Gallery / Contracts — DONE

- 正常 segmented 与 220pt narrow Inspector fallback specimen；
- 5 种 relationship role；
- 长中英文 hostile label；
- 3 种 achievement state + 长标题；
- ready/cooling/locked cooldown；
- `VisualAdvancedInteractionContractTests.swift` 锁定 native semantics、no timer、no color-only、presentation-only boundary。

## 7. Wave F 当前静态事实

相对 #31 已验证 head 的首次完整实现审计：
- ahead 8 / behind 0；
- 仅 Capsule / Batch / Living Plan、2 个 DesignSystem source、Gallery、1 个 test file；
- 无 Engine / DB / IPC / schema / `.github` / `.hacf` 变化。

后续 audit/test/doc 原子提交仍保持同一授权文件集合。

## 8. 生产入口事实

- Sidebar / Fate / Content Shell：真实生产入口。
- Ritual：已有真实组件，无独立一级路由。
- Character / Story Book / Cards / Worldline / Notes：部分 View primitive 已存在，但真实领域数据链未就绪时继续保持 placeholder。
- Artifact：作为 Fate 命运干预工具，不额外制造背包一级导航。
- Component Gallery：Showcase / Visual Regression / Visual QA Stress，不代表业务页面完成。
- Wave F world-state chrome 当前仅进入 Design System + Gallery；真实领域数据源未就绪前不伪造生产绑定。

## 9. Wave F 合并策略

1. #32 保持 stacked Draft，直至 #31 合并。
2. #31 合并后，将 #32 retarget 到 `main`。
3. 重新核对/reissue Capsule base，使 base SHA 与最新主线一致。
4. 再次回读 diff，确保只剩 Wave F 增量。
5. Mark Ready，并只对最终 Wave F head 执行完整 `MACOS_APP_P0`。
6. 若失败，只做日志驱动的原子 fix。
7. 未经明确指令不执行 merge。

## 10. 后续候选

Wave F 验证完成后再推进：
- 真实领域数据源就绪后的 Relation/Achievement/Cooldown production binding；
- 页面级 Inspector sizing / multi-window strategy；
- 生产 workspace 从 placeholder 迁移时的视觉/数据契约。

任何后续 Wave 继续继承 Visual QA Contract。

## 11. 恢复入口

`Visual_Asset_System_v1.0.md` → 本文件 → `Visual_QA_Contract_v1.0.md` → Batch 23 → `MAC-VISUAL-SYSTEM-WAVE-F` Capsule → PR #32 → `WOMAdaptiveSegmentedPicker` / `WOMWorldStateChrome` → Gallery → `VisualAdvancedInteractionContractTests` → retarget → final CI/readback。
