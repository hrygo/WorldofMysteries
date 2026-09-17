# Visual Asset System — Living Plan / 当前执行事实源

> 稳定设计基线：[`../Visual_Asset_System_v1.0.md`](../Visual_Asset_System_v1.0.md)  
> Visual QA：[`Visual_QA_Contract_v1.0.md`](Visual_QA_Contract_v1.0.md)  
> Source Guards：[`Visual_QA_Source_Guards_v1.0.md`](Visual_QA_Source_Guards_v1.0.md)

## 1. 持久化与交付规则

- 关键设计判断必须落仓库，不依赖聊天或临时环境。
- 同一阶段采用 **长期持久化 PR + 原子 commit**；PR 不要求最小化。
- 涉及方案时同步提交：Living Plan + Batch + Capsule + 实际代码/测试。
- 稳定增量尽早推远端；最终 head 统一执行 `MACOS_APP_P0`。
- 不绕过主分支保护；写入成功不等于交付完成。
- **最终 head 的完整 required gates 全部通过后，允许按当前项目授权自行合并；合并时必须使用 expected head SHA，并在合并后回读 `main` 与 open PR 状态。**
- Visual QA Contract 对历史和未来视觉代码都生效，已合并不是豁免理由。

## 2. 技术与 Visual QA 硬性边界

- 世界观图形：原创 vector asset + typed registry。
- 平台行为/状态：SF Symbols + typed semantic registry。
- Sheet / Popover / Inspector / segmented selection / WindowGroup 优先系统 SwiftUI/macOS 语义；WOM 不伪造系统控件/窗口。
- readable text contrast >= **4.5:1**；关键 non-text affordance >= **3:1**；长正文/重点说明批准组合优先 >= **7:1**。
- body 默认 >= **13pt**；metadata 默认 >= **11pt**；10pt 仅短数字/快捷键/极短标签；9pt 以下不承载关键语义。
- 最小窗口 **960×640** 无结构性重叠；舒适默认窗口 **1180×760**，但不锁定用户 resize。
- Inspector width contract：**280 / 320 / 420pt**（min / ideal / max）。
- 长中英文、Badge、Loading、Error、Empty 必须自然增长或 responsive fallback。
- 优先 adaptive Grid / `ViewThatFits`；不得通过缩小字体、负 padding、魔法宽度或抬高最小窗口掩盖空间问题。
- 同组卡片、按钮、标题基线、padding、视觉重量保持工整一致。
- Reduce Motion / Increased Contrast / Differentiate Without Color / Reduce Transparency / Keyboard Focus 必须稳定退化。

## 3. 当前视觉系统交付状态：COMPLETE

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
| Closure | current | Living Plan / merge policy / terminal delivery record | IN FINAL GATE |

> PR #30 是在 `main` 前进后主动关闭的过渡 Backfill PR；其有效工作已从最新主线重新建立并进入 #31，不属于遗留交付。

当前视觉系统不存在待实现的已承诺 Wave。Closure 合并后，本轮视觉系统工程交付视为结束。

## 4. 已形成的系统能力

### Assets / semantic registry

- World / Ritual / Codex / Artifact / Character / Clue / Inventory / Settings 等自有语义图标；
- 平台行为与状态通过 typed SF Symbols registry；
- Texture registry 复用现有高质量纹理，不复制大型资源；
- Asset Catalog、registry、SVG metadata 具备自动契约。

### Component primitives

- `WOMIcon`
- `WOMButtonStyle` / icon / toolbar variants
- `WOMPanelBackground` / `WOMCardSurface` / `WOMFloatingSurface`
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
- 15/15 Artifact individual QA completed；
- Source Guard scans production visual Swift and reports file + line；
- approved contrast combinations are calculated with WCAG relative luminance；
- shared typography token floors prevent global readability regression；
- Swift 6 / Xcode App Target continue to be required final gates。

## 5. Merge / verification policy

For visual-system work in this project:

1. pin current `main` SHA；
2. persist Capsule + plan/batch + implementation/tests early；
3. preserve atomic commits；
4. stacked work must reconcile to actual `main` before final validation；
5. final Files changed must contain only the intended wave increment；
6. required final checks:
   - PR Task Capsule & Evidence Audit；
   - PR Gate Reporter & Sticky Comment；
   - Architecture Fitness & Contracts；
   - Python Engine & Contracts；
   - Swift 6 Test Suite；
   - Xcode App Target build；
   - `All Quality Gates Passed`；
7. **all final gates success → may merge automatically using the verified expected head SHA**；
8. after merge, read back `main`, merged PR state and remaining open PRs。

A failed guard is repaired by changing the implementation or approved contract deliberately; it must not be weakened merely to obtain green CI.

## 6. 生产入口事实 / 当前产品边界

- Sidebar / Fate / Content Shell：真实生产入口。
- Ritual：已有真实组件，无独立一级路由。
- Artifact：作为 Fate 命运干预工具，不额外制造背包一级导航。
- Character / Story Book / Cards / Worldline / Notes：若真实领域数据链尚未就绪，继续保持 placeholder；**这属于产品/领域数据工作，不是本轮视觉系统遗留。**
- Component Gallery / Native Inspector Preview：Showcase / Visual Regression / QA surface，不代表业务页面完成。
- 不为“看起来更像专业 App”提前制造没有领域语义的独立窗口。

## 7. 后续仅在新前置条件成立时启动的新工作

以下项目不属于当前未完成工作；只有相应领域能力成熟后才开启新 Task Capsule / PR：

- production Inspector binding（真实领域 selection/state source 就绪后）；
- placeholder workspace 接入真实数据后的 NavigationSplitView / Inspector contract；
- Character / Codex / Story Book standalone window（具备独立工作流与 state restoration 后）；
- window restore / zoom / multi-window policy（确有产品需求后）。

## 8. 恢复入口

`Visual_Asset_System_v1.0.md` → 本文件 → `Visual_QA_Contract_v1.0.md` → `Visual_QA_Source_Guards_v1.0.md` → Batch 22–26 → Wave B–H Capsules → Component Gallery / Native Inspector Preview → Visual QA / Contrast / Typography contract tests。

本文件为当前执行事实源；历史 Batch 保留决策过程与每阶段证据。
