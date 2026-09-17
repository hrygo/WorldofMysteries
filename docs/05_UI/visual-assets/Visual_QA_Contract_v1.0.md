# World of Mysteries — Visual QA Contract v1.0

> 状态：ACTIVE / RETROACTIVE  
> 适用范围：所有已合入与未来新增的 macOS 视觉组件、页面、Overlay、状态视图与 Design System primitive。  
> 原则：历史代码不豁免；视觉风格不能以牺牲可读性、对比度、布局稳定性为代价。

## 1. 依据

本契约采用 Apple macOS/HIG 的清晰性、系统组件、布局与辅助功能原则，并以 WCAG 2.2 的对比度阈值作为最低量化基线。

官方参考：
- Apple HIG / Text Views: https://developer.apple.com/design/human-interface-guidelines/text-views
- Apple HIG / Labels: https://developer.apple.com/design/human-interface-guidelines/labels
- Apple HIG / Text Fields: https://developer.apple.com/design/human-interface-guidelines/text-fields
- Apple App Accessibility / Sufficient Contrast: https://developer.apple.com/help/app-store-connect/manage-app-accessibility/sufficient-contrast-evaluation-criteria
- W3C WAI / WCAG contrast checks: https://www.w3.org/WAI/test-evaluate/preliminary/

## 2. Contrast Contract

### 2.1 文字
- 常规正文、按钮文字、表单文字：最终合成对比度 **>= 4.5:1**。
- 大字号文字可接受 **>= 3:1**，但本项目不以“放大字号”规避正文可读性问题。
- 长阅读正文、主要状态文字、关键说明：目标优先 **>= 7:1**。
- 不允许通过低 opacity、纹理、Material 或 Glow 将原本达标的 Token 组合降低到阈值以下。
- 对比度以最终 Surface + Texture + Opacity 合成后的效果评估，而不是只看源 Token。

### 2.2 非文字
- 关键图标、Focus ring、Selected 边界、输入框/按钮边界、状态轨道：相邻背景对比度 **>= 3:1**。
- 状态不得只靠颜色区分；应同时使用 icon / stroke / shape / text / dash 等第二语义通道。

### 2.3 已知 Token 风险
当前 Token 定量审计已确认：
- `textTertiary` 在 Obsidian Surface 上通常达标，但在 `deepVoid` 上约 3.56:1，不可作为常规小字号正文。
- `brassGoldMuted` 在 `deepVoid` 上约 3.41:1，不可承载关键小字号语义。
- `textPrimary` 在 `crimsonStar` 上约 3.85:1；Danger 实心按钮需改用更高对比度前景组合。

## 3. Typography Legibility Contract

- 正文默认使用 `Font.Mystic.bodyMedium` 或更大：**>= 13pt**。
- 用户需要持续阅读的说明/元数据：默认 **>= 11pt**。
- **10pt** 仅允许：短数字、快捷键、极短徽章/辅助标签；必须使用清晰字重和达标对比度。
- **9pt 及以下** 不允许承载关键用户语义；仅可作为非必要装饰信息，并应优先移除或放大。
- 长正文不使用装饰字体；自定义/楷体/衬线字体必须限制在标题、叙事或短文段，并验证中文笔画清晰度。
- 不允许用低 opacity 代替合理字号/字重层级。
- `lineLimit(1)` 不能用于可能增长的关键标题/状态而没有 tooltip、wrap 或布局退化策略。

## 4. Layout Collision Contract

必须至少覆盖以下窗口与内容压力：
- 最小窗口：当前 App 声明的最小尺寸（现阶段 960×640）。
- 标准窗口：约 1180–1280pt 宽。
- 宽窗口：约 1440pt 及以上。
- 中文长标题、英文长标题、长状态值、Badge 增长、Loading/Error/Empty 状态。

禁止：
- 依赖负 offset / 负 padding 维持主布局。
- 用 overlay 承载会改变布局尺寸的正文或操作。
- 固定宽度造成文字与按钮互相覆盖。
- HStack 在最小窗口下没有 wrap / priority / truncation 策略却承载可增长内容。

允许例外：
- Focus ring、纯装饰 stroke/glow 等不参与布局的视觉层可使用负 inset/padding，但不得影响 hit target 或正文几何。

## 5. Alignment & Symmetry Contract

- 同组卡片使用一致 padding、圆角、标题基线、图标尺寸和内部节奏。
- 同级按钮高度、视觉重量、间距保持一致。
- 双栏/多栏结构必须有明确比例与对齐线；视觉对仗区域不能出现无意的 1–3pt 漂移。
- Grid 优先于依赖魔法数字拼出的多列 HStack。
- `Spacer` 用于弹性分配，不用于掩盖缺失的列宽/对齐规则。
- 非对称必须服务信息层级，而不是修补布局问题。

## 6. Accessibility States

历史组件和新组件都必须检查：
- Increased Contrast
- Differentiate Without Color
- Reduce Motion
- Reduce Transparency
- Keyboard Focus / Tab order
- inactive window appearance

辅助功能模式下不得出现：
- 文字变得更暗；
- Focus ring 被纹理吞没；
- 状态仅剩颜色；
- Reduce Transparency 后文字直接落在复杂纹理上。

## 7. Visual Stress Specimen

Component Gallery 必须逐步增加 Visual QA 区域，至少包含：
- minimum width
- long Chinese / English content
- multiline labels
- dense badges
- loading / success / warning / danger / empty
- selected / focus / disabled
- overlay surfaces

Gallery specimen 是人工视觉回归入口，不替代 Xcode/Swift tests。

## 8. Review Checklist

任何视觉 PR 在 Ready 前必须回答：
1. 主要文字/背景组合是否达到对比度阈值？
2. 是否存在 <11pt 的语义文本？为什么？
3. 960pt 最小宽度是否存在重叠、截断或按钮挤压？
4. 长中文/英文是否破坏对齐？
5. 同组卡片/按钮是否基线、尺寸和间距一致？
6. Overlay 是否遮挡关键内容？
7. 高对比度/减少透明度/减少动态效果是否稳定退化？
8. 是否存在用 offset/overlay/硬编码 frame 掩盖结构问题？

## 9. Backfill Rule

本契约自 v1.0 起追溯应用于 Wave A–E。已合入代码发现不满足时，必须通过 Visual QA Backfill 原子 commit 修复；不得以“已合并”“旧代码”“只是视觉效果”为理由保留缺陷。
