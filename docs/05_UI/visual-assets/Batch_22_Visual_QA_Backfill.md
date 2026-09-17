# Batch 22 — Visual QA Backfill（历史组件追溯审计）

> 分支：`feat/wom-visual-qa-backfill`  
> Base：`main@51a9b2679420edbf1fb9b12189033a2a6cdc8567`  
> 状态：IN PROGRESS

## 1. 目标

将 `Visual_QA_Contract_v1.0.md` 追溯应用到已合入 Wave A–D 的全部 macOS 视觉系统与生产组件，并在 #29 合并前对 Wave E 使用相同标准复核。

本批不是重新设计风格，而是做视觉质量治理：
- 对比度；
- 字体可读性；
- 最小窗口与长文本下无重叠；
- 布局基线/间距/对仗；
- accessibility state 稳定退化。

## 2. 审计对象

### Design System
- `WOMButtonStyles.swift`
- `WOMSurfaceStyles.swift`
- `WOMIcon.swift`
- `InteractionStyles.swift`
- `DesignTokens.swift`

### Production / shared components
- `AppSidebarView`
- `ContentView` shell
- Ritual：`BronzeAltarPrayerCard` / `CitrinePendulumScryingCard`
- Codex / Archive：`CharacterCodexCard` / `TingenCityDossierCard` / `NarrativeChronicleView`
- Fate / Artifact：`FateArtifactInterventionView` / `ArtifactShowcaseView`
- Component Gallery

## 3. 第一轮已发现问题

### QA-22-001 Danger Button Contrast
`WOMButtonStyle(.danger)` 当前组合：
- foreground: `textPrimary #F5F6F8`
- background: `crimsonStar #E63946`
- 对比度约 **3.85:1**

常规按钮文字不满足 4.5:1 目标。候选修复：实心 Danger 状态使用 `obsidianBase #0D0F12` 作为前景，组合约 **4.60:1**；并继续验证 hover / inactive opacity 的最终合成结果。

### QA-22-002 Deep-Void Small Text Risk
- `textTertiary` vs `deepVoid` ≈ **3.56:1**
- `brassGoldMuted` vs `deepVoid` ≈ **3.41:1**

在 Ritual/deepVoid Surface 中不得用于 11–13pt 关键文字。逐组件核对后升级为 `textSecondary` / `brassGoldPrimary` / `textGoldAccent` 等符合语义的更高对比度 Token。

## 4. 字体规则追溯检查

重点扫描：
- `.font(.system(size: 9...10))`
- 关键说明使用 `caption` 以下字号；
- 极低 opacity 的 `textSecondary/textTertiary`；
- `lineLimit(1)` 截断关键标题；
- 小字号叠加纹理/Glow。

修复原则：
- 正文 >=13pt；
- 说明/元数据默认 >=11pt；
- 10pt 只保留短数字/快捷键/极短 badge；
- 9pt 以下不承载关键语义。

## 5. 布局压力检查

重点扫描：
- 固定 `.frame(width:)` / `.frame(height:)`；
- 多列 `HStack` 在 960pt 下的宽度预算；
- `overlay` 内含可增长文本/按钮；
- `offset` / 负 padding；
- Badge/状态值/英文长文本造成的挤压；
- 卡片组高度与标题基线不一致。

最小窗口基线：960×640。

## 6. 计划中的原子修复

1. `fix(macos): raise danger button text contrast`
2. `fix(macos): harden ritual text contrast`
3. `fix(macos): raise microcopy legibility in sidebar and cards`
4. `fix(macos): harden responsive component layouts`
5. `test(macos): enforce visual QA contracts`
6. `feat(macos): add visual QA stress specimens`

具体提交以实际审计结果为准，不为了凑提交数量修改无问题代码。

## 7. 完成条件

- 主要文字/Surface 组合满足 Contract；
- 无已知关键 9pt 文本；
- 960pt 最小窗口关键生产组件无明显结构性重叠风险；
- 长文本与 Badge 压力有明确 layout 策略；
- Gallery 有 Visual QA stress specimen；
- 新增 contract tests；
- 最终 head 通过 `MACOS_APP_P0`。
