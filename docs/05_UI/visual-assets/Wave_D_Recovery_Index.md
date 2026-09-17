# Visual Asset System — Wave D Recovery Index

> Durable workspace: PR #28 / `feat/wom-visual-system-wave-d`  
> 状态：DRAFT / CONTINUOUS PERSISTENCE

## 1. 本阶段目的

Wave D 不是继续堆叠视觉素材，而是把 Wave B / C 建立的设计系统变成可长期维护的工程契约：

1. Asset Catalog 与 typed registry 自动一致；
2. 自有 SVG 的 template/vector 属性不可静默回退；
3. 平台动作继续由 SF Symbols 提供，不复制成自有资产；
4. typed icon 与局部 raw SF Symbol 的职责边界明确；
5. 一级导航、Section 与 ⌘1–⌘9 结构保持稳定；
6. 后续键盘/Focus 改动必须建立在这些结构事实之上。

## 2. 当前已落盘

### 方案

- `Batch_18_Asset_Catalog_Contracts.md`
- `Typed_Icon_Usage_Boundaries_v1.0.md`
- `Batch_19_Keyboard_Navigation_Contracts.md`

### 测试实现

- `VisualAssetCatalogContractTests.swift`
  - typed custom icon registry ↔ `wom.icon.*.imageset`
  - SVG template rendering intent
  - vector preservation
  - SVG payload existence
  - texture imageset/payload existence
  - texture alias reuse
  - platform action glyph 不复制成 custom imageset

- `VisualNavigationContractTests.swift`
  - 9 个一级入口
  - shortcut 1...9 唯一覆盖
  - NavigationSection 完整且无重复覆盖
  - Sidebar / ContentView 关键入口继续使用 typed `iconSource`

## 3. 当前未宣称完成的事项

- Wave D Task Capsule 尚需在 PR 最终基线固定前补齐/复核；
- 新测试尚未执行最终 `MACOS_APP_P0`，不得标记为通过；
- `AppMenuBarCommands` / Scene Commands 的真实快捷键实现仍需审计；
- placeholder 页面仍按现有产品事实保留，不因视觉系统成熟而自动升级为“已完成”。

## 4. 下一恢复动作

新执行环境从此处恢复后按顺序：

1. 回读 PR #28 base/head 与 changed files；
2. 读取 Batch 18 / Typed Icon Boundary / Batch 19；
3. 静态审查两个新增 Swift Testing 文件；
4. 审计 `AppMenuBarCommands.swift` 与 App Scene Commands；
5. 若需要修改 Commands，新增专用 Task Capsule，不扩大测试 Capsule；
6. 完成所有 Wave D 原子 commit；
7. 对最终 head 运行一次完整 `MACOS_APP_P0`；
8. 只根据最终 CI 与 diff 回读结果决定合并。

## 5. 完成判定

Wave D 只有同时满足以下条件才算完成：

- Asset Catalog contract tests 编译并通过；
- navigation contract tests 编译并通过；
- Task Capsule scope 覆盖最终 diff；
- Architecture / Contracts / Python / Swift 6 / Xcode App Target / PR Gate Reporter 全绿；
- PR 最终 diff 无 Engine / DB / IPC / schema 越界；
- 主线合并后回读 `main` 确认目标提交存在。
