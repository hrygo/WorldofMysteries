# Scene artwork in-game integration — 2026-09-19

## What this record covers

已交付的 **6 张世界 / 场景美术（W1–W6）** 与 **15 件神器美术** 此前只出现在运行时校验窗口与组件画廊里。
本记录登记它们进入**真实导航场景**的绑定关系：哪个场景用哪张已批准的图、由哪个视图消费、
以及哪些结论仍然没有证据。

本轮只做表现层接入，没有重新生成或修改任何一张图：Asset Catalog 里的 42 个运行期载荷
（21 × 2 派生图）保持不变。

## Scene bindings (W1–W6)

绑定唯一事实源：`macos-app/WorldOfMysteries/DesignSystem/WOMSceneArtworkRegistry.swift`。
页头呈现组件：`macos-app/WorldOfMysteries/Components/WOMSceneHeroHeader.swift`。

| 场景 | 导航入口 | 已批准资产 | 变体 | 消费点 |
| --- | --- | --- | --- | --- |
| 世界观察 | `.world` | `wom.art.world.hero` (W1) | wide | `ContentView.sceneHeroHeader` |
| 命运干预 | `.fate` | `wom.art.world.gray-fog` (W2) | wide | `ArtifactFateInterventionView.header`（既有） |
| 特殊物品档案库 | 命运页底部区块 | `wom.art.scene.artifact-vault` (W6) | wide | `ArtifactFateInterventionView.artifactLibrarySection` |
| 人物档案 | `.character` | `wom.art.scene.codex-archive` (W4) | wide | `ContentView.sceneHeroHeader` |
| 私人历史 | `.storyBook` | `wom.art.scene.codex-archive` (W4) | wide | `ContentView.sceneHeroHeader` |
| 世界线 | `.worldline` | `wom.art.scene.fate-worldline` (W5) | wide | `ContentView.sceneHeroHeader` |
| 调查笔记 | `.notes` | `wom.art.scene.ritual-altar` (W3) | wide | `ContentView.sceneHeroHeader` |

两条刻意的留白：

- `.cards`（卡牌收藏）与 `.settings`（系统设置）**不挂场景页头**：W1–W6 里没有与「途径卡牌」或
  「四库 HUD」语义相符的已批准资产，宁可留白，也不给它们套一张语义不符的图。
- W4 同时服务 `人物档案` 与 `私人历史`，这是生产方案 §9 明确允许的用法
  （W4 用于 Character Codex / dossier / Narrative Chronicle）。

## Artifact coverage (15/15)

| 消费面 | 载荷 | 覆盖 |
| --- | --- | --- |
| 命运页特殊物品档案库（只读登记网格） | `thumbnail` | 15/15（遍历 `ArtifactRegistry.all`） |
| 神器玩法组件身份面板 | `detail` | 15/15（`ArtifactUIPrimitivesCore` 按 `ArtifactID` 解析） |
| 命运页快捷入口 | `thumbnail` | 5/15（当前局势下真正可用的干预工具） |
| 组件画廊 `ArtifactShowcaseView` | `thumbnail` + `detail` | 15/15 |

档案库是**只读登记视图**：它不伪造任何世界状态，也不替代玩法组件。15 件里只有少数是当前局势下的
命运干预工具，其余物品的玩法组件需要活动的 World / Story 上下文；缺上下文时打开玩法组件只会得到
伪造事实，因此不做成第二套背包。

## Evidence

| 项 | 结果 |
| --- | --- |
| 架构适应度 | `python3 scripts/check_architecture_fitness.py` → PASSED |
| Swift 6 契约测试 | `cd macos-app && swift test --scratch-path .build` → 249 tests / 36 suites passed |
| 新增契约 | `SceneArtworkIntegrationTests`（7 项：登记表覆盖 6/6、变体纪律、导航绑定诚实性、页头挂载、15 件档案库、详情/缩略图可达性、页头文本优先） |
| Xcode App Target | `xcodebuild ... -scheme WorldOfMysteries build` → BUILD SUCCEEDED |
| 真实窗口观察 | Debug 构建实机打开：世界页渲染 W1、调查笔记渲染 W3、世界线渲染 W5、命运页渲染 W6 档案库与 15 个缩略图 |

窗口观察只用于本轮接入判断，**没有**作为 G5 运行时证据提交：`docs/05_UI/artwork/qa/*.qa.json` 里
已记录的 G5 采集哈希仍对应改造前的采集面，本轮没有重跑采集，也没有把新的抓图入库。

## What this record does not claim

- **不是 G1 Canon 核对**：15 件神器里 12 件的 `G1_canon_atmosphere` 仍是 `PENDING_CANON_REVIEW`，
  与本轮表现层接入无关。
- **不是发布批准**：全部 21 个美术目标的 `shipping_approved` 仍然为 `false`。
- **不是新的运行时证据**：本轮没有产生可复算的抓图证据，因此不改变任何 G2/G5 记录。
- **不新增领域事实**：场景文案只描述场景承载什么，不声明世界观、拥有关系或改编结论。

## Verification commands

```sh
cd macos-app && swift test --scratch-path .build --filter SceneArtworkIntegration
python3 scripts/check_architecture_fitness.py
```
