# Visual Asset System — 执行层总体方案与总进度索引

> 总体设计基线：[`../Visual_Asset_System_v1.0.md`](../Visual_Asset_System_v1.0.md)  
> 本文件性质：**Living Plan / 执行层总体方案**  
> 本目录职责：记录每一批视觉资产/组件皮肤 PR 的当前路线、状态、依赖、已落盘资产与下一恢复入口。

## 0. 权威性约定

`Visual_Asset_System_v1.0.md` 保存长期视觉原则、技术路线、资产分类和目标架构，作为稳定的**设计基线**。

本文件保存持续演进的**执行总体方案**。当为了“小步 PR”而继续拆分、重排 Batch，导致本文件与设计基线中的早期批次编号或路线表出现差异时：

- 视觉原则、技术边界、Token 原则：以 `Visual_Asset_System_v1.0.md` 为准；
- 当前 Batch 编号、依赖、状态、下一步实施顺序：**以本文件为准**；
- 每个 Batch 的具体实现与验收：以对应 `Batch_xx_*.md` + Task Capsule + PR diff 为准。

因此，新环境恢复时不应仅根据 `Visual_Asset_System_v1.0.md` 的早期路线表推断当前进度。

## 1. 总分式交付规则

后续所有视觉系统 PR 必须同时具备：

1. **总**：本 Living Plan 必须更新，反映总体路线、批次状态和依赖关系；若长期视觉原则/技术边界发生变化，同时更新设计基线 `Visual_Asset_System_v1.0.md`。
2. **分**：新增或更新本批 `Batch_xx_*.md`，记录设计判断、实际文件、验证和下一批入口。
3. **实物**：资产批必须进入 `Assets.xcassets`；组件批必须进入对应 Swift 源码目录。
4. **Task Capsule**：显式绑定本批写入范围与权威 gate profile。
5. **PR 回读**：验证 base/head、changed files、diff 与 CI；关键结论不得只存在于聊天、临时目录或 PR 描述。

## 2. 当前批次链

| Batch | PR / 分支 | 内容 | 状态 | 依赖 |
|---|---|---|---|---|
| 01 | PR #22 / `feat/wom-visual-assets-01` | 总体设计基线 + World / Ritual / Codex / Artifact + `WOMIconAsset` 基线 | ALL QUALITY GATES PASSED | `main@730582d8` |
| 02 | PR #23 / `feat/wom-visual-assets-02` | Character / Clue / Inventory / Settings + Living Plan | STACKED; CI WAITS FOR RETARGET TO MAIN | Batch 01 |
| 03 | planned | Add / Remove / Edit / Search 的平台系统资产语义 | PLANNED | Batch 02 |
| 04 | planned | Close / Back / Favorite / More | PLANNED | Batch 03 |
| 05 | planned | Warning / Success / Locked / Active / Cooldown + Divination / Spirituality / Fate / Gray Fog / Seal / Card | PLANNED | Batch 04 |
| 06 | planned | Parchment / Gold / Veil / Slate / Velvet 纹理盘点与 Texture Registry | PLANNED | Batch 05 |
| 07 | planned | `WOMIcon`：统一自有 Asset 与系统图标 source、尺寸、渲染、Accessibility | PLANNED | Wave A assets |
| 08 | planned | `WOMButtonStyle` 基础状态 | PLANNED | Batch 07 |
| 09 | planned | Icon / Toolbar Button Styles | PLANNED | Batch 08 |
| 10 | planned | Panel / Card Surface + Texture Layer + Section Chrome | PLANNED | Token + textures |

### Stacked PR CI 约束

当前仓库的 PR CI 对 `main` 目标分支触发；以功能分支为 base 的 stacked PR 不会立即获得同一套 GitHub Actions 门禁。因此：

1. stacked PR 用于持久化和审查纯增量；
2. 上游合并后必须立即 retarget 到 `main`；
3. retarget 后重新核验 base SHA / Capsule，并等待完整 required checks；
4. 在此之前不得把 stacked PR 标记为“CI 已通过”。

## 3. 已落盘资产目录

### Batch 01

- `wom.icon.world`
- `wom.icon.ritual`
- `wom.icon.codex`
- `wom.icon.artifact`

实施记录：[`Batch_01_Core_Semantic_Icons.md`](Batch_01_Core_Semantic_Icons.md)

### Batch 02

- `wom.icon.character`
- `wom.icon.clue`
- `wom.icon.inventory`
- `wom.icon.settings`

实施记录：[`Batch_02_Navigation_Icons.md`](Batch_02_Navigation_Icons.md)

## 4. 恢复工作时的读取顺序

任何新环境或 Agent 接手时按以下顺序恢复：

1. `AGENTS.md`
2. `docs/05_UI/Visual_Asset_System_v1.0.md`（稳定设计基线）
3. 本文件 `docs/05_UI/visual-assets/README.md`（执行总体方案 / 当前权威路线）
4. 最新 Batch 文档
5. 对应 Task Capsule
6. 当前 PR diff / CI 状态

不得从聊天记忆直接猜测当前资产状态。

## 5. PR 粒度

- 导航图标、行为图标、状态/世界图标分开提交；
- 基础资产与真实页面迁移分开提交；
- 每批尽量 4–8 个同类语义资产；
- 一个 Batch 对应一个 Task Capsule 和一个 PR；
- 依赖未合并时允许 stacked PR，但必须记录依赖并在上游合并后 retarget + 复核基线。
