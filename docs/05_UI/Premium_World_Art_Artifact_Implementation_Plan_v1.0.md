# World of Mysteries — Premium World Art & Artifact Visual Implementation Plan v1.0

> 状态：PROPOSED / A0 PLAN  
> 适用仓库：`hrygo/WorldofMysteries`  
> 目标平台：macOS 26+ / SwiftUI / Apple Silicon  
> 关联基线：`docs/05_UI/Visual_Asset_System_v1.0.md`、`docs/05_UI/visual-assets/Visual_QA_Contract_v1.0.md`  
> 当前事实：Visual System Foundation + Wave B–H 已完成；本方案开启新的 **Premium Art Program**，不是对既有组件系统的返工。

---

## 1. 结论先行

当前项目已经完成成熟的 UI 工程底座：typed icon、Button/Surface/Overlay、响应式布局、Window/Inspector、15 件 Artifact gameplay component、Visual QA / Contrast / Typography Guard 都已建立。

真正缺失的是一个决定产品是否“像一个真实的诡秘世界”的核心层：

> **Premium World Art + Premium Artifact Art**。

当前视觉更接近“高质量神秘学组件系统”，尚未达到“世界可被看见、神器具有实体感与位格感”的沉浸式产品目标。

下一阶段不再优先增加 ButtonStyle / Surface 种类，而是建立第一等公民的高品质美术资产层，并接入现有系统：

```text
Canon / World Research
        ↓
Art Bible / Canon Visual Brief
        ↓
Premium World Art       Premium Artifact Art
        ↓                       ↓
Atmosphere / Texture / Programmatic Effects
        ↓                       ↓
Existing WOM Visual System + Artifact Components
        ↓
Visual QA / Contrast / Typography / Layout / Asset Contracts
```

核心原则：

1. **先有世界，再有 UI 装饰。**
2. **神器组件围绕神器本体高品质插画组织，不再以 SF Symbol 充当主视觉。**
3. **高品质图片不能牺牲可读性、响应式布局和 macOS 原生交互。**
4. **当前 15 件 Artifact 的玩法与领域边界保持不变；本计划只增强表达层。**
5. **不复制官方动画、游戏或商业插画资产；只提炼世界观母题并生产原创视觉。**

---

## 2. 当前项目实现审计

### 2.1 已完成的工程能力

当前 Visual System 已完成：

- `WOMIcon` / typed asset & SF Symbols registry；
- `WOMButtonStyle`；
- `WOMPanelBackground` / `WOMCardSurface` / Overlay；
- Texture registry；
- Responsive `ViewThatFits` / adaptive Grid；
- 960×640 minimum window contract；
- 280 / 320 / 420pt Inspector contract；
- Contrast / Typography / Source Guards；
- Component Gallery / Visual QA Stress；
- Fate / Artifact / Ritual / Codex / App Shell production integration。

这些能力继续复用，不重做。

### 2.2 Artifact 当前已经不是空壳

`ArtifactRegistry` 已登记 15 件特殊物品：

1. 概率之骰 `probabilityDie`
2. 阿罗德斯 `arrodesMirror`
3. 0-08 阿勒苏霍德之笔 `alzuhodQuill`
4. 0-02 特伦索斯特黄铜书 `trunsoestBrassBook`
5. 0-05 许愿神灯 `magicWishingLamp`
6. 蠕动的饥饿 `creepingHunger`
7. 莱曼诺的旅行笔记 `leymanoTravels`
8. 格罗塞尔游记 `groselleTravels`
9. 阿兹克铜哨 `azikCopperWhistle`
10. 亵渎之牌 `cardsOfBlasphemy`
11. 海神权杖 `seaGodScepter`
12. 星之杖 `staffOfStars`
13. 旧日之盒 `boxOfGreatOldOnes`
14. 丧钟 `deathKnell`
15. 无暗十字架 `unshadowedCrucifix`

项目还区分：

- `sealedArtifact`
- `mysticalItem`
- `uniquenessArtifact`
- `specialObject`

因此后续美术 **不得把 15 件物品统一画成“传奇橙装”**。Canon class 是展示语义差异的重要输入。

### 2.3 Artifact 当前最大的视觉缺口

`ArtifactComponentShell.identityPanel` 当前主视觉核心仍是：

```swift
Image(systemName: descriptor.systemIcon)
    .font(.system(size: 62, weight: .ultraLight))
```

再叠加程序化 Ambient Field / Pulse Ring。

这套实现作为 fallback、可访问性和原型是合理的，但不足以承载：

- 物件材质；
- 历史痕迹；
- Canon 外形辨识；
- 位格；
- 危险性；
- “这是一件真实存在于世界中的东西”的实体感。

### 2.4 已有程序化 / 3D 表现应保留

概率之骰已经使用 RealityKit `ModelEntity` 实现可交互 3D 投掷，并保持 “Commit first · Presentation second”。

Premium Art 不应替代这种交互，而应补齐：

- 浏览缩略图；
- Artifact identity hero；
- Inspector / dossier 静态主视觉；
- contextual key art。

即：**3D / 程序化表现与 Premium Art 是互补关系。**

### 2.5 Asset Catalog 当前缺口

当前运行资产主要是：

- `PortraitKlein`
- `PendulumCitrine`
- Parchment / Gold / Fool Veil / Sacred Slate / Velvet textures
- `wom.icon.*` SVG semantic icons

尚未形成：

- World hero image family；
- Ritual / Codex / Fate scene art family；
- 15 件 Artifact 一一对应的 premium artwork family；
- Artifact contextual art family；
- artwork manifest / safe-crop / provenance contract。

这正是本计划补齐的核心。

---

## 3. 《诡秘之主》世界观调研 → 美术方向

### 3.1 不能把“诡秘”简单等同于黑紫克苏鲁

官方小说简介把两套现实并置在一个世界：

- 蒸汽、机械、枪械、大炮、巨舰、飞空艇、差分机；
- 魔药、占卜、诅咒、塔罗、封印物、教会与非凡者。

因此正确的视觉底层不是“时时刻刻宇宙恐怖”，而是：

> **可触摸的工业时代现实 + 渗入日常秩序的超凡异常。**

### 3.2 当前官方 IP / 游戏表达给予的方向

官方 IP 站点对游戏的描述包含：

- 维多利亚时代；
- 蒸汽朋克；
- 廷根；
- 黑荆棘安保公司；
- 贝克兰德；
- 神秘诡谲的音乐与环境。

2026 当前官方游戏条目进一步强调：

- 欧式古风神秘学；
- 廷根铁十字街；
- 贝克兰德灰雾；
- 五海；
- 源堡；
- 22 条途径；
- “力量背后，永远站着代价”。

本项目不复制其 UI 或资产，但这说明 IP 用户对“高质量环境实体感”的预期已经被抬高。

### 3.3 本项目 Art Direction 五个 Pillars

#### Pillar A — Mundane First / 日常先于异常

真实木材、铜器、纸张、煤烟、档案柜、煤气灯、工业器械先成立，再出现异常。

用途：App Shell、Codex、城市/档案语境、人物档案。

#### Pillar B — Occult Intrusion / 超凡侵入

异常不靠大面积紫光，而通过：

- 不自然的局部光；
- 影子/反射错误；
- 图案轻微错位；
- 雾与空间尺度不协调；
- 材质内部出现不可能结构。

用途：Artifact、Ritual、Fate。

#### Pillar C — Archive & Evidence / 档案与证据

知识边界、调查、档案、规则、记录是世界体验的重要组成。

视觉要能承载：

- 纸面记录；
- 封存编号；
- 鉴定状态；
- 风险说明；
- 事件痕迹。

但文字必须由 SwiftUI UI 层绘制，**不烘焙进 AI 图片**。

#### Pillar D — Gray Fog Is Semantic / 灰雾有语义，不是全局滤镜

灰雾主要服务：

- Fate；
- 源堡 / 高位空间；
- Worldline；
- 某些高位 Artifact context。

Codex、Ritual、普通世界场景不应全部套同一层灰雾，否则世界失去层次。

#### Pillar E — Power Always Has Cost / 力量与代价共存

Artifact 视觉不能只表现“酷”。每个物件至少表达一个危险/限制母题：

- containment；
- corruption；
- hunger；
- distortion；
- rule pressure；
- overexposure；
- unwanted attention；
- knowledge burden。

这与当前 `ArtifactRiskBand` 和 downside-oriented gameplay 一致。

---

## 4. Artifact Canon Art 原则

### 4.1 Canon appearance 先核验，再生成

美术生产不得从 UI icon 反推物件形态。

每件 Artifact 在正式出图前必须有 `Canon Visual Brief`：

```text
Artifact ID
Canon class
Novel/source references
Confirmed physical form
Confirmed materials/colors
Known transformations / active-state changes
Known size/scale
Forbidden inventions
Spoiler sensitivity
Gameplay presentation notes
```

Canon brief 是视觉制作输入，不是第二份 Domain Canon 数据库。

### 4.2 首轮形态核验入口

以下作为美术 brief 的研究入口，正式出图前仍需逐件回到原著/官方材料确认：

| Artifact | 核心物理形态研究入口 | 美术重点 |
|---|---|---|
| 阿罗德斯 | 银色镜子、古老纹样、眼状图案 | 反射错误、银器旧化、窥视感 |
| 蠕动的饥饿 | 薄的人皮手套，可随能力变化状态 | 皮肤材质、饥饿、灵魂槽位暗示，避免血浆化 |
| 莱曼诺的旅行笔记 | 掌心大小、铜绿色硬壳旧笔记本 | 铜绿旧化、不同纸张、记录痕迹 |
| 格罗塞尔游记 | 普通棕色山羊皮封面书 | “普通外形 / 内部世界”反差 |
| 许愿神灯 | 金色小型灯器、复杂神秘符号 | 金属厚重、愿望扭曲，不做卡通阿拉丁风 |
| 特伦索斯特黄铜书 | 黄铜薄片装订、黄铜页 | 规则、秩序、机械法典感 |
| 海神权杖 | 白色短杖/牙质，顶部细小蓝色宝石 | 海洋权柄、祈祷负担，不做大型王权权杖 |
| 旧日之盒 | 三层银黑旧首饰盒，镂空花纹与宝石 | 精致与禁忌并存；第三层危险感 |
| 星之杖 | 嵌宝石黑色手杖 | 空间/投射异常，不做星空法杖模板 |
| 丧钟 | 比普通左轮略长的铁黑色左轮 | 冷硬机械、弱点锁定、猎杀工具感 |
| 无暗十字架 | 古老青铜带尖刺十字架 | 纯化与伤害同体、古代遗物感 |
| 阿兹克铜哨 | 旧铜哨、神秘纹样 | 冷触感、无声召唤、亡灵关联 |
| 亵渎之牌 | 22 张类似大阿卡那的牌，可形成特殊书状结构 | 知识/途径揭示；禁止复制商业塔罗卡面 |

概率之骰、阿勒苏霍德之笔等同样需要正式 Canon brief 后才进入批准生产。

### 4.3 不做“统一稀有度皮肤”

`ArtifactCanonClass` 应影响视觉叙事，但不是 MMO rarity：

- `sealedArtifact`：containment / warning / cataloging；
- `mysticalItem`：可携带、人与物的长期使用痕迹；
- `uniquenessArtifact`：规则/权柄/不可替代性，更克制而不是更金；
- `specialObject`：知识、仪式、转换、结构性异常。

---

## 5. 游戏 UI / AAA 最佳实践 → 本项目规则

### 5.1 Art Direction 必须是一套系统，不是一堆漂亮图

AAA UI Art Direction 实践强调一致、可推导的视觉方向，从认知和艺术原则建立连贯表现。

落到本项目：

- 每张图必须属于一个 semantic domain；
- 每个 domain 有 palette / materials / light / density / safe zone；
- 不能每次生成一张“感觉不错”的图再强塞组件。

### 5.2 Key Art 与 UI Background 不是同一种图

前端 Key Art 的游戏实践强调，Front-End 图像应针对产品概念和 UI 重新设计，不等于把 marketing flat art 直接塞进界面。

因此运行时必须有独立 **UI-safe derivative**：

- 留 quiet zone；
- 支持裁切；
- 控制高频纹理；
- 不在文字区放强高光；
- 不烘焙文案。

### 5.3 Collection / Inventory 避免同时让所有物件竞争注意力

Artifact 浏览采用 progressive disclosure：

```text
Thumbnail / Selector
        ↓
Showcase Identity Panel
        ↓
Full Artifact Detail / Interaction
```

不把 15 张完整卡同时变成视觉竞争者。

### 5.4 UI 架构继续共享

现代大型游戏 UI 的经验强调 shared architecture 降低大量 collection/social/inventory screens 的复杂度。

本项目已有 `ArtifactComponentShell`、`ArtifactSection`、`ArtifactMeterCard` 等共享 primitive，因此 Premium Art 应注入 shell，而不是复制 15 个 art container。

### 5.5 macOS 游戏文本最低标准

Apple 对 macOS 游戏给出的默认文本基线为 13pt、最低 10pt，并要求文本在各显示环境保持可读、菜单适应不同比例、避免固定布局。

本项目现有 QA Contract 更严格：

- body >= 13pt；
- metadata >= 11pt；
- 10pt 仅用于极短辅助标签。

Premium Art 集成不能降低这一标准。

### 5.6 图片背景按最坏区域评估可读性

图片背景上不能简单使用白字即宣称完成。必须通过稳定承托层保证最坏局部背景下的对比度。

后续提供统一 `WOMArtworkScrim` / opaque surface / gradient field，而不是让每个页面自行调一个 opacity。

### 5.7 状态不能只靠颜色

Artifact risk / sealed / active / dangerous 状态继续保留现有 WOM badge / icon / border / dash 等第二信号；Premium Art 不承担唯一状态通道。

### 5.8 Focus 在复杂图片背景上仍要明显

系统 Focus Ring 或 WOM focus chrome 必须绘制在 artwork 上方。禁止用 subtle glow 作为唯一 Focus 信号。

---

## 6. 新统一视觉架构：5 层

### L1 — Premium World Art

- World / App hero；
- Gray Fog / Sefirah atmosphere；
- Ritual altar；
- Codex / archive room；
- Fate / worldline space；
- Artifact vault / evidence room。

### L2 — Premium Artifact Art

每件 Artifact 至少包含：

1. `objectMaster` — 单物件主图；
2. `thumbnail` — 浏览尺寸裁切；
3. `detail` — identity/detail panel 用；
4. `context` — 仅关键神器制作情境图。

### L3 — Atmospheric Assets

现有 textures + 必要新增：local fog、dust、ritual residue、metal wear、paper age、controlled light field。

Atmosphere 不承担状态信息。

### L4 — Existing WOM Component System

继续使用现有 WOM surface / icon / button / overlay / adaptive layout / Artifact shared primitives。

### L5 — Visual QA Governance

继续由现有 Guard 保底，并新增 artwork-specific contract。

---

## 7. Premium Art Runtime Architecture

### 7.1 新 typed registry（A1/A2 实现）

建议：

```swift
public enum WOMWorldArtworkAsset: String, CaseIterable, Sendable {
    case worldHero = "wom.art.world.hero"
    case grayFog = "wom.art.world.gray-fog"
    case ritualAltar = "wom.art.scene.ritual-altar"
    case codexArchive = "wom.art.scene.codex-archive"
    case fateWorldline = "wom.art.scene.fate-worldline"
    case artifactVault = "wom.art.scene.artifact-vault"
}

public enum WOMArtifactArtworkAsset: String, CaseIterable, Sendable {
    case probabilityDie = "wom.art.artifact.probability-die"
    // ... one-to-one with ArtifactID
}
```

### 7.2 Artifact registry 只增加 Presentation 映射

后续可给 `ArtifactDescriptor` 增加：

```swift
let artwork: WOMArtifactArtworkAsset
```

但不能把 domain power、downside truth、gameplay resolver、Canon progression 塞进图片 registry。

### 7.3 `ArtifactComponentShell` 改为 art-first identity panel

当前：SF Symbol → Name → metadata。

目标：

```text
┌──────────────────────────────┐
│ family / canon badge         │
│                              │
│       PREMIUM OBJECT ART     │
│       55–65% visual area     │
│                              │
│ stable contrast scrim        │
│ NAME                         │
│ subtitle / short gameplay    │
│ canon + state badges         │
└──────────────────────────────┘
```

Rules：

- artwork 不含文字；
- title 区使用稳定 Surface/scrim；
- art 加载失败时回退现有 `systemIcon`；
- Reduce Transparency 下增强承托层；
- Increased Contrast 下增强文本/边界承托，而不是简单把整图压黑。

### 7.4 `ArtifactShowcaseView`

不把 15 个 selector 全改成大卡。

A2：保持当前 horizontal selector，只增加 32–48pt 清晰 thumbnail。  
A3：只有可用性测试证明快速识别更好时，再评估 2–3 行 adaptive collection。

### 7.5 Probability Die 特例

RealityKit 3D 是交互主表现：保留。

新增 artwork 用于 library selector、Artifact dossier、static empty/locked state、hero moment。禁止用 2D 图替换 3D 投掷。

---

## 8. 图像生产规范

### 8.1 不生成完整 UI 截图当运行资产

生成物必须是 **art asset**，不是带按钮/标题/边框的完整 UI 图。

图片中禁止烘焙：

- artifact name；
- risk label；
- stats；
- fake ancient text；
- button；
- card frame；
- macOS chrome。

这些继续由 SwiftUI 渲染。

### 8.2 World / Scene Art 尺寸

Master 推荐：

- 4096×2560（16:10，贴近 Mac 内容窗口）；
- runtime derivative 2560×1600；
- wide header derivative 2400×900。

每张图必须定义：

- `focusRegion`；
- `quietZone`；
- `cropReserve`；
- light/dark hotspot map。

### 8.3 Artifact object master

Master：2048×2048。

要求：

- 主体完整可辨；
- 外围约 10–12% crop reserve；
- silhouette 在 96×96 缩略尺度仍可辨认；
- 不靠微小符文才能识别；
- 背景简洁、低频；
- 适合时提供 alpha-friendly 版本。

Runtime derivatives：

- 1024×1024 detail；
- 512×512 thumbnail；
- 必要时 4:5 inspector crop。

### 8.4 Context Art

关键 Artifact 可额外提供 2560×1600 情境图，但不是 15 件全部强制。

用途：story moment、Artifact dossier hero、Fate intervention transition、Ritual context。

### 8.5 内存与加载

4096×2560 RGBA 解码后约 40 MiB，因此：

- selector 禁止直接加载 master；
- selector 只用 512 thumbnail；
- detail 只加载当前 selection artwork；
- scene hero 使用 runtime derivative；
- 不同时常驻多张 4K master。

### 8.6 AI-assisted artwork 质量门槛

任何生成式美术必须人工 QA：

1. 物件结构无明显畸形；
2. 对称/机械结构可信；
3. 手、文字、齿轮、镜面反射等高风险区域无生成错误；
4. 无乱码文字；
5. 无官方商业图明显构图复刻；
6. 不模仿特定在世艺术家个人风格；
7. 与 Canon brief 一致；
8. 小尺寸 silhouette 可读；
9. 材质层次真实；
10. 不为了“神秘”过度添加触手、眼睛、紫光、符文。

---

## 9. 世界场景首批 6 张

### W1 — World Hero / Ordinary World, Hidden Mystery

工业时代城市/室内外交界；蒸汽、煤烟、路灯、纸张、交通等现实线索先成立，异常只占第二阅读层；两侧/底部预留 UI quiet zone。

### W2 — Gray Fog / Sefirah Atmosphere

用于 Fate / high-level world state。不是星空壁纸：强调尺度不确定、雾中秩序结构、远近关系异常、安静而非特效轰炸。

### W3 — Ritual Altar

用于 Bronze Altar / Divination / Ritual。蜡烛、器皿、纸张、材料真实，光源可解释，supernatural effect 局部出现。

### W4 — Codex / Archive

用于 Character Codex / dossier / Narrative Chronicle。木质、档案柜、旧纸、煤气灯/电灯过渡感；适合长期阅读，不用强 horror texture。

### W5 — Fate / Worldline

抽象但有规则；避免 generic neon graph；可将线、门、路径、纸面记录与雾融合。

### W6 — Artifact Vault / Evidence Room

不是 RPG loot room；更像封存证物、教会地下室、研究档案与仪式保存空间。物件被认真隔离，而不是炫耀展示。

---

## 10. Artifact 首批生产优先级

### P0 — 7 件 signature art

先覆盖视觉差异最大的 7 件，用于校准整个 Artifact Art Bible：

1. 阿罗德斯 — reflective / silver / sentient gaze
2. 阿勒苏霍德之笔 — writing / causality / ink
3. 特伦索斯特黄铜书 — law / brass / rule pressure
4. 许愿神灯 — distortion / gold / dangerous wish
5. 蠕动的饥饿 — body-material / hunger / soul loadout
6. 海神权杖 — authority / prayer / sea
7. 概率之骰 — fate / physical object / 与现有 RealityKit 对照

### P1 — 8 件补齐 15/15

8. 莱曼诺的旅行笔记
9. 格罗塞尔游记
10. 阿兹克铜哨
11. 亵渎之牌
12. 星之杖
13. 旧日之盒
14. 丧钟
15. 无暗十字架

P0 全部通过 Canon + Art QA 后才批量进入 P1，避免一次性生成 15 件后发现风格体系错误。

---

## 11. Art Bible：统一，但不“同质化”

### 11.1 Global material vocabulary

aged brass、silver / blackened silver、old copper / verdigris、ivory / bone / fang、leather / goatskin、paper / parchment、iron black、smoked glass / mirror、dark wood、wax / candlelight、fog / dust。

### 11.2 Light vocabulary

- warm practical light；
- cold moon/fog fill；
- local supernatural emission；
- high-level artifact 可有 impossible light，但控制面积。

### 11.3 禁止统一套模板

不要让所有 Artifact 都变成：黑底 + 金色圆环 + 中央悬浮 + 四周符文 + 下方烟雾 + 紫色边光。

这会把 15 个世界内物件变成 15 个商城商品。

### 11.4 每件 Artifact 必须有独立 visual verb

示例：

- Arrodes：**observe / answer**
- Quill：**write / alter**
- Brass Book：**declare / constrain**
- Wishing Lamp：**promise / distort**
- Creeping Hunger：**consume / borrow**
- Sea God Scepter：**command / hear**
- Box：**contain / displace**

视觉构图围绕 verb，而不只围绕名词外形。

---

## 12. 高品质图与 UI 可读性的结合

### 12.1 三个区域

任何用于 UI 背景的 premium art 必须声明：

```text
FOCUS ZONE   — 视觉主体
QUIET ZONE   — 文本 / 按钮 / Inspector 可覆盖
CROP RESERVE — 响应式裁切可牺牲区域
```

### 12.2 `WOMArtworkScrim`

A1 后续实现统一承托层，至少支持：

- `.none`
- `.bottomMetadata`
- `.leadingText`
- `.trailingInspector`
- `.fullReadable`

具体 alpha 不作为美术固定值，必须由 contrast QA 验证。

### 12.3 Accessibility

- Increased Contrast：增强承托 Surface / border，不依赖把图片整体压黑；
- Reduce Transparency：文本区域使用实色承托；
- Differentiate Without Color：状态仍用 badge/icon/shape；
- Reduce Motion：premium art 不依赖 parallax 才成立；
- Keyboard Focus：focus ring 始终由 UI 层绘制在 artwork 上方。

---

## 13. Asset 命名与目录建议

Runtime Asset Catalog：

```text
wom.art.world.hero
wom.art.world.gray-fog
wom.art.scene.ritual-altar
wom.art.scene.codex-archive
wom.art.scene.fate-worldline
wom.art.scene.artifact-vault

wom.art.artifact.probability-die
wom.art.artifact.arrodes
wom.art.artifact.alzuhod-quill
wom.art.artifact.trunsoest-brass-book
...
```

源文件 / provenance：

```text
docs/05_UI/artwork/
  art-bible/
  briefs/
  provenance/
```

禁止把大尺寸临时候选倾倒到仓库根目录。

---

## 14. Artwork Manifest / Provenance

后续增加 `artwork_manifest.json` 或等价 typed manifest，最少字段：

```json
{
  "id": "wom.art.artifact.arrodes",
  "role": "artifact_object",
  "canon_refs": ["source reference"],
  "master_aspect": "1:1",
  "runtime_variants": ["thumbnail", "detail"],
  "focus_region": "center",
  "quiet_zone": "bottom",
  "generated": true,
  "human_approved": true,
  "copyright_note": "original derivative visual; no official asset copied"
}
```

Manifest 记录 provenance，但不把生成 prompt 当作 Canon truth。

---

## 15. QA Gate：新增 Artwork 专项

### 15.1 Canon QA

- 物理类型正确；
- 已知材质/颜色不反转；
- 不把 mystical item 错标成 sealed artifact；
- 不把 UI gameplay abstraction 伪装成原著事实；
- spoiler level 可控。

### 15.2 Art QA

- 2048 master 无明显生成缺陷；
- silhouette 96px 可辨；
- object 与 background value separation 清晰；
- 无乱码、无不必要文字；
- 不依赖超强 bloom；
- 不套统一模板；
- context art 与 object art 保持同一对象身份。

### 15.3 UI QA

继续执行现有硬标准：

- text >= 4.5:1；
- long/important approved pairs target >= 7:1；
- body >=13pt；
- metadata >=11pt；
- key non-text >=3:1；
- 960×640 无 overlap；
- 1180×760 默认窗口；
- Inspector 280/320/420；
- long Chinese / English；
- Increase Contrast / Reduce Transparency / Reduce Motion / DWOC / Focus。

### 15.4 Asset Contract

A1/A2 后新增自动测试验证：

- typed artwork registry 与 Asset Catalog 双向一致；
- 15 Artifact artwork 不漏项；
- thumbnail/detail variant 存在；
- master 不被 selector 直接引用；
- scene art 不被当作 control state；
- artwork fallback 可用。

---

## 16. 实施路线

### A0 — 本方案 / Art Bible Foundation

产出：

- 本总体实施方案；
- research source record；
- Canon Visual Brief 模板；
- artwork naming / provenance / QA policy；
- PR / Capsule / Living Plan。

**A0 只做方案，不生成运行时图片。**

### A1 — 6 张 World / Scene Art

W1–W6，同时实现：

- `WOMWorldArtworkAsset`
- `WOMArtworkView`
- safe crop / scrim
- Gallery scene-art QA。

### A2 — Artifact P0 7 件

同时实现：

- `WOMArtifactArtworkAsset`
- `ArtifactDescriptor.artwork`
- art-first `ArtifactComponentShell.identityPanel`
- 7 件 object master + thumbnail/detail runtime variants。

### A3 — Artifact P1 8 件

补齐 15/15，并加入：

- Showcase thumbnail；
- full Artifact visual QA matrix；
- asset contract 15/15。

### A4 — Context Art / Production Integration

只为真正需要的关键节点做 context art：

- Fate intervention；
- Ritual；
- Codex；
- selected Artifact dossier；
- justified Empty/locked states。

### A5 — Final Visual Audit

最终检查：

- 15/15 Artifact；
- 6/6 world scenes；
- 960×640；
- 1180×760；
- Inspector states；
- accessibility modes；
- memory/load behavior；
- no official artwork copy；
- premium art 批准后，Artifact primary identity 不再停留于 SF Symbol。

---

## 17. PR / Commit 策略

延续已验证规则：

- 一个阶段性长期持久化 PR；
- 原子 commit 作为最小审查/回滚单位；
- 总方案 + Living Plan + Batch + Capsule 与实际资产同步；
- 每批图片尽早落远端；
- 不要求一个图片一个 PR；
- final head 跑完整 `MACOS_APP_P0`；
- required gates 全 success 后，按项目授权使用 verified expected head SHA 自动合并。

图片阶段原子 commit 示例：

```text
art(world): add gray-fog and world-hero premium artwork
art(artifact): add arrodes and quill object masters
feat(macos): integrate premium artifact artwork into component shell
test(macos): add premium artwork asset contracts
docs(macos): record artwork approval and provenance
```

---

## 18. 明确不做

本计划不做：

- 用官方动画截图直接当 App 背景；
- 用当前官方游戏截图/模型直接作为资产；
- 复制商业塔罗卡面；
- 在 AI 图里烘焙 UI 文本；
- 为了“高级感”降低文字对比度；
- 把所有 Artifact 画成统一金色传奇装备；
- 用高品质图替换 Domain / Resolver / Commit 逻辑；
- 为尚无真实领域数据的 placeholder 页面制造“假完成”美术。

---

## 19. 调研来源与使用边界

### 《诡秘之主》 / IP

- WebNovel official novel page: `https://www.webnovel.com/book/11022733006234505`
- 《诡秘之主 / 宿命之环》官方站点: `https://www.lotmworld.com/zh/lom`
- 当前官方游戏 TapTap 页面: `https://www.taptap.cn/app/281223`

Artifact 外形在正式生产前以原著章节/官方资料为最终依据；Fandom/Wiki 仅作为定位章节与交叉索引，不作为最高权威。

### Game / Platform UX

- Apple HIG — Designing for games: `https://developer.apple.com/design/human-interface-guidelines/designing-for-games/`
- Apple HIG — Typography: `https://developer.apple.com/design/human-interface-guidelines/typography`
- Apple HIG — Accessibility: `https://developer.apple.com/design/human-interface-guidelines/accessibility`
- Microsoft XAG 101 — Text display: `https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/101`
- Microsoft XAG 102 — Contrast: `https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/102`
- Microsoft XAG 103 — Additional visual channels: `https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/103`
- Microsoft XAG 113 — UI focus: `https://learn.microsoft.com/en-us/xbox/accessibility/xbox-accessibility-guidelines/113`
- Microsoft XAG 117 — Motion/distraction: `https://learn.microsoft.com/en-us/gaming/accessibility/xbox-accessibility-guidelines/117`
- GDC — Art Direction for AAA UI: `https://gdcvault.com/play/1025052/Art-Direction-for-AAA`
- GDC — Creating Living, Breathing Key Art for Your Front-End: `https://www.gdcvault.com/play/1025092/Creating-Living-Breathing-Key-Art`
- GDC — UI Engineering Patterns from Marvel’s Midnight Suns: `https://gdcvault.com/free/gdc-23/play/1028880/UI-Engineering-Patterns-from-Marvel`

外部游戏/官方 IP 图只用于研究 visual hierarchy、art direction、可读性与产品预期；运行时资产必须独立制作。

---

## 20. A0 Acceptance / 进入 A1 条件

A0 在以下条件满足后才结束：

1. 当前项目实现审计与 15 Artifact 清单确认；
2. Art Direction 五 Pillars 固化；
3. 6 张 World Art 首批清单固化；
4. Artifact P0/P1 优先级固化；
5. Canon Visual Brief 模板固化；
6. runtime artwork registry / shell integration 路线固化；
7. image safe-zone / crop / contrast policy 固化；
8. provenance / copyright boundary 固化；
9. Visual QA 硬标准继续追溯生效；
10. 本计划落仓库并通过项目门禁。

进入 A1 后，首要目标不是继续写文档，而是：

> **真正生成、筛选、落盘并集成第一批高品质 World / Artifact artwork。**
