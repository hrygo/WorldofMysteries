# Artifact Vault Exhibition Design v1.0

> 状态：ACTIVE DESIGN BASELINE  
> 适用范围：macOS Component Gallery / Artifact Vault / 15 件 Canon Artifact Gameplay Components  
> 目标平台：macOS 26+ / SwiftUI / Apple Silicon  
> 研究日期：2026-09-19  
> 当前实现基线：PR #90 已合入 main  
> 关联方案：Premium_World_Art_Artifact_Implementation_Plan_v1.0.md、Visual_Asset_System_v1.0.md、UI_交互基线_v1.0.md

---

## 1. 结论先行

Artifact Vault 不应继续被理解为“15 个组件的展示页”。

它应该成为一套同时满足三种用户意图的神器展览体验：

1. **我知道自己要找什么**：通过搜索与 Family 筛选快速定位；
2. **我想随便逛逛**：通过馆藏展柜、相邻展品与主题路径持续探索；
3. **我想真正摸一摸这件神器**：进入当前展品的 LIVE Artifact Workbench，运行正式 production component，而不是静态 mock。

因此 Artifact Vault 的核心产品模型不是传统 Inventory，也不是商店式 Grid，而是：

    Arrival / Orientation
            ↓
    Collection Shelf
            ↓
    Current Exhibit Dossier
            ↓
    Live Artifact Workbench
            ↓
    Related / Next Journey

这套结构必须同时保持四个边界：

- **对象优先**：神器本体、材质、危险性和独特交互是第一视觉层；
- **档案渐进披露**：Canon class、Family、玩法语义和风险信息按层次展开，不把所有字段一次塞满；
- **真实组件优先**：15 件神器继续由正式 Gameplay View 承载；
- **世界事实边界不变**：展览层只管理搜索、筛选、选择、浏览与 Preview Reset，不直接写 Domain / DB。

---

## 2. 外部调研结论

本方案调研了数字博物馆/馆藏产品与 macOS 平台交互规范，重点关注“如何让大量对象既可检索，又可探索，还能形成对象到对象的继续旅程”。

### 2.1 V&A：对象页不能成为数字死胡同

V&A 在重构在线馆藏时明确提出：

- 用户既有明确搜索意图，也会进入开放探索模式；
- 单一界面无法同等满足所有模式；
- 对象页不能只是孤立的“数字卡片”；
- 需要通过相关对象、故事、地点、人物、材质等上下文形成 onward journey；
- 搜索、筛选和视觉浏览应互补，而不是互相替代。

对 Artifact Vault 的直接启示：

- 当前展品不能只显示一件物品然后结束；
- 需要“上一件 / 下一件 / 同 Family / 相关主题”作为明确继续路径；
- 当前展品档案和 LIVE 操作台应是同一条旅程的两个层次，而不是两个互不关联的页面。

### 2.2 V&A 2025：强主视觉 + 横向浏览适合收藏型内容

V&A 2025 年对 Collections 页面继续调整：

- 强化 Header 的视觉冲击和信息层级；
- 用横向滚动 Carousel 替代静态 Grid，以便更轻松地浏览对象；
- 强调从 Discovery 到 Engagement 的路径。

对 Artifact Vault 的启示：

- 顶部 Artifact Vault Header 应负责定调和方向感，而不是堆工具；
- 15 件神器数量不大，横向“展柜/陈列轨”比密集 3×5 Grid 更像收藏展览；
- 用户应在保持当前展品上下文的同时浏览邻近对象。

### 2.3 Smithsonian：搜索与分类都是馆藏入口

Smithsonian Collections Search Center 提供：

- 一站式搜索；
- Gallery / Category 浏览；
- 多维筛选；
- “只看有媒体 / 只看馆藏对象”等范围收窄；
- 2D、3D、元数据都作为馆藏数字资产的一部分。

对 Artifact Vault 的启示：

- 搜索必须明确作用于“神器馆藏”，不能让用户猜搜索范围；
- Artifact Family 是第一层 Facet；
- Artwork、Canon metadata、Gameplay interaction 都属于同一个展品数字记录，不应割裂。

### 2.4 Rijksmuseum：搜索是发现层，不是对象本身

Rijksmuseum 的数据服务把 Search 明确定义为 Discovery Layer：

- 搜索返回“有哪些对象”；
- 具体对象记录再单独解析和呈现。

对 Artifact Vault 的启示：

- 搜索结果只应该帮助用户选中展品；
- 不应把完整 Artifact gameplay UI 塞进搜索结果；
- 选中后再进入 Current Exhibit Dossier + Live Workbench。

### 2.5 Apple HIG：搜索范围清晰、控制克制、运动有目的

Apple 当前 HIG 对本方案最关键的要求：

- Search 应有明确范围；
- 重要 Search 应放在容易找到的位置；
- Filter 可以帮助缩小范围；
- Toolbar/控制区不要过度拥挤；
- Motion 必须有明确目的，不应为了“高级感”持续运动；
- Reduce Motion 开启后应减少大幅旋转、缩放、多轴和持续动画；
- 重要信息不能只通过动画表达。

对 Artifact Vault 的启示：

- 搜索框明确写“搜索神器”；
- Family Picker 和搜索保持在同一检索区；
- 不使用自动轮播神器；
- 选中变化只使用短、可取消、低幅 transition；
- RealityKit / Ambient Field 在 Reduce Motion 下必须可降级。

---

## 3. 当前仓库事实与实现基线

### 3.1 单一馆藏事实源

神器清单由 ArtifactRegistry 驱动，目前固定 15 件：

1. 概率之骰
2. 阿罗德斯
3. 0-08 阿勒苏霍德之笔
4. 0-02 特伦索斯特黄铜书
5. 0-05 许愿神灯
6. 蠕动的饥饿
7. 莱曼诺的旅行笔记
8. 格罗塞尔游记
9. 阿兹克铜哨
10. 亵渎之牌
11. 海神权杖
12. 星之杖
13. 旧日之盒
14. 丧钟
15. 无暗十字架

Artifact Vault 不维护第二份神器名单。

### 3.2 现有五类 Family

当前 ArtifactFamily：

- 命运与因果
- 知识与隐秘
- 空间与世界
- 能力与战斗
- 规则、净化与基础能力

Family 是搜索/浏览 Facet，不代表 Canon 新分类。

### 3.3 现有 Canon Class

当前 ArtifactCanonClass：

- 封印物
- 神奇物品
- 高位特殊物
- 特殊物品

Canon Class 只作为身份标签，不直接决定危险等级、颜色或玩法。

### 3.4 已存在的高品质资产与真实玩法

当前已经具备：

- 15 件 Artifact Artwork 映射；
- thumbnail / detail 等运行时变体；
- ArtifactComponentShell；
- 15 件正式 Gameplay View；
- ProbabilityDieArtifactView 的 RealityKit 3D 骰子；
- PreviewArtifactResolver / PreviewProbabilityDieResolver 等 Gallery 演示 Resolver；
- Gallery Runtime Regression QA。

因此 Artifact Vault 后续不应重造 Artifact gameplay，而应持续提升“展陈层”和“生产组件的展览模式”。

---

## 4. 产品定位：不是 Inventory，而是 Digital Curiosity Cabinet

Artifact Vault 的视觉和交互定位：

> **维多利亚时代神秘学收藏室 + 数字博物馆 + 可操作实验台。**

不是：

- RPG 背包；
- 商城；
- 装备稀有度墙；
- 15 张同尺寸卡片；
- 纯数据库表格；
- 纯 3D 陈列柜。

“展览”需要同时存在三种感觉：

### A. Collection / 馆藏感

用户明确知道自己正在一个有编号、有分类、有秩序的收藏体系中浏览。

### B. Object Presence / 实体感

当前神器应像“真实物件”一样有重量、材质、比例与危险感。

### C. Experiment / 操作感

不是看完图片就结束，而是能在真实 Gameplay Component 中观察规则、触发 Preview、查看回执。

---

## 5. Artifact Vault 信息架构

### 5.1 Zone A — Arrival / Vault Header

职责：

- 告诉用户“这里是什么”；
- 显示馆藏规模；
- 提供搜索与 Family 筛选；
- 建立 Artifact Vault 世界观氛围。

保留内容：

- Artifact Vault wide artwork；
- “神器展览 · Artifact Vault”；
- “15 件馆藏”；
- 搜索；
- Family Picker。

禁止：

- 在 Header 放 Reset、Next、Gameplay action；
- 在 Header 展开完整 Canon 说明；
- 放自动切换的 Carousel。

### 5.2 Zone B — Collection Shelf / 馆藏展柜

职责：

- 快速视觉浏览；
- 保持当前展品上下文；
- 展示“还有什么可以看”。

每个 Shelf Item 建议只承担：

- Artwork thumbnail；
- 展品编号；
- 名称；
- Canon class 或极短身份提示；
- Selected state。

不承担：

- 长 Gameplay 描述；
- meter；
- action；
- history；
- 多 Badge 堆叠。

原则：

> Shelf 是“进入对象”的入口，不是对象详情页。

### 5.3 Zone C — Current Exhibit Dossier / 当前展品档案

职责：

- 建立当前神器身份；
- 用最少文字回答“它是什么、属于哪类、核心玩法是什么”；
- 提供展览导航。

首屏信息优先级：

1. Current Exhibit 状态；
2. 中文名称；
3. 英文/功能副标题；
4. Family；
5. Canon Class；
6. 一段 shortGameplay；
7. 上一件 / 下一件 / Reset。

暂不把以下内容全部塞到这里：

- 完整历史；
- 所有 meter；
- 原著长说明；
- 所有风险解释；
- 所有操作记录。

### 5.4 Zone D — Live Artifact Workbench / 实时操作台

职责：

- 直接运行 production Artifact component；
- 让用户“摸”神器；
- 展示真实 Preview state / Resolver feedback；
- 证明 Gameplay Component 不是静态示意。

原则：

- 不创建 Vault 专用伪交互；
- Probability Die 必须继续 RealityKit；
- 每件 Artifact 自己拥有自己的交互语法；
- 展览层不重写 Domain 结果；
- Reset 只重置 Preview presentation。

### 5.5 Zone E — Related Journey / 继续探索

当前 v1 可以只使用：

- 上一件；
- 下一件；
- 同 Family 过滤。

v1.1 后可以增加 presentation-only 的 Related Artifact：

- 同一玩法母题；
- 同一“代价”主题；
- 同一媒介（书、武器、镜、权杖等）；
- 同一探索路径。

Related 不能被描述为 Canon 关系，除非确有 Canon 数据源。

---

## 6. 展览模式与 Family 不是一回事

Family 是数据 Facet；Exhibition Mode 是表现策略。

建议新增五种 presentation-only Exhibition Archetype：

### 6.1 Fate Instrument / 命运仪器

适用：

- 概率之骰
- 0-08
- 许愿神灯

视觉：

- 中心物件；
- 因果线 / 概率 / 欲望与代价；
- 主操作明显；
- 结果区与代价区分离。

### 6.2 Oracle & Archive / 神谕与档案

适用：

- 阿罗德斯
- 莱曼诺旅行笔记
- 亵渎之牌

视觉：

- 物件 + 记录/揭示区；
- 信息逐层开放；
- Knowledge / Reveal state 强于 meter。

### 6.3 Spatial Relic / 空间遗物

适用：

- 格罗塞尔游记
- 星之杖
- 旧日之盒

视觉：

- 空间层级；
- Portal / Layer / Projection；
- 物件与世界空间关系比表单更重要。

### 6.4 Authority & Combat Apparatus / 权柄与战斗器具

适用：

- 蠕动的饥饿
- 海神权杖
- 丧钟

视觉：

- 当前目标；
- 可用能力；
- 风险与约束；
- 动作产生的世界后果必须明显。

### 6.5 Rule & Purification Relic / 规则与净化遗物

适用：

- 0-02
- 阿兹克铜哨
- 无暗十字架

视觉：

- rule / target / material / delivery；
- 更像“仪式工作台”；
- 不做传统 RPG 武器面板。

这五类是 UI presentation archetype，不修改 ArtifactFamily，也不进入 Domain。

---

## 7. 每件神器的展陈母题

| Artifact | 展陈母题 | 主视觉重点 | LIVE 主动作 |
|---|---|---|---|
| 概率之骰 | 命运被重新加权 | RealityKit 骰子 + 概率偏转 | 拖拽释放 / 投掷 |
| 阿罗德斯 | 会回应的镜 | 镜面凝视、问题与交换 | 提问 / 回答交换 |
| 0-08 | 因果书写器 | 羽毛笔、文本因果、暴露风险 | 编写候选 / 观察反噬 |
| 0-02 | 规则覆盖 | 黄铜法典、当前规则 | 提交规则候选 |
| 0-05 | 愿望契约 | 神灯、愿望与漏洞 | 许愿 |
| 蠕动的饥饿 | 活的能力容器 | 灵魂槽位、饥饿状态 | 调用灵魂能力 |
| 莱曼诺旅行笔记 | 能力记录册 | 页码、已记录/空页 | 记录 / 调用能力 |
| 格罗塞尔游记 | 书中世界入口 | 书页与 StorySpace | 进入 / 离开 |
| 阿兹克铜哨 | 世界内通信器 | 铜哨、信件、投递 | 发送 / 召唤 |
| 亵渎之牌 | 隐秘知识卡组 | Reveal state | 解锁知识 |
| 海神权杖 | 权柄与祈祷 | 权杖、祈祷队列、天气 | 回应祈祷 / 行使权柄 |
| 星之杖 | 基于认知的空间投射 | 星图、投射完整度 | 投射地点 |
| 旧日之盒 | 多层空间 | 层级结构与禁忌层 | 打开层级 |
| 丧钟 | 弱点锁定武器 | 目标、弱点、剩余弹药 | 锁定 / 射击 |
| 无暗十字架 | 净化工作台 | 材料、污染、分离 | 净化 / 提取 |

---

## 8. 主展台视觉层级

当前 production ArtifactComponentShell 已经包含 identityPanel。

因此 Artifact Vault 后续需要避免：

> Dossier 重复一次大标题 + Artwork，然后 ArtifactComponentShell 再重复一次同样大标题 + Artwork。

建议 v1.1 引入 presentation context：

    ArtifactPresentationContext
      ├─ standard
      └─ vaultExhibit

### standard

用于正常产品页面：

- 保留完整 identityPanel；
- detail panel 自包含。

### vaultExhibit

用于 Artifact Vault：

- 当前展品 Dossier 已承担身份说明；
- ComponentShell identityPanel 可缩窄、简化或转为更大纯 Artwork stage；
- gameplay controls 获得更高视觉权重；
- 避免“卡片套卡片”和重复标题。

这项改造必须是表达层环境值或显式参数，不允许复制 15 个 View。

---

## 9. Search / Browse 设计

### 9.1 Search Scope

搜索只作用于当前神器馆藏：

- displayName；
- subtitle；
- shortGameplay。

后续可扩展：

- aliases；
- presentation tags。

不要搜索：

- hidden Canon truth；
- user world DB；
- unrelated notes。

### 9.2 Facet

v1 只保留 ArtifactFamily。

原因：

- 15 件对象不需要十几个筛选项；
- Canon Class 可作为标签展示；
- 避免把馆藏变成数据库后台。

### 9.3 Browse

支持：

- 横向 Shelf；
- 上一件 / 下一件；
- 当前 Filter 内循环；
- Selected ordinal。

后续可增加：

- Related artifacts；
- Curated trails。

### 9.4 Curated Trails 建议

可作为 v1.2：

- “力量与代价”
- “会回应你的物件”
- “书与知识”
- “改变空间”
- “规则、净化与秩序”

Trail 是编辑策展，不是新的 Domain 分类。

---

## 10. 交互规则

### 10.1 选择

选中 Shelf Item：

- 切换 Current Exhibit；
- 重置该展品 Preview presentation；
- 不写 Domain；
- 不制造“已使用神器”的世界事实。

### 10.2 Reset

Reset 只允许重置：

- Preview model；
- animation；
- local history；
- demo meters。

不得：

- 反向改写 committed result；
- 表现成“撤销世界事实”。

### 10.3 Motion

允许：

- selected border / glow；
- 短 spring；
- Artifact 自己的真实交互运动；
- RealityKit 投掷。

禁止：

- 自动轮播 Shelf；
- 无意义悬浮；
- 全屏不断漂移雾效；
- 多件 Artifact 同时持续动画。

Reduce Motion：

- 停止自动循环；
- selection 使用 crossfade / short ease；
- RealityKit 保留必要结果反馈，但减少非必要旋转/抛物线强调；
- 任何状态必须有静态文本/几何反馈。

---

## 11. macOS 交互与键盘

v1 已有：

- Button 语义；
- Focus 系统；
- Search Field；
- Picker。

建议 v1.1：

- 当 Shelf 获得键盘焦点时支持左右方向键浏览；
- Search 保持单一入口；
- Reset 不设置抢占性全局快捷键；
- Gameplay Component 自己拥有 action shortcut 时继续生效；
- Hover 只作为增强反馈，不作为唯一可发现机制。

---

## 12. 响应式布局

### ≥ 1180 pt

目标：

- Header 横向；
- 搜索/筛选在右；
- Shelf 一行；
- Dossier 标题和 Controls 横向；
- Live Workbench 使用 Artifact 最佳宽度。

### 960–1179 pt

目标：

- Header 可折行；
- Filter/Search 可纵向；
- Shelf 保持横向；
- Dossier controls 必要时第二行；
- 不缩小 Artifact 主体到不可操作。

### 最小 960×640

硬标准：

- 不 overlap；
- 不出现负边距；
- 不通过 10pt 以下字体“塞进去”；
- Shelf 横向滚动；
- 搜索/筛选可折行；
- 当前展品标题和 Reset 可见；
- LIVE component 允许向下延展；
- Artifact 本体不可因 Header 过高而失去主要空间。

---

## 13. 视觉层级与材质

### 13.1 总体

遵循现有 WOM Visual System：

- obsidian；
- brass；
- sacred slate；
- low-luminance glow；
- fine grain；
- controlled fog。

### 13.2 Shelf

Shelf Item 的视觉重量必须明显小于 Current Exhibit。

推荐：

- thumbnail 约 118×88；
- 卡宽约 140–150；
- 只显示 2–3 行信息；
- selected border 明确；
- 非 selected 不做强 glow。

### 13.3 Current Exhibit

当前展品是整个页面视觉中心。

建议：

- title 使用 display hierarchy；
- Artwork / interactive surface 占主面积；
- Dossier metadata 保持紧凑；
- shortGameplay 是解释，不是营销文案。

### 13.4 不做统一“传奇橙装”

不同神器必须保留不同气质：

- 阿罗德斯不是武器；
- 0-08 不是普通笔；
- 0-02 不是技能书；
- 旧日之盒不是宝箱；
- 亵渎之牌不是抽卡入口。

---

## 14. 性能策略

Artifact Vault 的重资源原则：

> **只让当前展品成为重型对象。**

要求：

- Shelf 使用 thumbnail variant；
- Dossier 使用 detail variant；
- master 不直接进入 selector；
- 只实例化当前 selectedComponent；
- RealityKit 只在概率之骰当前展示时存在；
- 不同时创建 15 个 Reality / heavy animation tree；
- Shelf 使用 LazyHStack；
- 大图使用 Asset Catalog runtime variant；
- Ambient effect 不跨 15 个 Shelf Item 全开。

---

## 15. 状态与架构边界

### 15.1 Artifact Vault 拥有

- selection；
- searchText；
- selectedFamily；
- local showcaseRevision；
- presentation-only navigation。

### 15.2 Artifact Gameplay Component 拥有

- 自己的 UI 状态；
- action interaction；
- Preview model presentation。

### 15.3 Engine / Domain 拥有

- 世界事实；
- committed result；
- authoritative gameplay resolution。

### 15.4 禁止

- Artifact Vault 直接 SQLite；
- 根据 Artwork 推断 Domain；
- 用 Gallery Preview 写入 world.db；
- 用 UI 筛选结果改变 Canon；
- 把 presentation archetype 当作 Canon taxonomy。

---

## 16. 可访问性

必须持续覆盖：

- VoiceOver label：展品名称 + 当前选中；
- Focus Ring；
- Increase Contrast；
- Reduce Transparency；
- Reduce Motion；
- Differentiate Without Color；
- 键盘浏览；
- 文本不依赖 Artwork 才能理解；
- selected / dangerous / disabled 不只靠颜色。

Artifact thumbnail 是内容图像，不应全部 accessibilityHidden。

装饰背景、scrim、ambient particle 应隐藏于辅助技术。

---

## 17. Visual QA 与 Regression QA

Artifact Vault 的 QA 分两层。

### A. 人工 macOS Visual Review

用于判断：

- 展览感；
- 主次；
- 物件尺寸；
- 视觉重复；
- Artwork crop；
- RealityKit 手感；
- 文字密度。

人工测试优先窗口：

- 960×640；
- 1180×760；
- 1440×900。

### B. CI Smoke Regression

只兜底：

- App 可构建；
- Artifact Vault 可启动；
- 关键场景可渲染；
- 真实截图可产生；
- 生产组件没有丢失。

CI 不负责判断“够不够高级”。

---

## 18. 当前实现状态

### 已完成（PR #90）

- Artifact Vault Header；
- 搜索；
- Family filter；
- 横向 Collection Shelf；
- thumbnail + 编号 + selected state；
- Current Exhibit Dossier；
- 上一件 / 下一件；
- Reset；
- LIVE ARTIFACT WORKBENCH；
- 15 件 production component 保留；
- RealityKit Probability Die 保留；
- responsive ViewThatFits；
- ArtifactVaultExhibitionContractTests。

### 当前视觉债务

1. Dossier 与 ArtifactComponentShell identityPanel 仍存在身份信息重复；
2. 不同 Artifact 还没有独立 Exhibition Archetype；
3. Related Journey 尚未实现；
4. Shelf 尚未有键盘方向导航；
5. Probability Die 等重交互在 vaultExhibit 下仍可进一步扩大主舞台；
6. 部分 Artifact 的内部 UI 仍偏“工作台卡片”，缺少更强对象中心感。

---

## 19. 后续实施路线

### E1 — Vault Exhibition Foundation

状态：DONE

- Header；
- Shelf；
- Dossier；
- Prev/Next；
- LIVE Workbench；
- Search / Family；
- Contract Tests。

### E2 — Vault Presentation Context

目标：

- 新增 standard / vaultExhibit presentation context；
- ArtifactComponentShell 在 Vault 中消除重复 identity；
- 主展品 Artwork/RealityKit 获得更大舞台；
- 不复制 15 个 View。

完成标准：

- 所有 15 件 View 同时支持 standard 和 vaultExhibit；
- 产品页面默认行为不变；
- Vault 不出现双份标题/双份 Artwork 主视觉。

### E3 — Artifact Archetypes

目标：

- Fate Instrument；
- Oracle & Archive；
- Spatial Relic；
- Authority & Combat；
- Rule & Purification。

完成标准：

- 每种 archetype 至少有一个代表 Artifact 实机验证；
- archetype 只改变 presentation，不改变 gameplay。

### E4 — Onward Journey

目标：

- Related Artifact；
- Curated Trail；
- Shelf keyboard navigation。

完成标准：

- Current Exhibit 不再是 dead end；
- Filter / Trail / Related 三种路径不会制造第二份 Canon taxonomy。

### E5 — Final Vault Audit

检查：

- 15/15；
- 960×640；
- 1180×760；
- 1440×900；
- keyboard；
- VoiceOver；
- Increase Contrast；
- Reduce Transparency；
- Reduce Motion；
- Differentiate Without Color；
- RealityKit；
- no nested visual duplication；
- no Domain writes。

---

## 20. 明确不做

本方案不做：

- 把 Artifact Vault 变成装备背包；
- 稀有度颜色系统；
- 商城式卡片 Grid；
- 自动轮播；
- 15 件同时 3D；
- 15 件统一同一发光模板；
- 展览层自行生成 Canon 描述；
- Gallery Preview 直接 Commit 世界事实；
- 用官方商业资产替代现有原创 Runtime Artwork；
- 仅为了“沉浸”加入持续高成本背景动画；
- 用 CI 截图替代用户在真实 Mac 上的视觉判断。

---

## 21. 验收矩阵

| 维度 | v1 要求 |
|---|---|
| Collection | 15/15 来自 ArtifactRegistry |
| Discovery | Search + Family + Shelf |
| Navigation | Select + Prev + Next |
| Context | Family + Canon Class + shortGameplay |
| Interaction | production gameplay component |
| RealityKit | Probability Die 保留 |
| Reset | Preview-only |
| Responsive | 960×640 不 overlap |
| Scroll | Vault 不增加第二个纵向 ScrollView |
| Accessibility | Reduce Motion / Focus / VoiceOver / Contrast |
| Performance | 只实例化当前重型 Exhibit |
| Architecture | no DB / no Domain writes |
| QA | 人工视觉评审 + CI smoke regression |

---

## 22. 调研来源

### V&A

- Explore the Collections：
  https://www.vam.ac.uk/info/explore-the-collections
- Making the V&A’s collections more discoverable online：
  https://www.vam.ac.uk/blog/digital/making-the-vas-collections-more-discoverable-online
- Redesigning the V&A’s collections online：
  https://www.vam.ac.uk/blog/digital/redesigning-the-vas-collections-online
- 2025 Collections 页面刷新：
  https://www.vam.ac.uk/blog/digital/how-weve-refreshed-the-v-and-a-from-the-collections-pages

### Smithsonian

- Collections：
  https://www.si.edu/collections
- Collections Search Center：
  https://collections.si.edu/search/
- Open Access：
  https://www.si.edu/openaccess

### Rijksmuseum

- Collection Search / Discovery API：
  https://data.rijksmuseum.nl/tutorials/search/

### Apple

- Human Interface Guidelines — Searching：
  https://developer.apple.com/design/human-interface-guidelines/searching
- Human Interface Guidelines — Toolbars：
  https://developer.apple.com/design/human-interface-guidelines/toolbars
- Human Interface Guidelines — Motion：
  https://developer.apple.com/design/human-interface-guidelines/motion
- Reduced Motion evaluation criteria：
  https://developer.apple.com/help/app-store-connect/manage-app-accessibility/reduced-motion-evaluation-criteria

---

## 23. 设计决策摘要

后续实现统一遵循以下判断顺序：

1. **先让神器本体成立，再添加 UI。**
2. **先支持继续探索，再增加更多字段。**
3. **搜索负责找，Shelf 负责逛，Dossier 负责理解，Workbench 负责操作。**
4. **一个 Artifact 只存在一份 gameplay truth。**
5. **不同神器允许不同展陈母题，不强行统一成同一种卡片。**
6. **Artifact Vault 是 presentation layer，不是新的 Domain。**
7. **用户在真实 Mac 上的视觉评审优先于 CI 截图审美。**
8. **CI 只做防回归兜底。**
