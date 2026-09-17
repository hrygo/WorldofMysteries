# Visual QA Source Guards v1.0

> 状态：ACTIVE  
> 上位契约：`Visual_QA_Contract_v1.0.md`  
> 目标：把可读性、响应式布局和 macOS 原生性要求从人工检查升级为自动源代码契约。

## 1. 扫描范围

生产视觉 Swift 源码：

- `macos-app/WorldOfMysteries/DesignSystem/`
- `macos-app/WorldOfMysteries/Components/`
- `macos-app/WorldOfMysteries/Artifacts/`
- `macos-app/WorldOfMysteries/ContentView.swift`
- `macos-app/WorldOfMysteries/MyApp.swift`

不扫描 Tests / Preview-only test targets 作为生产规则对象；测试自身可以包含被禁止模式的字符串，用于断言。

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

## 6. 明确不做的过度规则

以下模式**不做全局禁止**，因为存在合法使用场景：

- `.offset(...)`：状态点、徽标等局部视觉定位可合法使用；
- `.lineLimit(1)`：短标签/紧凑工具栏可合法使用；
- `.opacity(...)`：装饰、背景、disabled chrome 可合法使用；
- 10pt 字号：短数字/快捷键/极短标签可用；
- 固定图标尺寸：图标本身需要稳定 optical size。

这些仍受最终可读性与布局验收约束，但不通过粗暴字符串禁令治理。

## 7. 失败处理

Source Guard 失败时：

1. 优先修实现；
2. 不通过提高最小窗口、缩字或降低内容量绕过；
3. 若确认是合法例外，应修改 Guard 的语义范围，而不是添加无解释的路径白名单；
4. 例外规则必须同步更新本文件与 Batch 记录。

## 8. 与人工 Visual QA 的关系

Source Guard 只能防止已知高风险写法，不能替代人工检查：

- 最终合成对比度；
- 纹理背景上的实际可读性；
- 960×640 的真实视觉重叠；
- Inspector 280pt 压力；
- 中英文排版节奏；
- 工整对齐和视觉重量。

因此 Component Gallery / Native Inspector Preview / Xcode build 仍是必需的回归面。
