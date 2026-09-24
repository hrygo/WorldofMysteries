# Artifact Vault v1.1 2.5D 展陈实现计划

> 目标：将已批准的 Artifact Vault v1.1 方案落地为可运行的 macOS SwiftUI 展览界面。  
> 基线：macOS 26+ / Swift 6 / Apple Silicon / 现有 `ArtifactRegistry` 与 15 个 production components。  
> 范围：P0 布局与 presentation context、P1 Shadow-box Object Stage、P2 轻量本机 2.5D 视差与降级契约。  
> 不在本次范围：重建 15 件 artwork、将所有 Artifact 转成 RealityKit 模型、任何 Domain/SQLite/IPC 协议变更。

## 实现原则

- `ArtifactRegistry` 继续是 15 件 Artifact 的唯一事实源；presentation profile 只通过 `ArtifactID` 关联展示策略。
- 原始方图只能等比显示，长方形 Stage 由背板、挂载框、接触阴影、铭牌和高光填充。
- 2.5D 只服务当前 selected Artifact；Shelf 不创建 RealityKit、Metal renderer 或深度纹理。
- `standard` 行为保持不变；`vaultExhibit` 通过 SwiftUI environment 传递给现有 `ArtifactComponentShell`，不复制 15 个 Gameplay View。
- 缺少遮罩、深度或图片资源时，必须回退到静态方形挂载框，不能出现空白展台或阻塞 Workbench。

## 任务 1：建立 presentation-only profile 与环境值

文件：

- 新增 `macos-app/WorldOfMysteries/Artifacts/ArtifactPresentationProfile.swift`
- 测试更新 `macos-app/WorldOfMysteriesTests/ArtifactVaultExhibitionContractTests.swift`
- 测试更新 `macos-app/WorldOfMysteriesTests/ArtifactComponentTests.swift`（只在需要共享 profile 完整性断言时更新）

实现：

1. 定义 `ArtifactPresentationContext`：`.standard`、`.vaultExhibit`。
2. 定义 `ArtifactExhibitionArchetype`：`.fateInstrument`、`.oracleAndArchive`、`.spatialRelic`、`.authorityAndCombat`、`.ruleAndPurification`。
3. 定义 `ArtifactMountStyle`：`.framedSquare`、`.plinthSquare`、`.bookCradle`、`.suspendedSquare`、`.ritualTray`。
4. 定义 `ArtifactPresentationAssetCapabilities`，仅描述 `subjectMask`、`coarseDepth`、`contactShadow`、`rimLight` 是否可用，不保存 Canon 或文案字段。
5. 定义 `ArtifactPresentationProfile`，字段只包含 `artifactID`、archetype、mount、stageAnchor、artwork variant、capabilities、environment token 和 presentation-only related IDs。
6. 定义 `ArtifactPresentationProfiles.profile(for:)` 与 `all`，逐一覆盖 `ArtifactRegistry.all` 的 15 个 ID；缺少 profile 时返回稳定的 `.framedSquare` fallback。
7. 增加 `EnvironmentKey`，使 `ArtifactComponentShell` 能读取 `ArtifactPresentationContext`，默认值必须是 `.standard`。
8. 为 `ArtifactID` 提供 profile 访问入口，但不在 profile 中复制 `displayName`、`subtitle`、`shortGameplay` 或 `canonClass`。

验收：

- 15 个 Registry ID 均有 profile；
- `ArtifactPresentationContext` 默认不改变现有 production component；
- profile 只包含 presentation 字段；
- related IDs 只能引用现有 Registry ID。

## 任务 2：实现 Object Stage 与等比方图挂载

文件：

- 新增 `macos-app/WorldOfMysteries/Artifacts/ArtifactObjectStage.swift`
- 可复用 `macos-app/WorldOfMysteries/DesignSystem/WOMArtworkView.swift`、`WOMSurfaceStyles.swift` 与现有 `DesignTokens`

实现：

1. 创建 `ArtifactObjectStage`，输入 `ArtifactDescriptor`、`ArtifactPresentationProfile` 和当前 selection revision。
2. Stage 外框固定为 `16:10`，使用现有 `WOMWorldArtworkAsset.artifactVault.runtimeAssetName` 作为低对比环境背板，并提供纯色/纹理 fallback。
3. 在 Stage 中央计算方形 mount，artwork 使用 `WOMArtworkView` 的 `contentMode: .fit`，明确设置相等的宽高，禁止 `.fill` 和非等比缩放。
4. 根据 `ArtifactMountStyle` 绘制不同的台座/挂载框：镜、牌和十字架使用 framed；骰子、灯、权杖使用 plinth；书类使用 book cradle；空间类使用 suspended；净化/规则类使用 ritual tray。
5. 增加环境背板、mount 边框、接触阴影、低强度 rim highlight、底部 plaque 五层结构；所有装饰层 `accessibilityHidden(true)`。
6. 使用 `onContinuousHover` 提供 `4–8pt` 以内的低幅视差：只移动 mount 内部的 artwork/highlight，不移动 Stage 边界或操作控件。
7. `accessibilityReduceMotion` 开启时关闭视差与装饰动画，保留静态 mount、selected 状态和文本 label。
8. 资源缺失时仍渲染 mount、系统图标 fallback 和铭牌；不让主展台变成空白区域。
9. 提供纯函数或静态 helper 计算 Stage frame、mount side 和 parallax offset，供单元测试验证无负尺寸、无越界和 1:1。

验收：

- `960×640`、`1180×760`、`1440×900` 下 Stage 保持 16:10 且不溢出；
- 15 个 Artifact 的 artwork 均等比显示；
- Reduce Motion 下没有 pointer parallax；
- 所有装饰层不改变 VoiceOver 顺序；
- detail artwork 缺失时能回退到 icon/挂载框。

## 任务 3：重排 Artifact Vault 主布局与浏览状态

文件：

- 修改 `macos-app/WorldOfMysteries/Artifacts/ArtifactShowcaseView.swift`

实现：

1. 保留现有 Header、搜索、Family filter、横向 Shelf、Dossier、15 个 `selectedComponent` 分支和 Preview resolver。
2. 在非空馆藏状态中加入 `ArtifactObjectStage`。
3. 使用 `ViewThatFits(in: .horizontal)`：
   - Wide：Shelf 约 `280–340pt`，右侧为 Object Stage + Dossier；
   - Compact/Minimum：Shelf 全宽横向滚动，Object Stage、Dossier、Workbench 纵向排列。
4. 保持 Vault 只有 Shelf 的横向 ScrollView；不额外包裹一个纵向 ScrollView。
5. 将当前 selection 的 profile 传给 Stage，并将 `.environment(\.artifactPresentationContext, .vaultExhibit)` 设置在 `selectedComponent` 的外层。
6. 选择、Prev、Next、筛选变化和 Reset 都推进同一 `showcaseRevision`，确保 Stage transition 与 Workbench Preview 同步。
7. 选择展品时取消/清理上一件的局部展陈状态；不写 Domain、不写 DB、不改变 ArtifactRegistry。
8. 为 Shelf 增加 focusable/辅助提示与左右方向键浏览；SearchField 聚焦时不抢占方向键。
9. 增加 Stage、Dossier 和 Workbench 的清晰 accessibility labels，保证当前展品是单一主要焦点。

验收：

- 原有 Artifact Vault contract tests 与 15 个 production component checks 继续通过；
- Wide/Compact 布局都保留搜索、选择、Prev、Next、Reset 和正式 Workbench；
- selecting Artifact 不会出现 identity panel 与 Stage 的双份主 artwork；
- Filter 后 selection 自动校正且同步重置 Preview。

## 任务 4：让 production component 支持 vaultExhibit 而不复制 View

文件：

- 修改 `macos-app/WorldOfMysteries/Artifacts/ArtifactUIPrimitivesCore.swift`

实现：

1. 在 `ArtifactComponentShell` 读取 `@Environment(\.artifactPresentationContext)`。
2. `standard` 保持现有 `identityPanel + detailPanel` 两栏/堆叠布局和最小高度。
3. `vaultExhibit` 只渲染 `detailPanel`，移除重复的 identity artwork、名称和长文案，让 Object Stage 承担对象身份、Workbench 承担正式操作。
4. `vaultExhibit` 仍保留 detail panel 的内部真实控件、resolver feedback、Preview 结果和现有 ScrollView；不改变任何 model 或 resolver。
5. 保持 `ArtifactComponentShell` 的默认 initializer 调用兼容现有 15 个 production View。

验收：

- 非 Vault 页面截图/契约保持原样；
- Vault 中不再渲染完整 identity panel；
- Probability Die 的 RealityKit 仍在 detail panel 中运行；
- 不新增 Domain/DB/IPC 依赖。

## 任务 5：契约与纯布局测试

文件：

- 修改 `macos-app/WorldOfMysteriesTests/ArtifactVaultExhibitionContractTests.swift`
- 新增 `macos-app/WorldOfMysteriesTests/ArtifactPresentationProfileTests.swift`

测试内容：

1. 源码契约：检查 `ArtifactShowcaseView` 包含 `ArtifactObjectStage`、`vaultExhibit` environment、`ViewThatFits`、横向 Shelf 和 15 个 production View。
2. 源码契约：检查 `ArtifactComponentShell` 包含 `ArtifactPresentationContext`，并在 vaultExhibit 下不走 identity panel。
3. profile 完整性：Registry 15/15、related IDs 合法、fallback 合法。
4. 几何计算：Stage 16:10、mount 宽高相等、mount 不越界、视差受 `4–8pt` 预算约束。
5. accessibility contract：Reduce Motion 分支、Stage label、装饰层 hidden、selected 不仅依赖颜色。
6. reset contract：selection revision、`resetShowcase()` 和 component preview reset 仍存在。

## 任务 6：验证、构建与交付

执行：

1. `swift test`（`macos-app`）验证单元与契约。
2. `swift build -c release` 或项目既有 Release gate 验证 Swift 6 编译。
3. 运行项目规定的最小 P0 gate；若触发完整 App 构建，再记录实际 gate 输出和环境。
4. 在真实 macOS 窗口检查 `960×640`、`1180×760`、`1440×900`，覆盖概率之骰、阿罗德斯和书类 Artifact。
5. 检查 Reduce Motion、VoiceOver label、Increase Contrast、资源 fallback 和当前重型 Stage 唯一性。
6. 运行 `git diff --check` 与目标测试，确认只提交实现文件和测试，不触碰 `.agents/receipts/` 现有未跟踪内容。

## 完成定义

- 方图没有被拉伸或裁成横图；
- 长方形 Stage 具有背板、挂载、阴影、铭牌和低幅 2.5D 层次；
- 15 个 production components 仍可操作，Probability Die 仍使用 RealityKit；
- Vault 不再显示重复 identity panel；
- standard 行为无回归；
- 资源缺失、Reduce Motion 和窄窗口都能安全降级；
- 测试和 Release 构建通过，并报告实际验证结果。
