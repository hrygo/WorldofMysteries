# Batch 28 — Premium Art Program A0 / Research & Implementation Plan

> 状态：A0 PLAN COMPLETE / PR VALIDATION PENDING  
> Branch：`feat/premium-world-artifact-plan`  
> Base：`main@33ff760a1bd939556a7c93ca760e4413dfb42a6e`  
> Task：`MAC-PREMIUM-ART-PLAN`

## 1. Why this batch exists

Visual System Foundation + Wave B–H 已完成工程底座，但用户复核指出一个真实缺口：此前几乎没有建立高品质世界观插画层，Artifact 组件的 primary identity 仍大量依赖 SF Symbol / 程序化氛围，而不是物件本体高品质视觉。

本 Batch 不把前面的工程工作视为错误，而是补上其上层内容：

> **Premium World Art + Premium Artifact Art**。

## 2. Current implementation facts audited

- `ArtifactRegistry` 已有 15 个 `ArtifactID`；
- `ArtifactCanonClass` 已区分 sealed / mystical / uniqueness / special；
- 15 件 Artifact 已有不同 gameplay component，而非空白卡片；
- `ArtifactComponentShell` 当前 identity panel 的大主体仍是 `Image(systemName:)`；
- Probability Die 已有 RealityKit 3D 表现，应保留；
- `ArtifactShowcaseView` 当前是 horizontal selector + selected detail component；
- `Assets.xcassets` 已有纹理、少量人物/灵摆图与 `wom.icon.*`，但没有 15 件 Artifact 的 premium art family，也没有 6 个世界/场景 art family。

## 3. External research completed

### Canon / IP

- WebNovel official novel synopsis；
- 《诡秘之主 / 宿命之环》官方 IP 站；
- 2026 当前《诡秘之主》官方游戏 TapTap 页面；
- Artifact 物理外形由 secondary index 辅助定位，但正式出图必须回到原著/官方证据。

### Game / platform best practice

- Apple HIG — Designing for games / Typography / Accessibility；
- Microsoft Xbox Accessibility Guidelines — text / contrast / additional channels / focus / motion；
- GDC — AAA UI Art Direction；
- GDC — Front-End Key Art；
- GDC — shared UI engineering patterns。

完整记录：`../artwork/Research_Sources_Premium_Art_A0.md`。

## 4. Decisions

### D1 — Art direction

采用 5 pillars：

1. Mundane First；
2. Occult Intrusion；
3. Archive & Evidence；
4. Gray Fog Is Semantic；
5. Power Always Has Cost。

禁止把“诡秘”简化为全局黑紫、触手、金框和大面积 bloom。

### D2 — Five-layer architecture

1. Premium World Art；
2. Premium Artifact Art；
3. Atmospheric Assets；
4. Existing WOM Component System；
5. Visual QA Governance。

### D3 — Artifact is art-first, not loot-card-first

Artifact 继续复用现有 `ArtifactComponentShell`，但 identity panel 后续由 premium object artwork 作为主视觉；SF Symbol 保留 fallback / accessibility / missing-art role。

### D4 — Progressive disclosure

Artifact collection 不同时展示 15 张完整详情卡：

`thumbnail selector → identity showcase → full interaction`。

### D5 — RealityKit remains valid

Probability Die 的 RealityKit 交互继续作为主交互表现；2D premium artwork 只补 library / dossier / static states。

### D6 — Artwork and UI are separate layers

Artwork 不包含：名称、risk、stats、button、fake UI text、macOS chrome。所有交互和文字仍由 SwiftUI 绘制。

### D7 — Visual QA remains retroactive

Premium Art 不获得“美术豁免”：现有 contrast / typography / source / layout contracts 继续强制执行。

## 5. First production scope

### A1 — World/Scene 6 pieces

1. World Hero
2. Gray Fog / Sefirah Atmosphere
3. Ritual Altar
4. Codex / Archive
5. Fate / Worldline
6. Artifact Vault / Evidence Room

### A2 — Artifact P0 7 pieces

1. Arrodes
2. Alzuhod Quill
3. Trunsoest Brass Book
4. Magic Wishing Lamp
5. Creeping Hunger
6. Sea God Scepter
7. Probability Die

### A3 — P1 remaining 8

Leymano / Groselle / Azik Whistle / Cards of Blasphemy / Staff of Stars / Box of Great Old Ones / Death Knell / Unshadowed Crucifix。

## 6. Image production contract

- World master：4096×2560；runtime：2560×1600；header：2400×900 when needed；
- Artifact object master：2048×2048；detail 1024×1024；thumbnail 512×512；
- 声明 Focus Zone / Quiet Zone / Crop Reserve；
- 96×96 silhouette 仍应可识别；
- selector 不直接解码 master；
- 不复制官方/游戏/漫画/商业资产；
- AI-assisted art 必须 human QA + provenance。

## 7. Persisted artifacts in A0

- `docs/05_UI/Premium_World_Art_Artifact_Implementation_Plan_v1.0.md`
- `docs/05_UI/artwork/Canon_Visual_Brief_Template.md`
- `docs/05_UI/artwork/Research_Sources_Premium_Art_A0.md`
- `docs/05_UI/visual-assets/Batch_28_Premium_Art_Program_Plan.md`
- `.agents/capsules/MAC-PREMIUM-ART-PLAN.json`
- `docs/05_UI/visual-assets/README.md` update

## 8. Explicit non-deliverables in A0

A0 **没有**：

- 生成运行时 artwork；
- 修改 `Assets.xcassets`；
- 修改 SwiftUI production code；
- 修改 Engine / IPC / Domain；
- 把 placeholder 页面伪装成完成。

因此本 Batch 的成功定义是“实施方案被完整落盘并通过门禁”，不是“已经有图片”。

## 9. Next entry point

A0 合并后立即进入 **A1 实际图片生产**：

1. 先完成 W1/W2 两张方向校准图；
2. 做人工 Art QA / UI-safe crop QA；
3. 方向通过后补 W3–W6；
4. 同一长期 PR 内建立 `WOMWorldArtworkAsset` / `WOMArtworkView` / scrim / Asset Catalog contract；
5. 然后进入 A2 Artifact P0 7 件。

下一阶段禁止继续用“补更多组件 primitive”替代实际绘图。
