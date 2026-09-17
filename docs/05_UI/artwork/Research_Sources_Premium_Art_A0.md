# Premium Art A0 — Research Sources & Authority Record

> 目的：记录 Premium Art Program A0 采用的外部研究来源、证据优先级与使用边界。  
> 本文件不是 Canon 数据库，也不保存第三方美术素材。

## 1. Authority hierarchy

### Tier 1 — Canon / official IP

用于确定世界观母题、时代语境与正式 Artifact 造型的最高优先级：

1. 原著正文 / 正式出版或官方授权文本
2. 阅文/《诡秘之主》官方 IP 站
3. 官方授权产品对世界设定的公开说明

### Tier 2 — Platform / industry primary guidance

用于 UI、可访问性、Art Direction 和工程策略：

- Apple Human Interface Guidelines
- Microsoft Xbox Accessibility Guidelines
- GDC Vault 一手演讲资料

### Tier 3 — Secondary index

Wiki / Fandom / 社区资料仅用于：

- 搜索 Artifact 别名；
- 定位可能的原著章节；
- 发现需要复核的物理描述。

不得单独作为最终 Canon Visual Brief 的批准依据。

---

## 2. Lord of Mysteries / IP sources

### Official novel page

`https://www.webnovel.com/book/11022733006234505`

研究结论：官方简介明确把机械、枪炮、巨舰、飞空艇、差分机与魔药、占卜、诅咒、塔罗、封印物并置。因此项目视觉底座应是“工业时代现实 + 超凡侵入”，而不是全局黑紫宇宙恐怖。

### Official IP site

`https://www.lotmworld.com/zh/lom`

研究结论：官方 IP 页面描述游戏背景融合维多利亚时代和蒸汽朋克，并点名廷根、黑荆棘安保公司、贝克兰德等场景。这支持项目使用真实时代材质、城市/档案环境作为主要视觉底座。

### Current official game listing

`https://www.taptap.cn/app/281223`

研究结论：当前官方游戏公开描述强调欧式古风神秘学、廷根铁十字街、贝克兰德灰雾、五海、源堡、22 条途径以及“力量背后永远站着代价”。本项目只把这些作为 IP 用户审美预期和世界表达参考，不复制其 UI、场景图、模型或商业资产。

---

## 3. Apple platform sources

### Designing for games

`https://developer.apple.com/design/human-interface-guidelines/designing-for-games/`

采用结论：

- macOS 默认游戏文本 13pt、最低 10pt；
- 文本必须与背景保持清晰对比；
- 菜单必须适应不同比例；
- 尽量使用动态布局而非固定布局；
- Mac 主要输入仍是键盘、鼠标和触控板。

本项目继续采用更严格的 body >=13pt / metadata >=11pt。

### Typography

`https://developer.apple.com/design/human-interface-guidelines/typography`

采用结论：跨不同上下文实际测试可读性；必要时扩大字号、提高对比度或调整字体。

### Accessibility

`https://developer.apple.com/design/human-interface-guidelines/accessibility`

采用结论：自定义字体需遵守平台推荐尺寸并考虑字重；Premium Art 不得破坏既有可访问性状态。

---

## 4. Microsoft Xbox Accessibility Guidelines

### XAG 101 — Text display

`https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/101`

用于文本尺寸、边缘、背景与可读性检查。

### XAG 102 — Contrast

`https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/102`

采用结论：关键 UI 元素必须与背景保持足够对比。Premium Art 背景上的 UI 必须按最终合成结果验证，而不是只看 Token 名义颜色。

### XAG 103 — Additional visual channels

`https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/103`

采用结论：重要状态不能只靠颜色；locked / dangerous / active 等状态继续保留 icon / shape / stroke / text 第二语义通道。

### XAG 113 — UI focus handling

`https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/113`

采用结论：Focus indicator 必须在各种背景、图片和 Overlay 上清晰可见；subtle glow 不能成为唯一焦点提示。

### XAG 117 — Visual distractions and motion settings

`https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/117`

采用结论：移动、闪烁、自动变化内容应可减弱/停止；当复杂运动背景无法避免时，为文字提供稳定承托层。

---

## 5. GDC primary industry sources

### Art Direction for AAA UI

`https://gdcvault.com/play/1025052/Art-Direction-for-AAA`

采用结论：UI Art Direction 必须是连贯系统，从视觉认知与一致性建立可推导规则，而不是逐张“漂亮图”的集合。

### Creating Living, Breathing Key Art for Your Front-End

`https://www.gdcvault.com/play/1025092/Creating-Living-Breathing-Key-Art`

采用结论：Front-End key art 应针对交互前端的概念和体验设计，不等于直接使用平面 marketing art。项目因此区分 master artwork 与 UI-safe runtime derivative。

### UI Engineering Patterns from Marvel's Midnight Suns

`https://gdcvault.com/free/gdc-23/play/1028880/UI-Engineering-Patterns-from-Marvel`

采用结论：现代游戏 UI 覆盖 inventory、social 等大量界面，应通过共享架构降低复杂度。项目已有 `ArtifactComponentShell` 等共享 primitive，因此 Premium Art 采用注入式集成，而不是重建 15 套 Artifact 外壳。

---

## 6. Copyright / provenance boundary

本研究允许：

- 阅读官方页面、HIG/XAG/GDC；
- 分析世界观母题、视觉层级、交互和可访问性；
- 为 Artifact 建立文字 Canon Visual Brief；
- 创作原创衍生视觉。

本研究不允许将以下内容直接落入运行时 Asset Catalog：

- 官方动画截图；
- 官方游戏截图或模型；
- 漫画扫描图；
- 商业塔罗卡面；
- 其他游戏 UI 截图；
- 未授权第三方插画。

每个正式 artwork 必须在 provenance 记录中说明来源与原创边界。
