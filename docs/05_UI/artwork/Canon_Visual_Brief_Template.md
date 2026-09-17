# Canon Visual Brief Template

> 用途：在任何 World / Artifact premium artwork 正式生成前，先固定可核验事实、允许创作空间、禁止发明项与 UI 使用约束。  
> 重要：本模板是 **美术生产输入**，不是第二份 Canon 数据库；领域正典仍遵循项目既有 Canon 边界。

## 1. Identity

- **Artwork ID**：
- **Artifact / Scene ID**：
- **Display Name**：
- **Role**：`world_hero | scene | artifact_object | artifact_context`
- **Canon Class**（如适用）：`sealedArtifact | mysticalItem | uniquenessArtifact | specialObject`
- **Spoiler Level**：`public | early | mid | late | restricted`

## 2. Canon Evidence

### Primary sources

- 原著章节 / 官方资料：
- 可直接确认的物理事实：

### Secondary index sources

- Wiki/Fandom/社区索引：
- 仅用于定位哪些章节/官方资料需要复核：

> Secondary source 不得单独支撑最终造型批准。

## 3. Confirmed Physical Form

- 物件/场景类型：
- 尺寸/尺度：
- 主材质：
- 次材质：
- 主色：
- 已知纹样/结构：
- 磨损/时代痕迹：
- 激活前形态：
- 激活后可确认变化：

## 4. Canon Unknowns / Creative Freedom

以下内容原著未明确，可进行原创补完：

- 
- 

补完原则：不得与已确认事实冲突；优先服从时代、制造工艺、使用场景与 Artifact gameplay identity。

## 5. Forbidden Inventions

- 不得改变已确认的物理类别；
- 不得反转已确认材质/颜色；
- 不得把 gameplay abstraction 画成 Canon 事实；
- 不得为了“神秘”任意增加触手/眼睛/紫色魔法光/大面积符文；
- 不得加入无法说明来源的现代工业设计语言；
- 不得复制官方动画、游戏、漫画或商业卡面的具体构图与资产。

项目专项禁止项：

- 
- 

## 6. Visual Verb

物件/场景的核心动作语义：

- **Primary verb**：
- **Secondary verb**：

示例：`observe / answer`、`write / alter`、`declare / constrain`、`contain / displace`。

构图优先表达 verb，而不是仅把物件居中悬浮。

## 7. Material & Lighting Direction

- 主材质词汇：
- 真实世界光源：
- 超凡局部光源：
- 允许的异常：
- 禁止的特效套路：

## 8. Composition Contract

### Artifact object master

- Master: 2048×2048
- Crop reserve: >= 10–12%
- 96×96 silhouette 可识别：`YES / NO`
- Alpha-friendly candidate：`YES / NO`

### Scene / world art

- Master: 4096×2560
- Runtime: 2560×1600
- Header derivative（如需）: 2400×900

### UI zones

- **FOCUS ZONE**：
- **QUIET ZONE**：
- **CROP RESERVE**：
- **Bright hotspot**：
- **Dark hotspot**：

## 9. Runtime Usage

- selector thumbnail：
- detail / identity panel：
- Inspector：
- world/scene hero：
- context art：
- fallback：typed SF Symbol / existing programmatic presentation

## 10. Visual QA

- [ ] Canon primary evidence reviewed
- [ ] No known physical contradiction
- [ ] No baked UI text
- [ ] No gibberish/AI text
- [ ] Structure/materials are credible
- [ ] 96px silhouette readable
- [ ] No unnecessary bloom/neon-purple cliché
- [ ] Context/object variants share the same identity
- [ ] Quiet zone works for real SwiftUI typography
- [ ] Text over final composition can reach >=4.5:1 with approved scrim/surface
- [ ] Key UI affordances can reach >=3:1
- [ ] 960×640 crop/layout checked
- [ ] 1180×760 default checked
- [ ] Inspector 280pt case checked when applicable
- [ ] Increased Contrast checked
- [ ] Reduce Transparency checked
- [ ] Reduce Motion does not remove necessary meaning

## 11. Provenance

- Generation / production method：
- Source reference list：
- Human reviewer：
- Approval date：
- Copyright note：原创衍生视觉；不复制官方商业资产。
- Final status：`DRAFT | CANON REVIEWED | ART APPROVED | RUNTIME APPROVED`
