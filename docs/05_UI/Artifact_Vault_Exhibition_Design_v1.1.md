# Artifact Vault Exhibition Design v1.1

> 状态：PROPOSED DESIGN REVISION  
> 适用范围：macOS Component Gallery / Artifact Vault / 15 件 Canon Artifact Gameplay Components  
> 目标平台：macOS 26+ / SwiftUI / Apple Silicon  
> 修订日期：2026-09-19  
> 上一版基线：[Artifact Vault Exhibition Design v1.0](Artifact_Vault_Exhibition_Design_v1.0.md)  
> 修订主题：Shadow-box 2.5D Exhibition / 长方形展台 / 方形原图实物化

---

## 1. 结论先行

v1.1 不改变 Artifact Vault 的产品定位，也不重造 15 件 Artifact 的 Gameplay View。它将 v1.0 的“馆藏浏览 + 当前展品 + LIVE Workbench”升级为一套更明确的展陈模型：

> **用户看到的不是被拉伸的一张方图，而是放置在真实展台里的一个可操作物件。**

本次修订解决五个具体问题：

1. 页面从“纵向组件串联”升级为“展览主舞台优先”的整体布局；
2. 所有 Artifact artwork 保持原始方形比例，不再强行填充长方形背板；
3. 长方形空间由环境、底座、背板、阴影、铭牌和局部光照共同填充；
4. 通过本机离线图像处理生成遮罩、粗深度、接触阴影和高光，使展品拥有可控的 2.5D 层次；
5. 将展陈数据限制在 presentation layer，避免复制 Canon 事实、污染 Domain 或让 15 个 Gameplay View 分叉。

v1.1 的核心视觉结构：

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Artifact Vault                         搜索神器   Family   15 件馆藏          │
├───────────────────────┬──────────────────────────────────────────────────────┤
│ Collection Shelf      │ Object Stage / 当前展品                              │
│ 横向浏览、轻量缩略图  │ ┌──────────────────────────────────────────────────┐ │
│                       │ │ 环境背板 / 纹理 / 光晕                           │ │
│ [01] [02] [03] ...    │ │       ┌──────────────┐                            │ │
│                       │ │       │  方形物件挂载 │  ← artwork 1:1              │ │
│                       │ │       └──────────────┘                            │ │
│                       │ │  底座 · 接触阴影 · 铭牌 · 2.5D 微差位移              │ │
│                       │ └──────────────────────────────────────────────────┘ │
│                       │ 展品档案 / 上一件 / 下一件 / Reset                    │
├───────────────────────┴──────────────────────────────────────────────────────┤
│ LIVE ARTIFACT WORKBENCH：当前 Artifact 的正式 production component          │
└──────────────────────────────────────────────────────────────────────────────┘
```

大窗口中，Collection Shelf 与 Object Stage 并列；窄窗口中，Shelf 仍保持横向浏览，Object Stage、Dossier 和 Workbench 顺序下移。布局变化不得改变展品选择、Preview Reset 或 Gameplay 语义。

---

## 2. 本次修订的边界

### 2.1 目标

- 将当前展品提升为单一视觉焦点；
- 把正方形 artwork 作为“物件本体”，而不是被拉伸的背景素材；
- 用稳定的 Shadow-box 结构给长方形容器提供比例、重量和材质关系；
- 让 2.5D 效果在本机完成预处理与运行时合成；
- 在没有遮罩、深度或高质量资产时仍能优雅降级；
- 让同一份 production Gameplay View 同时服务 standard 和 vaultExhibit 两种表达环境；
- 为 15 件 Artifact 建立可校验、可扩展、无 Canon 重复的 presentation contract。

### 2.2 明确不做

- 不将 Artifact Vault 改造成装备背包、商城或稀有度墙；
- 不把方图裁成横图来追求“填满”；
- 不把所有 15 件 Artifact 同时转换成 3D 或 RealityKit 场景；
- 不在运行时依赖云端抠图、云端生成或远端图片服务；
- 不凭 artwork 推断 Canon 属性、危险等级或世界事实；
- 不让 2.5D 预览直接写入 `world.db` 或触发 authoritative commit；
- 不为每件 Artifact 复制一套 Gameplay View；
- 不以持续粒子、自动轮播或大幅漂移换取“沉浸感”。

---

## 3. 与 v1.0 的差异

| 领域 | v1.0 基线 | v1.1 修订 |
|---|---|---|
| 页面焦点 | Dossier 与 Workbench 串联 | Object Stage 成为当前展品的视觉锚点 |
| 主展台 | 由现有组件内部自行表达 | 增加统一的 `Object Stage` 展陈层 |
| 原图比例 | detail artwork 由组件自行决定 | artwork 永远保持 1:1，禁止非等比缩放 |
| 长方形空间 | 主要由组件背景填充 | 环境背板 + 挂载框 + 底座 + 阴影 + 铭牌 |
| 实物感 | 主要依赖卡片材质与 artwork | 结构化 2.5D 五层合成 |
| 资产处理 | runtime variant 为主 | 离线生成 presentation asset，运行时只做轻量合成 |
| 组件关系 | vaultExhibit 方向已提出 | 明确 stage、identity、detail 的责任边界与参数 |
| 性能验收 | “只实例化当前重型 Exhibit” | 增加可测的资源、响应和降级目标 |
| 测试 | 以源代码契约和人工视觉检查为主 | 增加 profile 完整性、比例、状态重置和 accessibility 契约 |

---

## 4. 整体布局方案

### 4.1 三种窗口状态

布局以可用内容宽度为准，不以设备名称为准。

#### A. Wide：`contentWidth >= 1180pt`

```text
Header：标题 / 馆藏规模                         Search / Family
Shelf：横向展柜（可跨全宽）
┌───────────────────────┬────────────────────────────────────────────────────┐
│ 当前选中及邻近展品    │ Object Stage                                        │
│ 约 280–340pt           │ 16:10 展台，方形物件居中或按 profile 定位             │
│                       │ Dossier controls 位于 stage 下沿                   │
└───────────────────────┴────────────────────────────────────────────────────┘
LIVE Workbench：占满下方有效宽度，保留 production component 的最佳尺寸
```

规则：

- Object Stage 是 Wide 状态的主要视觉面积；
- Shelf 不得与 Stage 抢夺同等视觉权重；
- Dossier 的身份标题在 Stage 下沿或右侧呈现，但不得再次生成一张完整 artwork identity card；
- Workbench 位于主展览之后，仍是页面内可直接操作的正式组件。

#### B. Compact：`960pt <= contentWidth < 1180pt`

```text
Header 可折行
Shelf：保持横向滚动
Object Stage：全宽 16:10
Dossier：标题、标签、Prev / Next / Reset 分两行
Workbench：向下延展
```

规则：

- 优先保留 Stage 的可操作面积，不用极小字体压缩内容；
- Search 和 Family 可以分成两行，但搜索范围必须仍然明确；
- Shelf 只允许自己的横向滚动，不引入第二个纵向滚动容器。

#### C. Minimum：`960pt x 640pt` 可用窗口

规则：

- Header、Shelf、Stage、Dossier、Workbench 按垂直顺序排布；
- Stage 仍保持 `16:10`，必要时降低环境装饰密度而不是拉伸 artwork；
- 当前展品名称、当前选中状态、Reset 和主要 Gameplay 控件必须可见或可顺序聚焦；
- 不允许 overlap、负边距、被底部裁切的操作控件；
- Workbench 可以继续向下滚动，但 Vault 本身不创建嵌套纵向 ScrollView。

### 4.2 固定的视觉层级

每个窗口状态都遵循以下权重：

1. 当前展品 Object Stage；
2. 当前展品名称、展陈副标题和主要动作；
3. LIVE Workbench；
4. Collection Shelf；
5. 辅助 metadata、Related Journey 和环境装饰。

`Object Stage` 不是新的 Artifact identity truth，也不是新的 Gameplay state。它是展陈容器，负责让当前组件获得比例、材质和空间关系。

### 4.3 视图责任

建议将现有 `ArtifactShowcaseView` 分解为以下责任单元。名称是实现建议，最终以代码现状和实现计划为准：

- `ArtifactVaultHeader`：标题、搜索、Family filter、馆藏规模；
- `ArtifactCollectionShelf`：横向选择与键盘浏览；
- `ArtifactObjectStage`：长方形展台和 2.5D 合成；
- `ArtifactExhibitDossier`：当前展品身份、标签、Prev / Next / Reset；
- `ArtifactLiveWorkbench`：按 `standard` 或 `vaultExhibit` 渲染现有 production component；
- `ArtifactRelatedJourney`：同 Family、策展路径或相邻浏览。

分解的目的不是增加容器数量，而是让每个视觉区域拥有单一责任，并便于对 Object Stage 单独做视觉测试。

---

## 5. Object Stage：方形 artwork 的长方形展陈方案

### 5.1 硬性比例规则

1. 原始 Artifact artwork 的有效内容保持 `1:1`；
2. 只允许 `aspectRatioFit` 或等价的等比缩放；
3. 禁止把方图直接填充 `16:10` 容器；
4. 除非原图本身带有透明边界，否则禁止通过 crop 消除留白；
5. artwork 的最终像素尺寸由 Stage 中央挂载框决定，不能随背板宽高非等比变化；
6. 当 detail artwork 缺失时，使用 thumbnail 或 master 的等比 fallback，并记录降级状态；
7. 当所有 presentation asset 缺失时，仍显示带纹理和铭牌的方形占位挂载框，不显示破损的大图区域。

### 5.2 Stage 的五层合成

```text
Layer 0  Environment Backplate  长方形背景、暗纹、柔和色温
Layer 1  Mount / Plinth        方形挂载框、台座、玻璃或金属边缘
Layer 2  Contact Shadow         物件接触阴影、遮挡、底部重量
Layer 3  Object Artwork         原始方图，1:1，主体层
Layer 4  Rim / Plaque / Light   轮廓高光、铭牌、局部反光和危险提示
```

这些层均属于 presentation layer。Layer 0、1、2、4 可以是静态资产、Core Image 生成结果或 SwiftUI / Metal 绘制结果；Layer 3 是现有 Artifact artwork 或现有 RealityKit surface。

### 5.3 长方形空间的填充策略

背板不能只是放大版 artwork。它应当表达“展柜的空间”，而不是假装是物件本身。

默认策略：

- Stage 使用 `16:10` 容器；
- artwork 位于中央方形 mount，默认占 Stage 高度的 `68%–78%`；
- mount 可根据 Artifact profile 在垂直方向轻微偏移，但不得遮挡主要主体；
- Stage 两侧用低对比环境纹理、材质渐变和柔和 vignette 填充；
- mount 下方提供台座或落影区，给物件明确的接触面；
- Stage 底部可显示短铭牌：编号、中文名、展陈 archetype；
- 铭牌属于辅助信息，不得代替 VoiceOver label，也不得把完整 Canon 说明塞进 Stage。

### 5.4 物件挂载类型

挂载类型由 presentation profile 指定，仅影响视觉表达：

- `framedSquare`：适合镜、牌、十字架、封印面等正面物件；
- `plinthSquare`：适合骰子、铜哨、权杖、灯等需要重量感的物件；
- `bookCradle`：适合笔记、游记、黄铜书等书页或册页类物件；
- `suspendedSquare`：适合星之杖、旧日之盒等需要悬浮或空间感的物件；
- `ritualTray`：适合净化、材料、规则或组合交互类物件。

挂载类型不改变 gameplay control，不改变 ArtifactFamily，不写入 Canon。

### 5.5 Artwork 与环境色

环境色只能作为视觉 token，不能作为 Canon 语义或危险等级的推断来源。

优先顺序：

1. profile 显式指定的低亮度环境 token；
2. 现有 artwork 的安全、低对比调色采样；
3. 统一的 obsidian / sacred slate fallback。

不允许直接将 artwork 的高饱和主色铺满 Stage，也不允许用颜色单独表达 selected、dangerous、disabled 或 Canon class。

---

## 6. 2.5D 资产与本机图像处理方案

### 6.1 设计目标

2.5D 的目标是让物件看起来有层次、重量和轻微空间关系，不是把普通方图伪装成高精度 3D 模型。任何视觉效果都必须服务于以下感受：

- 物件在背板前，而不是贴在背板上；
- 物件有接触面、边缘和厚度提示；
- 指针移动时可以产生极小的视差回应；
- 选中变化能让用户确认当前物件；
- Reduce Motion 开启时仍能完整理解状态。

### 6.2 离线 presentation asset 产物

每件 Artifact 的可选 2.5D 资源由原始方图生成，建议包含：

| 资源 | 作用 | 必须性 |
|---|---|---|
| `object` | 原始或清理后的方形物件图 | 必需 |
| `subjectMask` | 前景主体 alpha / 遮罩 | 可选；缺失时使用方形 mount |
| `coarseDepth` | 粗粒度深度，用于非常小的位移差 | 可选 |
| `contactShadow` | 物件与底座接触阴影 | 可选；可由 fallback 生成 |
| `rimLight` | 低强度边缘高光 | 可选 |
| `stageBackdrop` | 与物件匹配的背板或材质 token | 可选 |
| `profile metadata` | 尺寸、锚点、挂载类型、资产能力 | 必需 |

资源按 ArtifactID 和 presentation variant 组织，但不复制 displayName、shortGameplay、Canon class 或其他事实字段。

### 6.3 本机处理能力

第一阶段采用系统能力组合，不引入外部服务依赖：

- Vision：在本机生成或校验前景主体遮罩；
- Core Image：生成等比缩放、色调、模糊阴影、边缘高光和 fallback；
- Metal：在需要批量合成或低成本视差时进行纹理合成；
- SwiftUI：承载布局、可访问性、焦点和静态层级；
- RealityKit：仅继续用于概率之骰等已有真实 3D gameplay，不扩散为所有展品的默认渲染器。

离线处理可以作为开发期资产生成工具或首次本机缓存步骤，但运行时不得阻塞页面展示。没有生成结果时必须直接走静态 fallback。

### 6.4 运行时 2.5D 合成

运行时只为当前 selected Artifact 建立 2.5D 层级：

1. 加载 Stage 背板和 mount；
2. 挂载 square artwork；
3. 如果存在 `subjectMask`，将高光、接触阴影和轻微视差限制在主体边界；
4. 如果存在 `coarseDepth`，把指针引起的平移限制在 `4–8pt` 范围；
5. 采用短时、低幅度的 selection transition；
6. 只在当前 Stage 中激活动态层，Shelf 使用静态 thumbnail。

视差不能改变物件的可读尺寸、不能导致边缘脱离 mount、不能遮挡主要控件，也不能成为理解当前状态的唯一通道。

### 6.5 降级矩阵

| 能力 | 正常 | 缺失或关闭时 |
|---|---|---|
| subjectMask | 主体与背板有遮挡关系 | 方形 mount + 静态阴影 |
| coarseDepth | 轻微指针视差 | 静态层级 + selection crossfade |
| rimLight | 低强度边缘高光 | mount 边框和系统对比色 |
| Core Image / Metal | 高效合成 | SwiftUI 静态层和现有 artwork |
| Reduce Motion | 关闭视差、漂移和非必要动画 | 保留静态选中和文本反馈 |
| 资产缓存不可用 | 使用已打包的 detail / thumbnail | 使用 placeholder mount，不阻塞 Workbench |

降级不能移除 Artifact 名称、主要动作、错误信息或 selected 状态。

---

## 7. Presentation Contract 与架构边界

### 7.1 单一事实源

`ArtifactRegistry` 继续是 15 件 Artifact 的唯一馆藏事实入口。v1.1 新增的 presentation profile 只能通过 `ArtifactID` 关联，不得重新维护第二份 Artifact identity registry。

建议的 profile 内容：

```swift
struct ArtifactPresentationProfile: Sendable, Equatable {
    let artifactID: ArtifactID
    let archetype: ArtifactExhibitionArchetype
    let mount: ArtifactMountStyle
    let stageAnchor: StageAnchor
    let artworkVariant: ArtifactArtworkVariant
    let assetCapabilities: ArtifactPresentationAssetCapabilities
    let environmentToken: ArtifactEnvironmentToken
    let relatedIDs: [ArtifactID]
}
```

字段约束：

- `artifactID` 是唯一业务关联；
- `archetype`、`mount`、`stageAnchor` 和 `environmentToken` 只描述表现；
- `artworkVariant` 只能选择已经存在的 artwork 变体或 fallback；
- `assetCapabilities` 描述资源是否有遮罩、深度、阴影和高光；
- `relatedIDs` 只是策展导航，不能被解释成 Canon 关系；
- 禁止加入 `displayName`、`subtitle`、`shortGameplay`、`canonClass` 等已由 Registry 提供的字段。

### 7.2 `standard` 与 `vaultExhibit`

现有 `ArtifactPresentationContext` 继续保留两个表达环境：

- `standard`：产品普通页面，保留完整 `ArtifactComponentShell` identity panel；
- `vaultExhibit`：Artifact Vault，Object Stage 和 Dossier 承担主要身份表达，Workbench 内部减少重复 identity，扩大 gameplay surface。

实现要求：

- 通过 context 或显式参数切换，不复制 15 个 Artifact View；
- 默认值保持 `standard`，避免影响非 Vault 产品路径；
- `vaultExhibit` 不可改变 Domain resolver、Preview schema 或提交语义；
- 当某个 component 不支持完整 2.5D profile 时，只降级 Stage，不回退到重复身份卡片。

### 7.3 展览状态与 Gameplay 状态

Artifact Vault 只持有：

- selected ArtifactID；
- searchText；
- selectedFamily；
- keyboard focus / shelf navigation；
- local showcase revision；
- presentation asset loading state。

Production component 只持有自己的 Preview presentation state。选择展品时：

1. 更新 selected ArtifactID；
2. 清理上一件展品的 2.5D runtime cache 和动态任务；
3. 重新初始化当前组件的 Preview state；
4. 让 Stage 和 Workbench 使用同一次 selection revision；
5. 不写 Domain、不写 SQLite、不伪造 committed result。

Reset 必须同时清理：当前组件 Preview、局部 history、demo meters、Stage 动画和 transient asset state。Reset 不能撤销任何已经提交的世界事实。

---

## 8. 五类 Exhibition Archetype 的 Stage 规则

Archetype 只规定主视觉和 Stage 关系，不能覆盖 Artifact 自己的真实交互。

| Archetype | Stage 重点 | 默认挂载 | 运动限制 |
|---|---|---|---|
| Fate Instrument | 中心物件、概率/愿望/代价的结果层 | `plinthSquare` | 结果出现时允许一次短反馈 |
| Oracle & Archive | 物件、记录、揭示层 | `framedSquare` / `bookCradle` | 只对 reveal 做短 crossfade |
| Spatial Relic | 物件和空间边界关系 | `suspendedSquare` | 仅允许低幅视差 |
| Authority & Combat | 权柄、目标、约束和后果 | `plinthSquare` | 只响应真实 action 结果 |
| Rule & Purification | 材料、规则、净化过程 | `ritualTray` | 禁止装饰性连续动画 |

代表性验证顺序：

1. 概率之骰：验证 Stage 与 RealityKit 共存；
2. 阿罗德斯：验证 square mirror artwork 与 framed mount；
3. 0-02 或莱曼诺旅行笔记：验证 book / rule 类长方形展台；
4. 其余 12 件按 profile 批量接入；
5. 15/15 完整性测试和 fallback 测试。

---

## 9. 交互、键盘与可访问性

### 9.1 选择与浏览

- Shelf 仍是选择入口；
- 当 Shelf 获得焦点时，左右方向键浏览当前过滤集合；
- `Enter` 确认当前 focus item；
- Search 输入中，方向键不抢占文本编辑；
- `Prev` / `Next` 只在当前筛选集合内循环；
- `Reset` 不设置全局抢占性快捷键；
- Hover 只是增强反馈，不能替代 focus、selected 或文本状态。

### 9.2 Motion

允许：

- selected border / glow；
- 短 spring 或 ease transition；
- 当前展品真实 Gameplay 反馈；
- 概率之骰既有 RealityKit 交互。

禁止：

- 自动轮播；
- 多个 Shelf Item 同时持续发光；
- 背景长期漂移；
- 没有状态意义的旋转、缩放或粒子。

Reduce Motion 开启后必须：

- 关闭 pointer parallax；
- 停止装饰性循环动画；
- 将 selection 过渡降为短 crossfade 或无动画；
- 用文字、边框、静态高光或几何状态表达选中和结果。

### 9.3 VoiceOver 与对比度

- Stage 的 accessibility label 应包含“当前展品 + 名称 + 展陈类型”，而非报告底层纹理层；
- artwork 是内容图像，不得默认全部 `accessibilityHidden`；
- 背板纹理、阴影、粒子和装饰光隐藏于辅助技术；
- selected、dangerous、disabled 不得只依赖颜色；
- Increase Contrast、Reduce Transparency 下，mount 边界、铭牌、selected ring 和主要 action 仍清晰；
- 2.5D 不得改变 VoiceOver 顺序；顺序仍为 Header → Shelf → Stage / Dossier → Workbench → Related Journey。

---

## 10. 性能与资源预算

### 10.1 资源策略

- Shelf 只加载 thumbnail；
- Stage 只加载当前 Artifact 的 detail 和 presentation layers；
- 只允许一个重型 2.5D / RealityKit stage 同时活跃；
- 切换时取消上一件的加载任务、动画任务和非必要纹理引用；
- 不在页面初始化时创建 15 个完整 Gameplay tree；
- 不在 Shelf Item 中创建 `RealityView`、Metal renderer 或深度纹理；
- 大图使用 Asset Catalog 的变体和缓存，master 仅用于开发期处理或显式 fallback；
- presentation cache 与 Domain 数据分离，可清除并重建。

### 10.2 可测目标

这些是 v1.1 的测试目标，具体基线由真实 Mac 上的 Instruments 和 Release 构建确认：

| 指标 | 目标 |
|---|---|
| 首次打开 Vault | 不因 2.5D 预处理阻塞 Header、Shelf 和第一屏布局 |
| 已缓存展品切换 | Stage 在 `150ms` 内显示静态可读内容 |
| 未缓存展品切换 | `500ms` 内先显示静态 fallback，再异步提升效果 |
| Shelf 滚动 | 15 件缩略图浏览无明显持续卡顿，不创建重型 Stage |
| 重型对象并发 | 最大 1 个当前 2.5D / RealityKit stage |
| Reduce Motion | 不加载非必要的动态深度和装饰动画 |
| 资源失败 | 不阻塞 Workbench，不显示空白主区域 |

如果真实设备测得结果与目标冲突，以用户可感知的稳定交互和可重复的 Instruments 证据为准，不通过偷偷降低 artwork 质量来达标。

---

## 11. 测试与验收矩阵

### 11.1 单元与契约测试

至少覆盖：

- `ArtifactRegistry` 的 15 个 Artifact 都能解析到一个 presentation profile；
- profile 不含重复的 Canon identity 字段；
- `ArtifactMountStyle`、`StageAnchor` 和 asset capability 均有合法 fallback；
- square artwork 的 layout calculation 永远保持等比；
- stage 计算不会产生负尺寸、越界或不可见的主要 action；
- selection revision 变化会重置当前 Preview，而不会写入 Domain；
- Reset 同时清理组件 Preview、Stage transition 和 transient asset state；
- related IDs 只引用存在的 ArtifactID，且不改变 ArtifactRegistry；
- standard context 的现有行为保持不变；
- vaultExhibit 不再出现重复 identity panel 的完整标题与 artwork。

### 11.2 macOS Visual QA

人工检查窗口：

- `960×640`：堆叠布局、无 overlap、主要 action 可达；
- `1180×760`：Compact / Wide 边界切换；
- `1440×900`：主舞台、Shelf、Workbench 视觉权重；
- 选中 15 件 Artifact：无方图拉伸、无空白破损 stage；
- 代表性 archetype：骰子、镜、书、仪式物件；
- 指针移动：视差低幅、主体不脱离 mount；
- Reduce Motion、Increase Contrast、Reduce Transparency、VoiceOver、键盘左右键；
- artwork 资产缺失、mask 缺失、depth 缺失和缓存清除后的 fallback。

### 11.3 回归门槛

通过条件：

1. 15/15 Artifact 可从 Registry 进入 Vault；
2. 15/15 artwork 保持 1:1；
3. 15/15 至少有静态 Stage fallback；
4. 概率之骰仍使用现有 RealityKit production component；
5. standard 页面行为不回归；
6. Vault 选择、Prev、Next、Reset 和搜索筛选正常；
7. 无新增 Domain / DB 写入；
8. 目标尺寸下无 overlap、不可达控件或空白主展台；
9. 2.5D 资源缺失时仍能完整操作 Workbench；
10. Release 构建通过并在真实 macOS 窗口完成一次人工检查。

---

## 12. 分阶段实施顺序

### P0 — Layout and Context Foundation

- 将 `ArtifactShowcaseView` 的区域责任拆清；
- 引入 `Object Stage` 占位实现；
- 接入 `standard` / `vaultExhibit` context；
- 解决 Dossier 与 `ArtifactComponentShell` 的重复身份；
- 保持现有 15 个 production component 可运行。

### P1 — Shadow-box Stage Prototype

- 实现长方形 Stage、square mount、底座、接触阴影和铭牌；
- 为概率之骰、阿罗德斯、0-02 或莱曼诺旅行笔记完成三种代表性挂载；
- 验证 artwork 不拉伸、不被 Stage crop；
- 记录真实 Release 构建下的切换和滚动基线。

### P2 — Local 2.5D Asset Pipeline

- 定义 presentation asset 命名和能力元数据；
- 加入遮罩、粗深度、阴影、高光的本机处理入口；
- 增加缓存、异步加载、取消和静态 fallback；
- 接入 pointer parallax 和 Reduce Motion；
- 不改变 Artifact domain contract。

### P3 — 15 Artifact Profile Completion

- 为 15 件 Artifact 完成 profile；
- 按五类 archetype 调整 mount、anchor、environment token；
- 补齐相关导航和键盘 Shelf 浏览；
- 增加 profile completeness 和 ratio contract tests。

### P4 — Visual / Accessibility / Release Audit

- 完成三种窗口尺寸人工视觉检查；
- 完成辅助功能与运动偏好检查；
- 运行 Release 构建和性能基线；
- 确认无 Domain 写入、无重型对象并发、无遗留重复 identity；
- 将已验证结果回写到实现状态文档或对应 ADR。

---

## 13. 实施后的成功标准

用户打开 Artifact Vault 时，应能立即理解：

1. 我正在一个有秩序的神器收藏室里；
2. 当前选中的不是一张被拉伸的图片，而是一个置于展台中的物件；
3. 我可以横向浏览其他藏品；
4. 我可以在正式 Workbench 中操作它；
5. 视觉装饰增强了物件存在感，但没有伪造 Canon 或世界事实；
6. 窗口变窄、动画关闭、资源缺失时，仍然能找到并使用核心功能。

工程上必须同时成立：

- 事实仍由 `ArtifactRegistry` 和 Domain 层拥有；
- presentation profile 可删、可重建、可回归校验；
- 当前只激活一个重型展台；
- 方图永远保持 1:1；
- 2.5D 是增强层，不是功能依赖；
- standard 和 vaultExhibit 不产生两份 Gameplay truth。

---

## 14. 决策摘要

1. 用 `16:10 Object Stage + 1:1 square mount` 解决方图与长方形背板的结构性冲突。
2. 用环境背板、挂载框、接触阴影、主体 artwork、铭牌/高光五层建立实物感。
3. 用 Vision、Core Image、Metal 做本机 presentation asset 处理；RealityKit 只保留在已有真实 3D Gameplay 场景。
4. 2.5D 默认只对当前展品生效，Shelf 保持轻量静态缩略图。
5. 2.5D 资产缺失时，静态 Stage fallback 必须完整可用。
6. `ArtifactPresentationProfile` 只记录展示策略，不复制 Artifact identity 和 Canon 字段。
7. `vaultExhibit` 只改变表达上下文，不改变 gameplay、resolver、Domain 或 DB。
8. P0 先解决布局和身份重复，P1 再做三件代表性展品，P2 才批量引入 2.5D。
9. v1.1 的最终验收以真实 macOS Release 窗口、可访问性和可复现性能证据为准。
