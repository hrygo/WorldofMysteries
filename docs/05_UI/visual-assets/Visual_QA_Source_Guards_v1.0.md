# Visual QA Source Guards v1.0

> 状态：ACTIVE  
> 上位契约：`Visual_QA_Contract_v1.0.md`  
> 目标：把可读性、响应式布局、对比度和 macOS 原生性要求从人工检查升级为自动工程契约。

## 1. 扫描范围

生产视觉 Swift 源码：

- `macos-app/WorldOfMysteries/DesignSystem/`
- `macos-app/WorldOfMysteries/Components/`
- `macos-app/WorldOfMysteries/Artifacts/`
- `macos-app/WorldOfMysteries/ContentView.swift`
- `macos-app/WorldOfMysteries/MyApp.swift`

不扫描 Tests 作为生产规则对象；测试自身可以包含被禁止模式的字符串，用于断言。

## 2. Guard A — 禁止 9pt 及以下直接语义字号

扫描 `.font(.system(size: ...))`，数值 **< 10pt** 即失败。

理由：Visual QA Contract 已规定 10pt 仅用于短数字、快捷键和极短标签；9pt 及以下不得承载关键语义。使用更小字号不应成为解决布局压力的方法。

这条规则不禁止：

- `Font.Mystic.caption`（11pt）；
- `Font.Mystic.monoBadge`（11pt）；
- 10pt 的紧凑短标签；
- 图形几何尺寸（例如 6pt 状态点），因为它们不是文字。

## 3. Guard B — 禁止 `.minimumScaleFactor`

生产视觉代码不得通过 `minimumScaleFactor` 自动缩小文本以塞进固定布局。

正确处理：

- 允许换行；
- 使用 `ViewThatFits`；
- 使用 adaptive Grid；
- 改为纵向 fallback；
- 放宽非关键固定宽度。

## 4. Guard C — 内容布局层禁止负 padding

扫描：

- `Components/`
- `Artifacts/`
- `ContentView.swift`

禁止 `.padding(..., -N)` / `.padding(-N)` 这类负值布局修补。

`DesignSystem/` 不纳入这条 blanket ban，因为 focus ring 外扩等视觉实现可以合理使用负 padding；这类实现必须局限于基础样式层，不能变成页面布局手段。

## 5. Guard D — 视觉层禁止自建窗口基础设施

生产视觉范围禁止直接引入：

- `NSPanel`
- `NSWindow`
- `NSViewRepresentable`

窗口、Inspector、Popover、Sheet 优先使用 SwiftUI/macOS 原生机制：

- `WindowGroup`
- `.defaultSize`
- `.inspector`
- `.inspectorColumnWidth`
- `.popover`
- `.sheet`

若未来确实需要 AppKit bridge，必须独立高风险 Task Capsule 评审，不得在普通视觉 PR 中顺手引入。

## 6. Guard E — Approved Contrast Matrix

`VisualContrastContractTests.swift` 直接解析 `DesignTokens.swift` 的 RGB Token，并按 WCAG 相对亮度公式计算批准组合。

### AAA / 长文本优先组合（>= 7:1）

- `textPrimary` / `obsidianBase`
- `textPrimary` / `obsidianCard`
- `textPrimary` / `deepVoid`
- `textSecondary` / `obsidianBase`
- `textSecondary` / `obsidianCard`
- `textGoldAccent` / `obsidianCard`
- `textGoldAccent` / `deepVoid`
- `brassGoldPrimary` / `obsidianCard`
- `parchmentInk` / `parchmentCard`
- `parchmentInkSecondary` / `parchmentCard`

### AA 普通文字组合（>= 4.5:1）

- `textSecondary` / `deepVoid`
- `textTertiary` / `obsidianBase`
- `textTertiary` / `obsidianCard`（10-11pt 元数据大量落在卡片面，底线收紧到 6:1）
- `brassGoldMuted` / `obsidianCard`（小字号金色元数据，底线 5:1）
- `spiritualBlue` / `obsidianCard`
- `statusOnline` / `obsidianCard`
- `statusWarning` / `obsidianCard`
- `textPrimary` / `crimsonThread`（Danger Button）
- `parchmentInkTertiary` / `parchmentCard`

### 非文本边界与徽标底座（>= 3:1 / >= 4.5:1）

- `brassGoldBoundary` / `obsidianBase` 与 / `obsidianCard`：承担输入框轮廓、hover 与选中态描边，满足 1.4.11 的 3:1；
  使用时不得低于 0.9 不透明度，否则会重新跌回不可辨识区间。装饰性发丝线继续使用 `brassGoldBorder`，不受此约束。
- `crimsonBadge` 上的白色计数数字：徽标承载 10pt 白字，必须使用自己的实底；
  装饰语义色 `crimsonStar` 对白字仅 4.2:1，禁止直接作为计数徽标底色。

未进入批准矩阵的动态 pathway/accent/status 色，默认只能承担图标、边界、装饰或大面积状态提示；若要承担正文，必须先纳入可计算对比度契约。

Contrast Matrix 只验证不含透明合成的 Token 基础组合；带 opacity / texture / material 的最终视觉仍需人工 Visual QA 和压力 Preview 验证。

## 7. Guard F — 状态诚实性（Honest State）

`VisualHonestyContractTests.swift` 守护的是「界面可以说得少，但不能说得不真」。以下断言任一被打破，都意味着产品重新开始向用户宣称它并不知道的状态：

1. **连接状态唯一来源**：顶栏只能消费 `AppState.connectionState`；`EngineIPCClient.isScaffoldOnly` 为真时状态必须停在 `scaffoldPreview`，不得出现「已就绪 · IPC 活跃」，且必须同时显示示例数据标识。
2. **四库 HUD 默认未探明**：`DatabaseProbeStatus` 默认 `notProbed`，探针不可达时不得渲染容量、健康度或可点击的重建按钮。
3. **导航徽标数据驱动**：`AppSidebarView.badgeCounts` 默认必须为空字典，禁止常量徽标制造假待办。
4. **规划中入口自曝状态**：`NavigationItem.availability` 为 `planned` 的入口必须在侧边栏、菜单与落地页同时标明「规划中」，且落地页说明目标与能力边界，禁止工程自述式占位文案。
5. **叙事数值单一事实源**：人物名、序列、灵性、世界时间只能来自 `DemoWorldSnapshot`，禁止同屏出现两套互相矛盾的数值。
6. **建议台语境化**：常驻建议台只在 `NavigationItem.showsAdviceConsole` 为真的页面挂载，并在滚动内容底部预留内边距。
7. **聆听符号去科技感**：Listening Ring 不得使用麦克风作为主视觉（对齐 `Interaction_Runtime_State_v1.0.md` §10）。
8. **滚动所有权唯一**：页面级滚动容器只能有一个，画廊等子树不得自带嵌套滚动。

## 8. 明确不做的过度规则

以下模式**不做全局禁止**，因为存在合法使用场景：

- `.offset(...)`：状态点、徽标等局部视觉定位可合法使用；
- `.lineLimit(1)`：短标签/紧凑工具栏可合法使用；
- `.opacity(...)`：装饰、背景、disabled chrome 可合法使用；
- 10pt 字号：短数字/快捷键/极短标签可用；
- 固定图标尺寸：图标本身需要稳定 optical size。

这些仍受最终可读性与布局验收约束，但不通过粗暴字符串禁令治理。

## 9. 失败处理

Source Guard / Contrast Guard 失败时：

1. 优先修实现或 Token；
2. 不通过提高最小窗口、缩字或降低内容量绕过；
3. 若确认是合法例外，应修改 Guard 的语义范围，而不是添加无解释的路径白名单；
4. 例外规则必须同步更新本文件与 Batch 记录；
5. 新增可读文字颜色组合必须进入 Approved Contrast Matrix。

## 10. 与人工 Visual QA 的关系

自动 Guard 不能替代人工检查：

- 带透明度、纹理、Material 后的最终合成对比度；
- 960×640 的真实视觉重叠；
- Inspector 280pt 压力；
- 中英文排版节奏；
- 工整对齐和视觉重量；
- 用户缩放、动态内容和系统辅助功能组合。

因此 Component Gallery / Native Inspector Preview / Xcode build 仍是必需的回归面。
