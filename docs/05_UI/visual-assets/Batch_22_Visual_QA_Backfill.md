# Batch 22 — Visual QA Backfill（Wave A–E 历史组件追溯审计）

> 分支：`feat/wom-visual-qa-backfill-v2`  
> PR：#31  
> Base：`main@475949e8d07c99683776faa63c88543e96e8d250`（已包含 Wave E / #29）  
> 状态：IMPLEMENTATION COMPLETE / FINAL CI PENDING

## 1. 目标

将 `Visual_QA_Contract_v1.0.md` 追溯应用到已合入 Wave A–E 的 macOS 视觉系统、生产入口、共享 primitive、历史组件与 15 件 Artifact 个体 View。历史代码不豁免。

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
**修复**：Pathway 色退出正文职责；状态色保留在 dot/icon；正文回稳定文字 Token；仪轨键值行落 Card Surface。

### QA-22-003 — Sidebar Microcopy
旧 Sidebar 有 9pt 品牌/状态微文案，以及 `textTertiary.opacity(0.6)` 快捷键。  
**修复**：品牌/灵性元数据升至 11pt；Seq 保留 10pt 短 badge；快捷键取消低 opacity 并提高字重；不扩大 Sidebar 宽度。

### QA-22-004 — Character Codex Long Content Collision
姓名、途径 badge、traits、状态、Advice 对长内容不稳；低 sanity 数值直接使用 danger 色。  
**修复**：identity `ViewThatFits`；traits adaptive grid；state 等宽；Advice fallback；低 sanity 数字回高对比文字。

### QA-22-005 — Tingen Dossier Status Layout
状态摘要固定同一行、状态标题 9pt、红月文字对比不足。  
**修复**：摘要横向→纵向 fallback；标题 11pt；红色保留为 dot；地标说明自然换行。

### QA-22-006 — Narrative Header Collision
长角色名 / speaker badge / timestamp / audio action 固定单行。  
**修复**：Header 使用 `ViewThatFits`；空间不足时 metadata 下移；正文维持 16pt narrative style。

### QA-22-007 — Artifact Showcase Header / Dynamic Tone Text
标题 + 固定 170pt 搜索框无 fallback；selected label 用动态 tone 小字。  
**修复**：Header `ViewThatFits`；Search Field 使用 min/ideal/max；tone 只做 icon/chrome。

### QA-22-008 — ContentView Minimum Window
960pt 下 Fate 固定双栏与 280pt 右栏挤压；Settings 固定双列。  
**修复**：Engine header、Fate、内部键值都可纵向 fallback；Settings adaptive grid；长文本自然增长。

### QA-22-009 — Fate Artifact 5-card Single Row
5 张动态内容卡强制单行；subtitle 使用动态 tone 色。  
**修复**：adaptive grid；title/subtitle 多行；tone 只用于 icon/chrome；runtime hint 可换行。

### QA-22-010 — Worldline Metadata / Causal Summary
世界时间 + 回合 + 状态固定单行；关键因果摘要硬截两行。  
**修复**：metadata `ViewThatFits`；cause summary 不再 `lineLimit(2)`。

### QA-22-011 — Shared Artifact Shell
15 件 Artifact 共用 Shell 强制左 >=250 + 右 >=430；副标题/Meter 数值依赖动态 tone 色。  
**修复**：Shell 左右→上下 fallback；badge adaptive；subtitle / meter / error 使用稳定高对比文字。

### QA-22-012 — Shared Mystic Primitive Readability
`MysticBadge` 固定 10pt 且直接使用动态 tone 色；KeyValueRow 无窄宽 fallback。  
**修复**：新增 `MysticTone.readableForeground`；Badge 11pt；KeyValueRow responsive；Empty/IconButton 使用可读前景；status dot 增加轮廓。

### QA-22-013 — Overlay / Feedback Long-content Collision
`WOMStatusBanner` 固定“icon + text + action”单行。  
**修复**：`ViewThatFits` 横向→纵向；Loading / Empty / Banner 允许自然换行。

### QA-22-014 — Spirituality Gauge Low-value Text
低值 11pt 百分比使用 `statusDanger`，在 `obsidianCard` 上约 3.61:1。  
**修复**：危险语义由红色仪表弧表达，低值数字改 `textPrimary`。

### QA-22-015 — Listening Ring Motion / Icon Contrast
旧组件无条件循环呼吸/旋转；interpreting 图标使用低 opacity `spiritualGlow`。  
**修复**：组件内部读取 Reduce Motion；关闭循环动画；interpreting 使用 `spiritualBlue`；提示可多行。

### QA-22-016 — Backlund Metropolis Dense Layout
9pt 文案、双状态卡固定单行、城区名 + danger badge 固定 HStack、选中动画忽略 Reduce Motion。  
**修复**：11pt microcopy；状态/城区 header `ViewThatFits`；描述自然换行；动画尊重 Reduce Motion。

### QA-22-017 — Crimson Star Beacon
`灰雾共鸣` 11pt 红字约 3.93:1；长星名+状态固定一行；Prayer 截断；脉冲无视 Reduce Motion。  
**修复**：红色退回 dot/chrome；文字改 `textSecondary`；header fallback；Prayer 自然增长；脉冲遵守 Reduce Motion。

### QA-22-018 — Legacy Spirit Pendulum
状态 caption 使用 `auraColor`；标题+状态、说明+按钮固定单行；循环占卜动画无视 Reduce Motion。  
**修复**：状态色退回 dot/border；正文使用 parchment ink；`ViewThatFits`；长文自然换行；循环动画尊重 Reduce Motion。

### QA-22-019 — 15/15 Artifact Individual View Audit
共享 Shell 修复后继续逐件审计，避免个体 View 重新引入固定横排、动态 tone 正文或 9pt 关键文本。

已覆盖：
1. Probability Die — header / meter / result action / history adaptive；危险/error 文字稳定化。
2. Arrodes — header / focus grid / ask footer / exchange actions responsive；拒答使用 `WOMButtonStyle(.danger)`。
3. Alzuhod Quill — 三指标 adaptive；Picker / badges / footer fallback；error text 高对比。
4. Trunsoest Brass Book — header / Picker / rule footer fallback；TextEditor 显式可读前景。
5. Magic Wishing Lamp — Meter+commit fallback；sealed explanation adaptive grid。
6. Creeping Hunger — header / soul invocation footer responsive；长 soul/pathway 可增长。
7. Leymano Travels — header / record footer / page metadata fallback；长 ability/source 可增长。
8. Groselle Travels — header responsive。
9. Azik Copper Whistle — 清除 9pt 投递状态；投递 timeline adaptive；信件/信使 footer fallback。
10. Cards of Blasphemy — card name 不再单行截断；header responsive。
11. Sea God Scepter — header / intensity / prayer response responsive；祈祷文案自然增长。
12. Staff of Stars — header / projection footer responsive；target 不再两行硬截。
13. Box of Great Old Ones — header responsive；第三层 danger 语义由 icon/chrome 表达，正文高对比。
14. Death Knell — reticle + weakness list 双栏→纵向 fallback；trigger footer responsive。
15. Unshadowed Crucifix — target ID 不截断；intensity/action responsive；三阶段 pipeline adaptive grid。

同时 `VisualQAContractTests` 新增个体 Artifact 合同，锁定这些结构不回退。

## 4. 已审计且无需修改

- `AdviceInputField`：13pt 输入、11pt 提示、按钮对比度与最小窗口空间合理；
- `DatabaseStatusHUDCard`：正文/元数据字号与色彩达标，父级 Settings adaptive grid 保障布局；
- `TarotCardView`：11pt stage text 在 Card Surface 上达标，固定卡牌几何属于产品比例；
- `CluePinboardNodeView`：纸张 ink / crimson / tertiary 与 parchment surface 对比度达标，固定宽度属于 pinboard card 设计。

## 5. Visual QA Stress Surface

Component Gallery 新增 `Visual QA Stress · 可读性与布局压力`：超长中英文、多行正文、密集 Badge、长 Warning Banner + action、adaptive grid。Gallery 自身固定多列样例也改为 adaptive。

## 6. 自动契约

`VisualQAContractTests.swift` 锁定：
- Danger / Ritual / shared primitive 可读性；
- Sidebar microcopy；
- Character / Dossier / Narrative / Worldline responsive；
- ContentView / Fate / Showcase / Artifact Shell adaptive；
- Overlay Status responsive；
- Listening / Backlund / Crimson / Spirit / Gauge；
- **15/15 Artifact 个体 View 的 responsive / text-first 合同**；
- Gallery Visual QA Stress specimen。

## 7. 未修改 / 不应修改

- Engine / Domain / DB / IPC / schema；
- Story / World commit 语义；
- Artifact resolver / model / domain action；
- 业务导航完成度；
- 不通过缩小字体或扩大最小窗口掩盖布局问题。

## 8. 完成条件

实现与文档已收口。最终仅剩：
1. 回读最终 PR base/head/diff 与 Capsule scope；
2. 对最终 head 执行完整 `MACOS_APP_P0`；
3. 若失败，仅做单点原子 fix；
4. CI 全绿后更新本文件为 `READY TO MERGE`，不再修改实现代码。
