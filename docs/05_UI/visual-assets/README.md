# Visual Asset System — Living Plan / 当前执行事实源

> 稳定设计基线：[`../Visual_Asset_System_v1.0.md`](../Visual_Asset_System_v1.0.md)  
> Visual QA：[`Visual_QA_Contract_v1.0.md`](Visual_QA_Contract_v1.0.md)  
> Source Guards：[`Visual_QA_Source_Guards_v1.0.md`](Visual_QA_Source_Guards_v1.0.md)  
> Premium Art Program：[`../Premium_World_Art_Artifact_Implementation_Plan_v1.0.md`](../Premium_World_Art_Artifact_Implementation_Plan_v1.0.md)

## 1. 持久化与交付规则

- 关键设计判断必须落仓库，不依赖聊天或临时环境。
- 同一阶段采用 **长期持久化 PR + 原子 commit**；PR 不要求最小化。
- 涉及方案时同步提交：Living Plan + Batch + Capsule + 实际代码/测试/资产。
- 稳定增量尽早推远端；最终 head 统一执行 `MACOS_APP_P0`。
- 不绕过主分支保护；写入成功不等于交付完成。
- **最终 head 的完整 required gates 全部通过后，允许按当前项目授权自行合并；合并时必须使用 expected head SHA，并在合并后回读 `main` 与 open PR 状态。**
- Visual QA Contract 对历史和未来视觉代码与 artwork 集成都生效，已合并不是豁免理由。

## 2. 技术与 Visual QA 硬性边界

- 世界观图形：原创 vector asset + typed registry。
- 平台行为/状态：SF Symbols + typed semantic registry。
- Premium World / Artifact Art：原创高品质 raster artwork + typed artwork registry + provenance；不得复制官方动画/游戏/漫画商业资产。
- Sheet / Popover / Inspector / segmented selection / WindowGroup 优先系统 SwiftUI/macOS 语义；WOM 不伪造系统控件/窗口。
- readable text contrast >= **4.5:1**；关键 non-text affordance >= **3:1**；长正文/重点说明批准组合优先 >= **7:1**。
- body 默认 >= **13pt**；metadata 默认 >= **11pt**；10pt 仅短数字/快捷键/极短标签；9pt 以下不承载关键语义。
- 最小窗口 **960×640** 无结构性重叠；舒适默认窗口 **1180×760**，但不锁定用户 resize。
- Inspector width contract：**280 / 320 / 420pt**（min / ideal / max）。
- 长中英文、Badge、Loading、Error、Empty 必须自然增长或 responsive fallback。
- 优先 adaptive Grid / `ViewThatFits`；不得通过缩小字体、负 padding、魔法宽度或抬高最小窗口掩盖空间问题。
- 同组卡片、按钮、标题基线、padding、视觉重量保持工整一致。
- Reduce Motion / Increased Contrast / Differentiate Without Color / Reduce Transparency / Keyboard Focus 必须稳定退化。
- 高品质图片不是 QA 豁免项：文字区必须有可验证的 quiet zone / scrim / Surface，不能把白字直接压在不可控复杂背景上。

## 3. 已完成：Visual System Engineering Foundation

| 阶段 | PR | 内容 | 状态 |
|---|---|---|---|
| Foundation | #21–#25 | Core/navigation icons、ornament、texture、platform semantics | DONE |
| Wave B | #26 | Icon/Button/Surface、Gallery、Sidebar、Ritual、Codex、Artifact/Fate、Shell | DONE |
| Wave C | #27 | Focus / Contrast / Accessibility states | DONE |
| Wave D | #28 | Asset contracts、typed icon、navigation/commands/focus | DONE |
| Wave E | #29 | Overlay / Feedback / Loading / Status / typed Empty State | DONE |
| Visual QA Backfill | #31 | Wave A–E retroactive contrast / typography / collision / alignment / 15-of-15 Artifact QA | DONE |
| Wave F | #32 | Native segmented fallback、Relation、Achievement、Cooldown、advanced interaction contracts | DONE |
| Wave G | #33 | Window metrics、native Inspector、responsive workspace layout | DONE |
| Wave H | #34 | Source Guard、WCAG Contrast Guard、Typography Token Guard | DONE |
| Closure | #35 | Living Plan、merge policy、terminal delivery record | DONE |

> PR #30 是在 `main` 前进后主动关闭的过渡 Backfill PR；其有效工作已从最新主线重新建立并进入 #31，不属于遗留交付。

**Visual System 工程底座已经完成。Premium Art Program 是新的视觉内容生产计划，不把旧 Wave 重新打开。**

## 4. 已形成的系统能力

### Assets / semantic registry

- World / Ritual / Codex / Artifact / Character / Clue / Inventory / Settings 等自有语义图标；
- 平台行为与状态通过 typed SF Symbols registry；
- Texture registry 复用现有高质量纹理，不复制大型资源；
- Asset Catalog、registry、SVG metadata 具备自动契约。

### Component primitives

- `WOMIcon`
- `WOMButtonStyle` / icon / toolbar variants
- `WOMPanelBackground` / `WOMCardChrome` / `WOMFloatingSurface`
- `WOMTextureLayer`
- Overlay / Loading / Status / Empty State
- `WOMAdaptiveSegmentedPicker`
- `WOMRelationBadge`
- `WOMAchievementSeal`
- `WOMCooldownIndicator`
- `WOMAdaptivePair`
- `WOMInspectorContent`

### Production integration

- App Sidebar
- Content Shell
- Fate / Artifact intervention
- Ritual components
- Codex / Archive components
- Component Gallery / Visual QA Stress
- App commands / Advice focus chain
- Window default/minimum metrics

### Visual QA governance

- historical Wave A–E backfill completed；
- 15/15 Artifact individual UI QA completed；
- Source Guard scans production visual Swift and reports file + line；
- approved contrast combinations are calculated with WCAG relative luminance；
- shared typography token floors prevent global readability regression；
- Swift 6 / Xcode App Target remain required final gates。

## 5. 当前新工作流：Premium Art Program

### A0 — Research / Art Bible / Implementation Plan — DONE

PR：**#37**  
Merged commit：`d98af5f4eec413407a6c83de245ebc434fcd267d`  
Task：`MAC-PREMIUM-ART-PLAN`  
Batch：[`Batch_28_Premium_Art_Program_Plan.md`](Batch_28_Premium_Art_Program_Plan.md)  
总体方案：[`../Premium_World_Art_Artifact_Implementation_Plan_v1.0.md`](../Premium_World_Art_Artifact_Implementation_Plan_v1.0.md)  
状态：**A0 DONE / ALL QUALITY GATES PASSED / A1 READY**。

A0 已完成：

- 审计当前 15 件 Artifact 实现和 Asset Catalog；
- 调研《诡秘之主》官方小说简介、官方 IP 站、2026 当前官方游戏公开表达；
- 调研 Apple HIG、Microsoft XAG、GDC AAA UI / Key Art / UI Architecture 实践；
- 建立 5 个 Art Direction Pillars；
- 定义 6 张首批 World / Scene Art；
- 定义 Artifact P0 7 件 + P1 8 件；
- 定义 4096×2560 scene master 与 2048×2048 artifact object master；
- 定义 focus / quiet / crop zones、provenance 和 artwork QA；
- 建立 [`../artwork/Canon_Visual_Brief_Template.md`](../artwork/Canon_Visual_Brief_Template.md)；
- 建立 [`../artwork/Research_Sources_Premium_Art_A0.md`](../artwork/Research_Sources_Premium_Art_A0.md)。

A0 没有生成运行时 premium image、没有修改 `Assets.xcassets`、没有修改 SwiftUI production code，也没有把现有 SF Symbol fallback 冒充成最终 Artifact 美术。

### A1 — World / Scene Premium Art — NEXT

下一阶段固定为真正的图片生产：

1. W1 World Hero；
2. W2 Gray Fog / Sefirah；
3. 人工 Art QA + UI-safe crop / quiet-zone QA；
4. W3 Ritual / W4 Codex / W5 Fate / W6 Artifact Vault；
5. 同阶段建立 `WOMWorldArtworkAsset` / `WOMArtworkView` / `WOMArtworkScrim`；
6. 随后 A2 开始 Artifact P0 7 件 premium object art。

**A1 不得继续用“补更多 UI primitive”替代真正绘图。**

## 6. Premium Artifact 关键事实

当前 `ArtifactRegistry` 已有 15 件物品和明确 gameplay component；Premium Art 不是重新设计玩法。

后续 `ArtifactComponentShell.identityPanel` 由：

```text
SF Symbol primary identity
```

升级为：

```text
Premium object artwork primary identity
    + existing typed SF Symbol fallback
    + existing metadata / status / interaction
```

Probability Die 的 RealityKit 3D 交互继续保留；premium 2D art 只补浏览、dossier 与静态状态。

Artifact collection 继续 progressive disclosure，不把 15 个完整详情卡同时堆在一屏。

## 7. Merge / verification policy

For visual-system / premium-art work in this project:

1. pin current `main` SHA；
2. persist Capsule + plan/batch + implementation/assets/tests early；
3. preserve atomic commits；
4. stacked work must reconcile to actual `main` before final validation；
5. final Files changed must contain only intended increment；
6. required final checks:
   - PR Task Capsule & Evidence Audit；
   - PR Gate Reporter & Sticky Comment；
   - Architecture Fitness & Contracts；
   - Python Engine & Contracts；
   - Swift 6 Test Suite；
   - Xcode App Target build；
   - `All Quality Gates Passed`；
7. **all final gates success → may merge automatically using verified expected head SHA**；
8. after merge, read back `main`, merged PR state and remaining open PRs。

Failed guard 必须修实现或显式修改批准契约；不得单纯为了绿灯降低视觉标准。

## 8. 生产入口事实 / 产品边界

- Sidebar / Fate / Content Shell：真实生产入口。
- Ritual：已有真实组件，无独立一级路由。
- Artifact：作为 Fate 命运干预工具，不额外制造背包一级导航。
- Character / Story Book / Cards / Worldline / Notes：若真实领域数据链尚未就绪，继续保持 placeholder；不能用高品质图掩盖功能未完成状态。
- Component Gallery / Native Inspector Preview：Showcase / Visual Regression / QA surface，不代表业务页面完成。
- 不为“看起来像游戏”提前制造没有领域语义的独立窗口或伪 gameplay。

## 9. 恢复入口

### Visual System engineering

`Visual_Asset_System_v1.0.md` → 本文件 → `Visual_QA_Contract_v1.0.md` → `Visual_QA_Source_Guards_v1.0.md` → Batch 22–27 → Wave B–H Capsules → QA tests。

### Premium Art Program

`Premium_World_Art_Artifact_Implementation_Plan_v1.0.md` → 本文件 → Batch 28 → `MAC-PREMIUM-ART-PLAN` Capsule → Canon Visual Brief Template → Research Sources → PR #37 → A1 actual artwork production。

本文件为当前执行事实源；历史 Batch 保留决策过程与每阶段证据。
