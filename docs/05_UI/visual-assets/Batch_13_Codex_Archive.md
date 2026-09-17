# Visual Asset System — Batch 13：Codex / Archive 真实组件迁移

> Task：`MAC-VISUAL-CODEX-ARCHIVE`  
> 执行总计划：[`README.md`](README.md)  
> 状态：IMPLEMENTED IN PR #26

## 1. 仓库现状

`ContentView` 中 Story Book 当前仍进入 generic placeholder，因此本批不宣称“Story Book 页面完成”。仓库中真实存在并承载 Codex / Archive 语义的组件是：

- `CharacterCodexCard`
- `TingenCityDossierCard`
- `NarrativeChronicleView`

本批先迁移这三个真实组件。

## 2. Character Codex

- 根卡片切换为 `WOMCardChrome(.card)` + Velvet；
- Character / Spirituality / Voice Advice 使用 typed WOM icon；
- Divider 使用 `WOMDividerOrnament`；
- Advice 行为使用 `WOMButtonStyle(.secondary)`；
- 灵性/理智指标补充 accessibility value；
- hover 动画尊重 reduced motion；
- 人物身份、traits、spirituality、sanity、在线状态及回调语义不变。

## 3. Tingen Dossier

- 根 Surface 使用 `WOMPanelBackground(.panel)` + Sacred Slate；
- Header 的历史 Velvet 资源通过 `WOMTextureLayer` 接入；
- Codex / Clue / Lock / Search 语义进入 typed icon 层；
- status pill 使用统一 Card surface；
- 地点选择动画尊重 reduced motion；
- 地点列表、选中状态、note 与 `onLocationSelected` 语义不变。

## 4. Narrative Chronicle

- 叙事条目切换为 `WOMCardChrome`；
- narrator / character / playerAdvice 各自映射到 typed `WOMIconSource`；
- 原声回放通过 `WOMSystemIcon.audioReplay` + `WOMToolbarButtonStyle`；
- timestamp、正文、空状态和 `onReplayAudio` 语义保持不变。

## 5. 明确边界

- 不把 Story Book placeholder 标记为生产完成；
- 不修改角色/知识边界；
- 不修改领域事实或数据库；
- 不改变音频回调；
- 不重构现有业务数据模型。

## 6. 后续

下一批进入 Artifact / Fate：优先迁移真实 `FateArtifactInterventionView` 与 Artifact 展示链路；继续保持“Artifact 嵌入 Fate，不新增一级背包导航”的产品基线。
