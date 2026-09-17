# World of Mysteries 视觉资产系统与组件皮肤改造方案

> 文档版本：v1.1（持续演进）  
> 状态：ACTIVE  
> 适用范围：`macos-app/` 的视觉资产、SwiftUI 组件皮肤、应用级视觉壳层与页面视觉迁移  
> Token 事实源：[`design_tokens.json`](design_tokens.json)  
> 执行状态事实源：[`visual-assets/README.md`](visual-assets/README.md)

## 1. 总目标

把《诡秘世界》macOS 客户端建设为一套可复用、可扩展、可审计的 **Visual Asset System + Component Skin System**，同时满足：

1. **世界观一致性**：神秘学、晚期维多利亚、灰雾、档案、秘仪、低饱和金属，以及理性秩序中的超凡裂缝。
2. **macOS 原生性**：保留系统键盘、Focus、Toolbar、Inspector、Sheet、Popover、可访问性、窗口状态与缩放行为。
3. **Token 一致性**：视觉数值继续以现有 Design Token 为事实源，不在新组件内形成第二套隐式参数系统。
4. **资产可维护性**：图标、纹理、徽记、卡框、插槽、背景与状态语义拥有稳定命名和 typed API。
5. **工程可恢复性**：方案、Batch 记录、Task Capsule、代码和资产尽早推远端，不能依赖聊天或临时执行环境。

## 2. 持久化与交付协议

### 2.1 当前有效规则

- **总方案常驻仓库**：本文件保存长期视觉原则、技术边界和总体路线。
- **Living Plan 常驻仓库**：`visual-assets/README.md` 保存当前真实执行状态、PR 与恢复入口。
- **每个涉及设计判断的阶段必须有 Batch 文档**：记录本阶段范围、决策、完成项、未完成项与下一入口。
- **同一连续工作流优先使用长期持久化 PR**，不再以“PR 必须最小化”为目标。
- **原子 commit 是最小审查与回滚单元**：每个 commit 应具备单一语义目的。
- **方案与实现同步落盘**：涉及方案变化时，总体方案 / Living Plan / Batch 记录必须与对应代码或资产一并推进。
- **PR body 不是唯一事实源**：关键设计结论不得只存在于 PR 描述或聊天。
- **最终 head 统一验证**：稳定增量持续推远端，准备合并时执行一次完整 `MACOS_APP_P0`；失败以原子 fix commit 修复最终 head。
- **不绕过主分支保护**：CI/readback 是合并前事实验证层。

### 2.2 历史规则说明

本方案初版曾要求“一个 Batch 一个最小 PR”。该规则已被实际工程经验替代：当前采用 **一个阶段性长期 PR + 多个原子 commit**。旧 Batch 文档与历史 PR 保留用于追溯，但不再作为未来 PR 粒度要求。

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

优先：黄铜、乌金、深青铜、旧银、旧纸、档案纸、深色木质、灰雾、细颗粒、浅铜锈、仪式刻痕、密文、星图、钟摆、圆环与封印纹。

避免：高饱和魔法紫、霓虹 RGB、大面积廉价 Bloom、过度玻璃化、商城式金光、装饰堆叠，以及不可缩放的大图拼贴。

### 3.3 光效规则

允许的主要光效：

- subtle glow
- edge highlight
- low-luminance bloom
- soft fog
- fine grain

光效只服务于层级、反馈与状态，不成为内容主体。

## 4. 资产与语义分类

### A. 世界观 Icons

World / Character / Codex / Ritual / Clue / Artifact / Inventory / Divination / Spirituality / Fate / Gray Fog / Seal / Card / Worldline / Notes。

实现：原创可缩放 SVG + Asset Catalog + typed registry。

### B. 平台行为与通用状态

Add / Remove / Edit / Search / Close / Back / Favorite / More，以及 Warning / Success / Locked / Active / Cooldown。

实现：SF Symbols + `WOMSystemIcon` / `WOMStatusIcon`；不得为了资产数量复制一套仿系统 SVG。

### C. Controls

Primary / Secondary / Tertiary / Toolbar / Icon-only / Ritual / Danger，以及后续 Segmented / Tab-like。

状态由 SwiftUI style 驱动：

```text
normal / hover / pressed / selected / focused / disabled / loading
```

### D. Surfaces

- Sidebar / Content Card
- Floating Inspector
- Popover / Sheet content chrome
- HUD / Status Banner
- Artifact / Ritual / Codex surfaces

**呈现机制继续由系统 API 负责**：`.sheet` / `.popover` / `.inspector` 不被自定义伪窗口替代；WOM 只提供视觉 chrome 与内容容器。

### E. Special Chrome

Card frame / Artifact slot / Badge / Seal / Tag / Section ornament / Divider / Spirituality meter / Worldline node。

### F. Backgrounds & Textures

Global app background / Gray Fog atmosphere / Codex Archive / Ritual / Empty-state atmosphere / Parchment / metal / veil / slate / velvet。

## 5. 命名与 typed API

### 5.1 Asset Catalog

稳定世界观资源使用小写命名空间：

```text
wom.icon.*
wom.ornament.*
wom.texture.*
```

现有大纹理继续保留物理 Asset Catalog 名称，通过 `WOMTextureAsset` 提供语义桥接，避免复制大型资源。

### 5.2 图标边界

- 世界观稳定语义：typed + custom vector。
- 跨组件平台行为和状态：typed + SF Symbols。
- 页面内部一次性内容 pictogram：允许直接 SF Symbol，不做机械全局包装。
- 一级导航由 `NavigationItem.iconSource` 作为单一视觉事实源。

### 5.3 图标尺寸

当前已实现并由测试锁定：16 / 20 / 24 / 32 pt。新增尺寸前必须先更新 token/API/测试，不在调用方写新的隐式 size scale。

## 6. Token 对齐原则

`docs/05_UI/design_tokens.json` 与 `DesignTokens.swift` 继续承担数值事实源。视觉系统按以下语义域消费：

- Color
- Surface
- Stroke
- Shadow
- Radius
- Spacing
- Motion
- Iconography
- Texture
- Accessibility

新增组件优先组合现有 token；若 token 确实缺失，应先补 semantic token，再消费它，而不是在多个组件中复制魔法数字。

## 7. macOS 技术路线

优先级固定为：

1. **SwiftUI 程序化绘制**：控件底板、边框、状态层、Focus、阴影、轻量发光、Loading/Status feedback。
2. **Asset Catalog Vector**：世界观图标、Sigil、Seal、Ornament。
3. **少量高质量纹理**：灰雾、旧纸、金属、帷幕；纹理只增强质感，不承担控件状态。

系统事实优先读取 SwiftUI environment：Focus、Increase Contrast、Differentiate Without Color、Reduced Motion、Reduced Transparency、active appearance 等不自建平行状态机。

## 8. 已形成的核心 API

```text
WOMIconAsset
WOMNavigationIconAsset
WOMSystemIcon
WOMStatusIcon
WOMIconSource
WOMIcon
WOMTextureAsset
WOMButtonStyle
WOMIconButtonStyle
WOMToolbarButtonStyle
WOMPanelBackground
WOMCardChrome
WOMTextureLayer
WOMSectionHeaderStyle
WOMDividerOrnament
```

主题层提供语义，Asset Catalog 提供资源，避免巨型全局 Singleton。

## 9. 可访问性与性能边界

- 支持键盘导航、Focus Ring 与 Scene Commands。
- Hover 不能成为唯一反馈。
- 支持 Reduced Motion。
- Reduced Transparency / Increase Contrast 下保留清晰边界。
- Differentiate Without Color 下关键状态必须有非颜色几何差异。
- icon 可由调用方提供语义标签；纯装饰 icon 默认隐藏于 VoiceOver。
- Overlay/Loading 不使用持续高成本 blur/mask 动画。
- 大型纹理不复制，不在高频控件重复解码多份资源。

## 10. 实际交付路线与状态

### Foundation — PR #21–#25（DONE）

完成核心/导航世界观图标、系统行为语义、Ornament、Texture 基线和持久化文档基础。

### Wave B — PR #26（DONE）

完成 Icon / Button / Surface primitives、Component Gallery、Sidebar、Ritual、Codex/Archive、Artifact/Fate 与 App Shell 迁移。

### Wave C — PR #27（DONE）

完成 Focus / Increase Contrast / Differentiate Without Color / inactive appearance / Reduced Motion & Transparency，以及视觉系统 semantic regression tests。

### Wave D — PR #28（DONE）

完成 Asset Catalog contract、typed icon 使用边界、9 个导航与 ⌘1–⌘9 契约、Commands typed icon、⌘K → Advice 原生 Focus 链，以及 placeholder 生产接入条件。

### Wave E — Overlay & Feedback Chrome（CURRENT）

目标：补齐应用级交互壳层与状态反馈，不改变业务状态机。

计划能力：

1. `WOMOverlayPanel`：Inspector / Popover / Sheet 内容统一 chrome；呈现仍由系统 API 完成。
2. `WOMLoadingState`：统一 Loading / waiting / unavailable 等视觉状态，尊重 Reduced Motion。
3. `WOMStatusBanner`：Info / Success / Warning / Danger 的持久状态提示。
4. `MysticEmptyState` typed icon 兼容升级：保留旧 raw SF Symbol API，同时提供 `WOMIconSource` 入口。
5. Component Gallery Overlay/Feedback specimen。
6. Overlay semantic contract tests。

### Future — Production Binding

Character / Story Book / Cards / Worldline / Notes 只有在真实领域数据源、状态/错误模型、交互回调与测试到位后才从 placeholder 升级为生产页面。不得用静态 demo 数据绕过这一条件。

## 11. 页面与展示真实性

- Component Gallery 是设计系统 Showcase / Visual Regression 观察入口，不代表业务功能完成。
- Sidebar、Fate、App Shell 已是生产入口。
- Ritual 当前以真实组件存在，但没有独立一级路由。
- Codex / Archive / Cards / Worldline 等已有高质量 View primitive，不等于已接入生产数据链。
- placeholder 必须继续明确功能状态，直到真实生产绑定满足条件。

## 12. 恢复协议

新执行环境恢复视觉系统工作时按顺序读取：

1. 本总体方案；
2. `visual-assets/README.md` Living Plan；
3. 当前 Wave Batch 文档；
4. 当前 Wave Task Capsule；
5. 当前 PR base/head 与 diff；
6. `DesignSystem/WOM*` 与 Component Gallery；
7. 最终 CI/readback 状态。

任何与上述事实冲突的聊天摘要、旧 PR body 或历史计划，以仓库当前文件和远端 Git 状态为准。
