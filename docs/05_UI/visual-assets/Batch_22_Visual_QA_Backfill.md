# Batch 22 — Visual QA Backfill（Wave A–E 历史组件追溯审计）

> 分支：`feat/wom-visual-qa-backfill-v2`  
> PR：#31  
> Base：`main@475949e8d07c99683776faa63c88543e96e8d250`（已包含 Wave E / #29）  
> 状态：IMPLEMENTATION COMPLETE / FINAL AUDIT PENDING

## 1. 目标

将 `Visual_QA_Contract_v1.0.md` 追溯应用到已合入 Wave A–E 的 macOS 视觉系统与主要生产/共享组件。历史代码不豁免。

本批不是重新设计风格，而是做视觉质量治理：
- 对比度；
- 字体可读性；
- 最小窗口与长文本下无重叠；
- 布局基线/间距/对仗；
- accessibility state 稳定退化。

## 2. 量化基线

- 常规正文 / Button / Form text：最终合成对比度 >= **4.5:1**。
- 关键非文本边界 / Focus / Selected / control affordance：>= **3:1**。
- 长正文与关键说明优先向 **7:1** 靠拢。
- 正文默认 >= **13pt**；说明/元数据默认 >= **11pt**。
- 10pt 仅允许短数字 / 快捷键 / 极短标签；9pt 以下不承载关键语义。
- App 最小窗口基线：**960×640**。

## 3. 已确认并修复的问题

### QA-22-001 — Danger Button Contrast
旧组合 `textPrimary` + 半透明 `crimsonStar` 最终合成不足 4.5:1。

**修复**：Danger solid fill 改为 `crimsonThread`，保留 `textPrimary`。当前普通 / hover / pressed / inactive 合成均有更大安全余量。

### QA-22-002 — Ritual Deep-Surface Text
已确认：
- `textTertiary` vs `deepVoid` ≈ 3.56:1；
- `brassGoldMuted` vs `deepVoid` ≈ 3.41:1；
- `spiritualBlue` vs `deepVoid` ≈ 3.75:1；
- 部分 Pathway raw color（如 Fool / Darkness）作为正文色远低于 4.5:1。

**修复**：
- `BronzeAltarPrayerCard`：Pathway 色退出正文职责，仅保留装饰 shadow / border；关键说明改稳定文字 Token。
- `CitrinePendulumScryingCard`：状态色保留在 dot/icon，正文回到 `textPrimary/textSecondary`；仪轨键值行放回 Card Surface。

### QA-22-003 — Sidebar Microcopy
旧 Sidebar 存在 9pt 品牌副标题、Seq / spirituality 文案，以及 `textTertiary.opacity(0.6)` 快捷键（实际约 2.6–2.7:1）。

**修复**：
- 品牌副标题 -> 11pt Caption；
- Seq -> 10pt 短 badge；
- 灵性标签/数值 -> 11pt；
- 快捷键保留 10pt，但提高字重并取消低 opacity；
- 不通过扩大 Sidebar 宽度掩盖问题。

### QA-22-004 — Character Codex Long Content Collision
旧 identity / traits / state / Advice 行均偏单行 HStack，长姓名/途径/标签可能碰撞；低 sanity 数值直接使用低对比 danger 色。

**修复**：
- identity 用 `ViewThatFits` 水平→纵向 fallback；
- traits 用 adaptive grid；
- state metrics 等宽；
-低 sanity 数值回到 `textPrimary`，Danger 语义仍由 Meter 表达；
- Advice 行提供纵向 fallback。

### QA-22-005 — Tingen Dossier Status Layout
旧两张 status card 固定同一行，状态标题 9pt；“红月笼罩”低对比红字叠暗红背景。

**修复**：
- 状态摘要 `ViewThatFits` 横向→纵向 fallback；
- 状态标题升 11pt；
- 红色保留为语义 dot，文字改 `textPrimary`；
- 地标说明允许自然换行。

### QA-22-006 — Narrative Header Collision
长角色名 / speaker badge / timestamp / audio action 旧版固定单行。

**修复**：Header 使用 `ViewThatFits`，空间不足时元数据降到第二行；正文仍保持 16pt narrative style。

### QA-22-007 — Artifact Showcase Header / Dynamic Tone Text
Showcase 标题 + 固定 170pt 搜索框在窄宽度缺乏 fallback；selected artifact label 使用动态 tone 色作为 11pt 文本。

**修复**：
- Header 使用 `ViewThatFits`；
- Search Field 使用 min/ideal/max 弹性宽度；
- Artifact tone 仅用于 icon/chrome，label 文字回到稳定 Token。

### QA-22-008 — ContentView Minimum Window
960pt 总宽减 224pt Sidebar 与内容 padding 后，Fate 主区旧双栏仍固定 280pt 右栏；Settings 固定双列。

**修复**：
- Engine status header 有纵向 fallback；
- Fate 主区用 `ViewThatFits` 双栏→纵向；
- character anchor 内部键值也可纵向；
- Settings 改 adaptive grid；
- 长标题/正文显式允许自然增长。

### QA-22-009 — Fate Artifact 5-card Single Row
5 张含动态文本的快捷卡硬塞单行，最小窗口只能压缩/截断；subtitle 直接使用动态 tone 色。

**修复**：
- 改 adaptive grid；
- title/subtitle 可多行；
- tone 只用于 icon/chrome；
- runtime hint 可换行。

### QA-22-010 — Worldline Metadata / Causal Summary
世界时间 + 回合 + 状态固定单行；关键因果摘要硬截两行。

**修复**：
- metadata `ViewThatFits`；
- cause summary 不再 `lineLimit(2)`；
- title/time 可自然换行。

### QA-22-011 — Shared Artifact Shell
15 件 Artifact 共用 Shell 强制左 >=250 + 右 >=430，最小工作区可能溢出；副标题/Meter 数值依赖动态 tone 色。

**修复**：
- `ArtifactComponentShell` 用 `ViewThatFits` 左右→上下布局；
- badge group adaptive；
- subtitle / meter value 使用稳定文字 Token；
- error message 使用高对比文字；
- 一次覆盖 15 件 Artifact UI Shell。

### QA-22-012 — Shared Mystic Primitive Readability
`MysticBadge` 固定 10pt 且直接使用动态 tone 色；`MysticKeyValueRow` 不能降级布局；Empty/Icon Button 同类色彩风险。

**修复**：
- 新增 `MysticTone.readableForeground`；
- Badge 基线提升至 11pt；
- tone accent 继续用于背景/边界/状态几何，低对比 tone 不再承担关键文字；
- KeyValueRow 支持纵向 fallback；
- EmptyState / IconButton 使用可读前景；
- 状态 dot 增加辅助轮廓。

## 4. Visual QA Stress Surface

Component Gallery 新增 `Visual QA Stress · 可读性与布局压力`：
- 超长中文标题；
- 超长英文标题；
- 多行正文；
- 密集 Badge；
- 长 Warning Banner + action；
- adaptive grid。

同时把 Gallery 自身的固定多列 Icon / Button / Surface / Overlay 样例改为 adaptive grid，避免回归页自身在最小窗口溢出。

## 5. 自动契约

新增 `VisualQAContractTests.swift`，锁定：
- Danger 使用高对比 solid fill；
- Ritual 不再使用不安全动态正文色；
- shared semantic primitive 使用 readable foreground / 11pt Badge；
- Sidebar 不退回 9pt / 0.6 opacity；
- Character / Dossier / Narrative / Worldline 保持 responsive fallback；
- ContentView / Fate Artifact / Showcase / Artifact Shell 保持 adaptive structure；
- Artifact dynamic tone 不退回小字号正文；
- Gallery 必须保留 Visual QA Stress specimen。

## 6. 未修改 / 不应修改

- Engine / Domain / DB / IPC / schema；
- Story / World commit 语义；
- Artifact resolver / model / domain action；
- 业务导航完成度；
- 通过缩小字体或扩大最小窗口掩盖布局问题。

## 7. 原子提交链

实现以原子 commit 持续写入 #31，涵盖：
- Danger button contrast；
- Ritual readability；
- Sidebar microcopy；
- Character Codex responsive；
- Tingen Dossier responsive；
- Narrative responsive；
- Artifact Showcase responsive；
- Content shell minimum-window；
- Fate Artifact adaptive grid；
- Worldline responsive；
- shared Artifact Shell；
- shared Mystic primitives；
- Gallery QA stress；
- Visual QA contract tests。

## 8. 完成条件

当前实现层已收口。最终仅剩：
1. 回读 PR base/head/diff 与 Capsule scope；
2. 静态检查无 Engine / DB / IPC / schema 越界；
3. 将 PR 转 Ready；
4. 对最终 head 执行一次完整 `MACOS_APP_P0`；
5. 若失败，仅做单点原子 fix；
6. CI 全绿后才标记 `READY TO MERGE`。
