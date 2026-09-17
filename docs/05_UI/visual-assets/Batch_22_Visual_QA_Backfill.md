# Batch 22 — Visual QA Backfill（Wave A–E 历史组件追溯审计）

> 分支：`feat/wom-visual-qa-backfill-v2`  
> PR：#31  
> Base：`main@475949e8d07c99683776faa63c88543e96e8d250`（已包含 Wave E / #29）  
> 状态：IMPLEMENTATION COMPLETE / FINAL CI PENDING

## 1. 目标

将 `Visual_QA_Contract_v1.0.md` 追溯应用到已合入 Wave A–E 的 macOS 视觉系统、生产入口、共享 primitive 与主要历史组件。历史代码不豁免。

硬性目标：
- 对比度符合最佳实践；
- 字体清晰可辨；
- 最小窗口 / 长文本下无结构性重叠；
- 布局基线、间距、对仗稳定；
- Reduce Motion / Increase Contrast / Differentiate Without Color 等辅助功能可稳定退化。

## 2. 量化基线

- 常规正文 / Button / Form text：最终合成对比度 >= **4.5:1**。
- 关键非文本边界 / Focus / Selected / control affordance：>= **3:1**。
- 长正文与关键说明优先向 **7:1** 靠拢。
- 正文默认 >= **13pt**；说明/元数据默认 >= **11pt**。
- 10pt 仅允许短数字 / 快捷键 / 极短标签；9pt 以下不承载关键语义。
- App 最小窗口基线：**960×640**。

## 3. 已确认并修复的问题

### QA-22-001 — Danger Button Contrast
旧 `textPrimary` + 半透明 `crimsonStar` 最终合成不足 4.5:1。

**修复**：Danger solid fill 改为 `crimsonThread`，保留 `textPrimary`。

### QA-22-002 — Ritual Deep-Surface Text
`textTertiary / brassGoldMuted / spiritualBlue / 部分 Pathway raw color` 在 `deepVoid` 上不足以承担小字号正文。

**修复**：
- `BronzeAltarPrayerCard`：Pathway 色退出正文职责，仅保留装饰 shadow / border；
- `CitrinePendulumScryingCard`：状态色保留在 dot/icon，正文回到稳定文字 Token；仪轨键值行落 Card Surface。

### QA-22-003 — Sidebar Microcopy
旧 Sidebar 有 9pt 品牌/状态微文案，以及 `textTertiary.opacity(0.6)` 快捷键。

**修复**：品牌/灵性元数据升至 11pt；Seq 保留 10pt 短 badge；快捷键取消低 opacity 并提高字重；不通过扩大 Sidebar 宽度掩盖问题。

### QA-22-004 — Character Codex Long Content Collision
姓名、途径 badge、traits、状态、Advice 旧结构对长内容不稳；低 sanity 数值直接使用 danger 色。

**修复**：identity `ViewThatFits`；traits adaptive grid；state 等宽；Advice fallback；低 sanity 数字回到高对比文字，危险语义由 Meter 表达。

### QA-22-005 — Tingen Dossier Status Layout
状态摘要固定同一行、状态标题 9pt、红月文字对比不足。

**修复**：摘要横向→纵向 fallback；标题 11pt；红色保留为 dot，文字用高对比前景；地标说明允许自然换行。

### QA-22-006 — Narrative Header Collision
长角色名 / speaker badge / timestamp / audio action 固定单行。

**修复**：Header 使用 `ViewThatFits`；空间不足时 metadata 下移；正文维持 16pt narrative style。

### QA-22-007 — Artifact Showcase Header / Dynamic Tone Text
标题 + 固定 170pt 搜索框在窄宽度无 fallback；selected label 用动态 tone 小字。

**修复**：Header `ViewThatFits`；Search Field 使用 min/ideal/max；动态 tone 只做 icon/chrome，文字回稳定 Token。

### QA-22-008 — ContentView Minimum Window
960pt 总宽下 Fate 固定双栏与 280pt 右栏挤压；Settings 固定双列。

**修复**：Engine header 可纵向；Fate 双栏→纵向；内部键值可纵向；Settings adaptive grid；长标题/正文自然增长。

### QA-22-009 — Fate Artifact 5-card Single Row
5 张动态内容卡强制单行，最小窗口只能压缩/截断；subtitle 使用动态 tone 色。

**修复**：adaptive grid；title/subtitle 多行；tone 只用于 icon/chrome；runtime hint 可换行。

### QA-22-010 — Worldline Metadata / Causal Summary
世界时间 + 回合 + 状态固定单行；关键因果摘要硬截两行。

**修复**：metadata `ViewThatFits`；cause summary 不再 `lineLimit(2)`；title/time 自然换行。

### QA-22-011 — Shared Artifact Shell
15 件 Artifact 共用 Shell 强制左 >=250 + 右 >=430；副标题/Meter 数值依赖动态 tone 色。

**修复**：Shell 左右→上下 fallback；badge adaptive；subtitle / meter / error 使用稳定高对比文字。

### QA-22-012 — Shared Mystic Primitive Readability
`MysticBadge` 固定 10pt 且直接使用动态 tone 色；KeyValueRow 无窄宽度 fallback。

**修复**：新增 `MysticTone.readableForeground`；Badge 基线 11pt；KeyValueRow responsive；Empty/IconButton 使用可读前景；status dot 增加轮廓。

### QA-22-013 — Overlay / Feedback Long-content Collision
`WOMStatusBanner` 旧结构固定“icon + text + action”单行，在 Inspector / Popover 窄宽度可能将正文压成窄列。

**修复**：`ViewThatFits` 横向→纵向；Loading / Empty / Banner 标题与正文显式允许自然换行。

### QA-22-014 — Spirituality Gauge Low-value Text
低值 11pt 百分比使用 `statusDanger`，在 `obsidianCard` 上约 3.61:1。

**修复**：危险语义继续由红色仪表弧表达，低值数字改 `textPrimary`；中/高值保持达标 warning/blue。

### QA-22-015 — Listening Ring Motion / Icon Contrast
旧组件无条件启动 `repeatForever` 呼吸/旋转，Reduce Motion 不生效；interpreting 图标使用带低 opacity 的 `spiritualGlow`。

**修复**：组件内部读取 `accessibilityReduceMotion`；关闭循环动画/旋转/脉冲；interpreting 图标使用稳定 `spiritualBlue`；提示文字允许多行。

### QA-22-016 — Backlund Metropolis Dense Layout
存在 9pt 文案、双状态卡固定单行、城区名 + danger badge 固定 HStack、选中动画忽略 Reduce Motion。

**修复**：11pt microcopy；状态块和城区 header `ViewThatFits`；描述自然换行；选中动画尊重 Reduce Motion。

### QA-22-017 — Crimson Star Beacon
`灰雾共鸣` 11pt 红字在 Card Surface 上约 3.93:1；长星名+状态固定一行；祈祷 preview 硬截两行；脉冲动画无视 Reduce Motion。

**修复**：红色退回 dot/chrome，文字改 `textSecondary`；header fallback；Prayer 自然增长；脉冲遵守 Reduce Motion；数字 badge 保持 10pt 短数据用途。

### QA-22-018 — Legacy Spirit Pendulum
状态 caption 直接使用 `auraColor`（静止态含 0.4 opacity）；标题+状态、说明+按钮均固定单行；循环占卜动画无视 Reduce Motion。

**修复**：状态色退回 dot/border，正文使用 parchment ink；上下两处 `ViewThatFits`；statement/guidance 自然换行；循环动画遵守 Reduce Motion；操作按钮使用 WOM Button primitive。

## 4. 已审计且无需修改

以下组件当前未发现需要为本 Contract 额外修改的明确问题：
- `AdviceInputField`：13pt 输入、11pt提示、按钮对比度与最小窗口空间均合理；
- `DatabaseStatusHUDCard`：正文/元数据字号与色彩组合达标，Settings 已由父级 adaptive grid 保障布局；
- `TarotCardView`：11pt stage text 在 Card Surface 上达标，固定卡牌几何属于产品卡牌比例；
- `CluePinboardNodeView`：纸张 ink / crimson / tertiary 与 parchment surface 对比度达标；固定宽度属于 pinboard card 设计而非窗口主布局。

## 5. Visual QA Stress Surface

Component Gallery 新增 `Visual QA Stress · 可读性与布局压力`：
- 超长中文 / 英文标题；
- 多行正文；
- 密集 Badge；
- 长 Warning Banner + action；
- adaptive grid。

Gallery 自身固定多列 Icon / Button / Surface / Overlay 样例也改为 adaptive，避免回归页自身在最小窗口失真。

## 6. 自动契约

`VisualQAContractTests.swift` 锁定：
- Danger / Ritual / shared primitive 可读性；
- Sidebar microcopy；
- Character / Dossier / Narrative / Worldline responsive fallback；
- ContentView / Fate / Showcase / Artifact Shell adaptive structure；
- Overlay Status responsive fallback；
- Listening / Backlund / Crimson / Spirit 的 Reduce Motion 与布局边界；
- Gauge low-value text；
- Artifact 动态 tone 不退回小字号正文；
- Gallery Visual QA Stress specimen 持久存在。

## 7. 未修改 / 不应修改

- Engine / Domain / DB / IPC / schema；
- Story / World commit 语义；
- Artifact resolver / model / domain action；
- 业务导航完成度；
- 通过缩小字体或扩大最小窗口掩盖布局问题。

## 8. 完成条件

实现与文档已收口。最终仅剩：
1. 回读最终 PR base/head/diff 与 Capsule scope；
2. 对最终 head 执行完整 `MACOS_APP_P0`；
3. 若失败，仅做单点原子 fix；
4. CI 全绿后更新本文件为 `READY TO MERGE`，不再修改实现代码。
