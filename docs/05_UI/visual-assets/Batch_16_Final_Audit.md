# Visual Asset System — Batch 16：最终静态审计与兼容修复

> Task：`MAC-VISUAL-SYSTEM-WAVE-B`  
> 执行总计划：[`README.md`](README.md)  
> 状态：STATIC AUDIT COMPLETE / READY FOR FINAL CI

## 1. PR 结构审计

以 `main@33a2ac58e8d59bdeb3200f3c8c0d1fec552ea1e8` 对比 PR #26 head：

- head ahead 13 / behind 0；
- 13 个语义原子 commit；
- 48 个 changed files；
- 变更集中于 Task Capsules、`docs/05_UI/visual-assets/`、DesignSystem、视觉资产及明确授权的 macOS UI/Artifact 文件；
- Engine / DB / IPC / schema contract 未进入 diff。

## 2. 发现并修复：WOMTextureAsset 兼容性

审计发现 `main` 在 Wave B 开始前已经存在 `WOMTextureAsset.swift`，原 API 为：

```text
grayFogSoft
agedGold
parchment
sacredSlate
velvet
semanticKey
```

Batch 06 早期实现误将该文件视为新文件，重写为 `foolVeil / gold / ...`，会造成原有调用能力回退。

本审计修复为：

- 完整保留 `grayFogSoft / agedGold / parchment / sacredSlate / velvet`；
- 完整保留 `semanticKey`；
- 增加 `foolVeil` → `.grayFogSoft` 兼容别名；
- 增加 `gold` → `.agedGold` 兼容别名；
- 不复制任何大纹理二进制。

因此既保护既有 API，也允许 Wave B 新组件使用更直接的语义别名。

## 3. Token/API 核对

直接对照当前 `DesignTokens.swift` 确认新 primitive 使用的 Token 均真实存在：

- `Interaction.pressedScale`
- `Interaction.pressedOpacity`
- `Interaction.selectedBorderWidth`
- `Interaction.selectedShadowRadius`
- `Interaction.clickSpring`
- `Interaction.hoverAnimation`
- `Interaction.selectionSpring`
- `Motion.smoothSpring`
- `Accessibility.focusRingWidth / focusRingOffset`

未创建第二套常量源。

## 4. 最终门禁策略

按当前持久化规则，不为 13 个原子 commit 分别重复跑 CI。

下一步只对最终 PR #26 head 执行一次完整权威门禁：

1. Task Capsule & Evidence Audit；
2. Architecture Fitness / Contracts；
3. Python suite；
4. Swift 6 suite；
5. Xcode App Target build；
6. PR Gate Reporter。

若失败，只用新的原子 fix commit 修复失败项，然后重新验证最终 head。
