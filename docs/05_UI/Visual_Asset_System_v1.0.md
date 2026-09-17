# World of Mysteries 视觉资产系统与组件皮肤改造方案 v1.0

> 状态：ACTIVE  
> 适用范围：`macos-app/` 的视觉资产、SwiftUI 组件皮肤与页面视觉迁移  
> 既有 Token 事实源：[`design_tokens.json`](design_tokens.json)  
> 当前批次记录：[`visual-assets/Batch_01_Core_Semantic_Icons.md`](visual-assets/Batch_01_Core_Semantic_Icons.md)

## 1. 目标

本方案把《诡秘世界》macOS 客户端从“零散组件与单点素材”升级为一套可复用、可扩展、可审计的 **Visual Asset System + Component Skin System**。

目标同时覆盖五个维度：

1. **世界观一致性**：神秘学、晚期维多利亚、灰雾、档案、秘仪、低饱和金属与理性秩序中的超凡裂缝。
2. **macOS 原生性**：保持 SwiftUI/macOS 的键盘、焦点、Hover、Toolbar、Inspector、可访问性与缩放行为。
3. **Token 一致性**：所有组件视觉语义优先映射到现有 Design Token，不建立第二套数值事实源。
4. **资产可维护性**：图标、纹理、徽记、卡框、插槽与背景具有稳定命名、来源、用途和渲染策略。
5. **小步交付**：所有工作按可独立审查、独立回滚、独立合并的小 PR 推进。

## 2. 总分式持久化协议

为避免执行环境、聊天上下文或临时工作区不稳定造成设计与决策丢失，后续视觉系统工作必须遵循以下规则：

- **总方案常驻仓库**：本文件保存完整目标、视觉语言、技术路线、资产分类和长期批次路线图。
- **每批一份实施记录**：每个涉及方案或设计判断的 PR，在 `docs/05_UI/visual-assets/` 下新增或更新对应 Batch 文档。
- **方案与实现同 PR**：如果一个 PR 只实现总体方案的一小部分，也必须把总体方案和该批实施记录一起提交或同步更新。
- **PR 描述不是唯一事实源**：PR body 只负责索引与审查摘要，关键设计结论不得只存在于 PR、聊天或临时文件中。
- **实际资产必须落盘**：只讨论方向不算完成；资产批次必须进入 `Assets.xcassets`，组件批次必须进入对应 Swift 源码目录。
- **状态可继承**：每批记录必须明确“已完成 / 未完成 / 下一批入口”，后续 Agent 可以仅靠仓库恢复上下文。

## 3. 视觉语言

### 3.1 核心气质

- Occult / 神秘学
- Late Victorian / 晚期维多利亚
- Gray Fog / 灰雾
- Archive / 古典文献与档案
- Ritual / 秘仪与封印
- Rational Order / 理性秩序
- Supernatural Fracture / 秩序中的超凡裂缝

### 3.2 材质母题

优先使用：

- 黄铜、乌金、深青铜、旧银；
- 旧纸、档案纸、深色木质；
- 灰雾、细颗粒、浅铜锈；
- 仪式刻痕、密文、星图、钟摆、圆环、封印纹。

避免：

- 高饱和魔法紫与霓虹 RGB；
- 大面积廉价 Bloom；
- 过度玻璃化；
- 商城式金光与装饰堆叠；
- 把整套 UI 做成不可缩放的大图拼贴。

### 3.3 光效规则

允许的主要光效只有：

- subtle glow；
- edge highlight；
- low-luminance bloom；
- soft fog；
- fine grain。

光效应服务于层级和状态，不应成为内容主体。

## 4. 资产分类

### A. Icons

- 主导航：World / Character / Codex / Ritual / Clue / Artifact / Inventory / Settings；
- 行为：Add / Remove / Edit / Search / Close / Back / Favorite / More；
- 世界交互：Divination / Spirituality / Fate / Gray Fog / Seal / Card；
- 状态：Warning / Success / Locked / Active / Cooldown。

### B. Buttons

- Primary / Secondary / Tertiary；
- Ghost / Toolbar / Icon-only；
- Ritual / Danger / Confirm / Accent；
- Segmented / Tab-like。

### C. Surfaces

- Sidebar section；
- Content card；
- Floating inspector；
- Modal / Sheet / Popover；
- HUD / Artifact slot。

### D. Special Chrome

- Card frame；
- Artifact slot；
- Badge / Seal / Tag；
- Section ornament；
- Divider ornament；
- Spirituality / Cooldown meter。

### E. Backgrounds & Textures

- Global app background；
- Gray Fog scene background；
- Codex / Archive background；
- Ritual background；
- Empty-state atmosphere；
- Parchment / metal / veil / subtle grain textures。

## 5. 命名与尺寸规范

### 5.1 Asset Catalog 命名

稳定语义名使用小写命名空间：

```text
wom.icon.world
wom.icon.ritual
wom.icon.codex
wom.icon.artifact
wom.button.primary.background
wom.panel.codex.surface
wom.texture.grayfog.soft
```

调用方不应散落硬编码字符串；语义名应逐步收口到注册表或类型化 API。

### 5.2 图标尺寸

标准逻辑尺寸：

```text
16 / 18 / 20 / 24 / 28 / 32 pt
```

矢量图标优先使用 Asset Catalog 单份可缩放 SVG，并启用 template rendering。只有无法矢量表达的质感资源才使用位图。

### 5.3 交互状态

组件层必须覆盖：

```text
normal / hover / pressed / selected / focused / disabled / loading
```

图标资产本身默认保持中性模板；颜色、强调、选中与禁用状态优先由 SwiftUI + Token 驱动，避免为每个状态复制位图。

## 6. Token 对齐原则

现有 `docs/05_UI/design_tokens.json` 继续作为设计 Token 事实源；Swift 实现继续通过现有 `DesignTokens.swift` 等映射消费。

视觉系统按以下语义域组织，但本方案不复制具体数值：

- Color
- Surface
- Stroke
- Shadow
- Radius
- Spacing
- Motion
- Iconography
- Texture

新增组件不得随意内嵌颜色、透明度、圆角、阴影和交互时长；如果现有 Token 不足，应在独立、小范围 PR 中补齐，而不是在组件内部形成隐式第二套 Token。

## 7. macOS 技术路线

优先级固定为：

### 第一层：SwiftUI 程序化绘制

适用于按钮底板、边框、状态层、焦点、高亮、阴影、轻量发光与动画。

### 第二层：Asset Catalog 矢量资源

适用于图标、Sigil、Seal、Ornament 与稳定轮廓图形。默认：

- scalable vector；
- template rendering；
- 由 SwiftUI Token 决定前景色和状态。

### 第三层：少量高质量纹理

适用于灰雾、旧纸、铜锈、帷幕与少数不可程序化的氛围层。纹理只用于质感增强，不承担控件状态逻辑。

## 8. SwiftUI 目标结构

目标能力逐步收口为：

```text
DesignSystem/
  Tokens/
  Styles/
  Icons/
  Surfaces/
  Backgrounds/
  Components/
```

现阶段仓库已有 `DesignSystem/`，迁移采用渐进式方式，不为追求目录形式一次性搬迁已有文件。

目标组件 API：

```text
WOMIconAsset
WOMIcon
WOMButtonStyle
WOMIconButtonStyle
WOMToolbarButtonStyle
WOMPanelBackground
WOMCardSurface
WOMSectionHeaderStyle
WOMTextureLayer
```

主题层提供语义，`Assets.xcassets` 提供资源；避免建立巨型全局资产 Singleton。

## 9. 可访问性与性能边界

- 支持键盘导航和 Focus Ring；
- Hover 不能成为唯一状态提示；
- 支持 Reduce Motion；
- 对 Reduced Transparency / Increase Contrast 保留可读边界；
- 图标必须能通过语义标签或调用方 Label 获得可访问性描述；
- 避免超大 PNG；
- 避免高频控件叠加多层实时 blur + mask；
- 重型背景优先分层缓存；
- 高频交互组件保持轻量。

## 10. 分批 PR 路线图

### Wave A — 资产尽快落盘

| Batch | 内容 | 状态 |
|---|---|---|
| 01 | 总体方案 + World/Ritual/Codex/Artifact 四个核心语义 SVG + `WOMIconAsset` | IN PROGRESS |
| 02 | Character/Clue/Inventory/Settings + Add/Remove/Edit/Search/Close/Back/Favorite/More | PLANNED |
| 03 | Warning/Success/Locked/Active/Cooldown + Divination/Spirituality/Fate/Gray Fog/Seal/Card | PLANNED |
| 04 | 盘点现有 Parchment/Gold/Veil/Slate/Velvet 纹理并建立语义 Texture Registry | PLANNED |

### Wave B — 组件皮肤基础

| Batch | 内容 | 状态 |
|---|---|---|
| 05 | `WOMIcon`：尺寸、template rendering、Label/Accessibility 接口 | PLANNED |
| 06 | `WOMButtonStyle` 基础状态 | PLANNED |
| 07 | `WOMIconButtonStyle` + `WOMToolbarButtonStyle` | PLANNED |
| 08 | `WOMPanelBackground` + `WOMCardSurface` | PLANNED |
| 09 | `WOMTextureLayer` | PLANNED |
| 10 | Section / Divider / Panel Chrome | PLANNED |

### Wave C — 真实页面迁移

| Batch | 内容 | 状态 |
|---|---|---|
| 11 | Component Gallery 作为 Design System Showcase | PLANNED |
| 12 | Sidebar | PLANNED |
| 13 | Codex / Archive | PLANNED |
| 14 | Ritual | PLANNED |
| 15 | Artifact 展示区域 | PLANNED |

### Wave D — 世界观特殊组件

后续继续独立拆分：Ritual Button、Artifact Slot、Artifact Card Chrome、Spirituality Meter、Relation Badge、Worldline Node、Achievement Badge、Empty State 与 Global Background。

## 11. PR 粒度规则

- 一个 PR 只处理一个明确批次 / Task Capsule；
- 每批从最新 `main` 建独立分支；
- 能独立回滚，不依赖未提交的本地状态；
- 不在视觉 PR 中顺带修改 Engine / Database / Domain Contract；
- 真实页面迁移与基础资产尽量分开；
- 每个 PR 都要回读 `base/head`、changed files、diff 与 CI；
- 未通过权威 CI 的内容不得宣称“已完成”。

## 12. Batch 01 设计决策

首批优先落盘四个高辨识语义：World、Ritual、Codex、Artifact。

共同规范：

- 24×24 viewBox；
- 单色模板 SVG；
- 约 1.0–1.5pt 主线；
- 图形采用原创几何母题，不复制商业美术或官方素材；
- 由 Asset Catalog 保留矢量表示；
- 由 `WOMIconAsset` 提供稳定语义名；
- 本批不改页面、不引入 `WOMIcon`，降低首次资产 PR 风险。

具体实现与验收见 [`visual-assets/Batch_01_Core_Semantic_Icons.md`](visual-assets/Batch_01_Core_Semantic_Icons.md)。
